from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol

from ...action import (
    ActionAdmission,
    ActionProposal,
    AdmissionDecision,
    CapabilityAvailability,
    CapabilityRef,
    EffectName,
    EffectSet,
)
from ...agent.contracts import AgentRunHeader
from ...agent.ownership import AgentOwnershipPermit
from ...agent.store import AgentStore
from ...canonical import canonical_json_bytes
from ...errors import StoragePolicyError
from ...execution import AuthorizationReference
from ...semantic.projection import SemanticContextProjection
from .contracts import (
    HostedAgentCellPolicy,
    HostedAgentCellState,
    HostedModelDecision,
    HostedToolCatalog,
    HostedToolManifest,
    HostedToolRequest,
)
from .errors import HostedAgentCellBudgetError, HostedToolDeniedError


def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or (
        hasattr(os.path, "isjunction") and os.path.isjunction(path)
    )


def _exact_keys(
    arguments: Mapping[str, object],
    expected: frozenset[str],
) -> dict[str, object]:
    if not isinstance(arguments, Mapping):
        raise HostedToolDeniedError("tool arguments must be an object")
    values = dict(arguments)
    if set(values) != expected:
        raise HostedToolDeniedError("tool arguments are incomplete or unknown")
    return values


def _bounded_int(name: str, value: object, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise HostedToolDeniedError(f"{name} is outside its tool bound")
    return value


def _bounded_text(name: str, value: object, maximum: int) -> str:
    if not isinstance(value, str) or not value:
        raise HostedToolDeniedError(f"{name} must be non-empty text")
    if len(value.encode("utf-8")) > maximum:
        raise HostedToolDeniedError(f"{name} exceeds its tool bound")
    return value


@dataclass(frozen=True)
class PreparedHostedTool:
    request: HostedToolRequest
    manifest: HostedToolManifest
    arguments: Mapping[str, object]
    max_result_bytes: int


@dataclass(frozen=True)
class HostedToolAdmission:
    prepared: PreparedHostedTool
    proposal: ActionProposal
    admission: ActionAdmission


_EXECUTION_SEAL = object()


@dataclass(frozen=True)
class HostedToolExecutionPermit:
    action_id: str
    request_digest: str
    admission_digest: str
    ownership_lease_id: str
    ownership_fencing_token: int
    cell_state_digest: str
    semantic_projection_digest: str
    _seal: object


def _mint_execution_permit(
    *,
    action_id: str,
    request_digest: str,
    admission_digest: str,
    ownership: AgentOwnershipPermit,
    cell_state_digest: str,
    semantic_projection_digest: str,
) -> HostedToolExecutionPermit:
    return HostedToolExecutionPermit(
        action_id=action_id,
        request_digest=request_digest,
        admission_digest=admission_digest,
        ownership_lease_id=ownership.lease_id,
        ownership_fencing_token=ownership.fencing_token,
        cell_state_digest=cell_state_digest,
        semantic_projection_digest=semantic_projection_digest,
        _seal=_EXECUTION_SEAL,
    )


class HostedActionAuthorityVerifier(Protocol):
    def verify(
        self,
        reference: AuthorizationReference,
        *,
        agent_run_id: str,
        tool: HostedToolManifest,
        target_digest: str,
        policy_digest: str,
    ) -> None: ...


class AgentStoreOwnershipVerifier:
    def __init__(
        self,
        store: AgentStore,
        *,
        now=None,
    ) -> None:
        if not isinstance(store, AgentStore):
            raise ValueError("store must be an AgentStore")
        self.store = store
        self._now = now or (lambda: datetime.now(timezone.utc))

    def verify(self, permit: AgentOwnershipPermit) -> None:
        observed = self.store._read_ownership(permit.agent_run_id)
        if observed != permit:
            raise HostedToolDeniedError("tool ownership permit is stale")
        observed_time = self._now()
        if not isinstance(observed_time, datetime) or observed_time.tzinfo is None:
            raise ValueError("ownership verifier clock must be timezone-aware")
        if datetime.fromisoformat(permit.expires_at) <= observed_time.astimezone(
            timezone.utc
        ):
            raise HostedToolDeniedError("tool ownership permit expired")


class HostedWorkspaceTools:
    def __init__(
        self,
        root: str | Path,
        *,
        allowed_prefixes: tuple[str, ...],
        max_file_bytes: int = 2 * 1024 * 1024,
        max_scan_bytes: int = 16 * 1024 * 1024,
        max_walk_entries: int = 10_000,
    ) -> None:
        candidate = Path(root)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError("hosted workspace root must be absolute on D:")
        current = Path(candidate.anchor)
        for component in candidate.parts[1:]:
            current = current / component
            if _is_reparse(current):
                raise StoragePolicyError(
                    "hosted workspace ancestry may not contain a reparse point"
                )
        resolved = candidate.resolve(strict=True)
        if (
            _is_reparse(candidate)
            or not resolved.is_dir()
            or resolved.drive.upper() != "D:"
        ):
            raise StoragePolicyError(
                "hosted workspace root must be an ordinary directory"
            )
        self.root = resolved
        prefixes = tuple(
            self._normalize_relative(item, allow_root=True) for item in allowed_prefixes
        )
        if not prefixes or len(prefixes) != len(set(prefixes)):
            raise ValueError("allowed_prefixes must be non-empty and unique")
        self.allowed_prefixes = tuple(sorted(prefixes))
        self.max_file_bytes = _bounded_int(
            "max_file_bytes", max_file_bytes, 8 * 1024 * 1024
        )
        self.max_scan_bytes = _bounded_int(
            "max_scan_bytes", max_scan_bytes, 64 * 1024 * 1024
        )
        self.max_walk_entries = _bounded_int(
            "max_walk_entries",
            max_walk_entries,
            1_000_000,
        )
        self.execution_profile_digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "root_sha256": hashlib.sha256(
                        str(self.root).replace("\\", "/").casefold().encode("utf-8")
                    ).hexdigest(),
                    "allowed_prefixes": list(self.allowed_prefixes),
                    "max_file_bytes": self.max_file_bytes,
                    "max_scan_bytes": self.max_scan_bytes,
                    "max_walk_entries": self.max_walk_entries,
                }
            )
        ).hexdigest()
        adapter_version = "hosted-workspace-v2-" + self.execution_profile_digest
        self._consumed_execution_permits: set[str] = set()
        self._execution_lock = threading.Lock()
        read_effect = EffectName.REPOSITORY_READ
        self.catalog = HostedToolCatalog(
            (
                HostedToolManifest(
                    "workspace.list_files",
                    "List bounded ordinary files under an approved relative prefix.",
                    read_effect,
                    {
                        "type": "object",
                        "required": ["prefix", "limit"],
                        "additionalProperties": False,
                    },
                    adapter_version,
                ),
                HostedToolManifest(
                    "workspace.read_text",
                    "Read one bounded UTF-8 file under an approved relative prefix.",
                    read_effect,
                    {
                        "type": "object",
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                    adapter_version,
                ),
                HostedToolManifest(
                    "workspace.search_text",
                    "Search bounded UTF-8 files under an approved relative prefix.",
                    read_effect,
                    {
                        "type": "object",
                        "required": ["prefix", "query", "max_matches"],
                        "additionalProperties": False,
                    },
                    adapter_version,
                ),
            )
        )

    @staticmethod
    def _normalize_relative(value: object, *, allow_root: bool) -> str:
        if not isinstance(value, str) or not value:
            raise HostedToolDeniedError("workspace reference must be text")
        if "\\" in value or ":" in value or "\x00" in value:
            raise HostedToolDeniedError(
                "workspace reference is not relative POSIX form"
            )
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            if allow_root and value == ".":
                return "."
            raise HostedToolDeniedError("workspace reference escapes its scope")
        normalized = path.as_posix()
        if not normalized and allow_root:
            return "."
        return normalized

    def _is_allowed(self, relative: str) -> bool:
        return any(
            prefix == "." or relative == prefix or relative.startswith(prefix + "/")
            for prefix in self.allowed_prefixes
        )

    @staticmethod
    def _is_denied_relative(relative: str) -> bool:
        parts = tuple(part.lower() for part in PurePosixPath(relative).parts)
        name = parts[-1] if parts else ""
        return (
            ".git" in parts
            or name == ".env"
            or name.startswith(".env.")
            or PurePosixPath(name).suffix.lower() in {".key", ".pem", ".pfx"}
            or any(part in {"credentials", "secrets", "key"} for part in parts)
        )

    def _resolve(self, value: object, *, directory: bool) -> tuple[str, Path]:
        relative = self._normalize_relative(value, allow_root=directory)
        if not self._is_allowed(relative):
            raise HostedToolDeniedError(
                "workspace reference is outside approved prefixes"
            )
        if relative != "." and self._is_denied_relative(relative):
            raise HostedToolDeniedError("workspace reference is denied by local policy")
        target = (
            self.root
            if relative == "."
            else self.root.joinpath(*PurePosixPath(relative).parts)
        )
        current = self.root
        for component in () if relative == "." else PurePosixPath(relative).parts:
            current = current / component
            if _is_reparse(current):
                raise HostedToolDeniedError(
                    "workspace reference contains a reparse point"
                )
        try:
            resolved = target.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise HostedToolDeniedError("workspace reference does not exist") from exc
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise HostedToolDeniedError("workspace reference escapes its root") from exc
        if directory and not resolved.is_dir():
            raise HostedToolDeniedError("workspace prefix is not a directory")
        if not directory and not resolved.is_file():
            raise HostedToolDeniedError("workspace target is not a file")
        if not directory and self._is_denied_relative(relative):
            raise HostedToolDeniedError("workspace target is denied by local policy")
        return relative, resolved

    def _bounded_file_walk(
        self,
        directory: Path,
    ) -> tuple[tuple[Path, ...], int, bool, int]:
        stack = [directory]
        files: list[Path] = []
        examined = 0
        truncated = False
        skipped = 0
        while stack and examined < self.max_walk_entries:
            current = stack.pop()
            remaining = self.max_walk_entries - examined
            entries = []
            try:
                with os.scandir(current) as iterator:
                    for entry in iterator:
                        if len(entries) >= remaining:
                            truncated = True
                            break
                        entries.append(entry)
            except OSError:
                skipped += 1
                continue
            directories: list[Path] = []
            for entry in sorted(entries, key=lambda item: item.name):
                examined += 1
                path = Path(entry.path)
                try:
                    relative = path.relative_to(self.root).as_posix()
                    if _is_reparse(path) or self._is_denied_relative(relative):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(path)
                    elif entry.is_file(follow_symlinks=False) and self._is_allowed(
                        relative
                    ):
                        files.append(path)
                except (OSError, ValueError):
                    skipped += 1
            stack.extend(reversed(directories))
        if stack:
            truncated = True
        return tuple(files), examined, truncated, skipped

    def prepare(
        self,
        request: HostedToolRequest,
        *,
        max_result_bytes: int,
    ) -> PreparedHostedTool:
        if not isinstance(request, HostedToolRequest):
            raise ValueError("request must be a HostedToolRequest")
        try:
            manifest = self.catalog.get(request.tool_id)
        except KeyError as exc:
            raise HostedToolDeniedError("unknown hosted tool") from exc
        arguments = dict(request.arguments)
        if request.tool_id == "workspace.read_text":
            values = _exact_keys(arguments, frozenset({"path"}))
            relative, _ = self._resolve(values["path"], directory=False)
            normalized = {"path": relative}
        elif request.tool_id == "workspace.list_files":
            values = _exact_keys(arguments, frozenset({"prefix", "limit"}))
            relative, _ = self._resolve(values["prefix"], directory=True)
            normalized = {
                "prefix": relative,
                "limit": _bounded_int("limit", values["limit"], 1000),
            }
        elif request.tool_id == "workspace.search_text":
            values = _exact_keys(
                arguments,
                frozenset({"prefix", "query", "max_matches"}),
            )
            relative, _ = self._resolve(values["prefix"], directory=True)
            normalized = {
                "prefix": relative,
                "query": _bounded_text("query", values["query"], 512),
                "max_matches": _bounded_int(
                    "max_matches",
                    values["max_matches"],
                    500,
                ),
            }
        else:  # pragma: no cover - closed catalog
            raise HostedToolDeniedError("unknown hosted tool")
        return PreparedHostedTool(
            request=request,
            manifest=manifest,
            arguments=normalized,
            max_result_bytes=_bounded_int(
                "max_result_bytes",
                max_result_bytes,
                8 * 1024 * 1024,
            ),
        )

    def _execute(
        self,
        prepared: PreparedHostedTool,
        execution_permit: HostedToolExecutionPermit,
    ) -> bytes:
        if not isinstance(prepared, PreparedHostedTool):
            raise ValueError("prepared must be a PreparedHostedTool")
        if (
            not isinstance(execution_permit, HostedToolExecutionPermit)
            or execution_permit._seal is not _EXECUTION_SEAL
            or execution_permit.action_id != prepared.request.request_id
            or execution_permit.request_digest != prepared.request.request_digest
        ):
            raise HostedToolDeniedError("tool execution requires an exact host permit")
        with self._execution_lock:
            if execution_permit.action_id in self._consumed_execution_permits:
                raise HostedToolDeniedError(
                    "tool execution permit was already consumed"
                )
            self._consumed_execution_permits.add(execution_permit.action_id)
        tool_id = prepared.manifest.tool_id
        if tool_id == "workspace.read_text":
            relative, path = self._resolve(prepared.arguments["path"], directory=False)
            if path.stat().st_size > self.max_file_bytes:
                raise HostedToolDeniedError("workspace file exceeds read bound")
            with path.open("rb") as handle:
                raw = handle.read(self.max_file_bytes + 1)
            if len(raw) > self.max_file_bytes:
                raise HostedToolDeniedError("workspace file exceeds read bound")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise HostedToolDeniedError("workspace file is not UTF-8") from exc
            result = {
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "text": text,
            }
        elif tool_id == "workspace.list_files":
            prefix, directory = self._resolve(
                prepared.arguments["prefix"],
                directory=True,
            )
            limit = prepared.arguments["limit"]
            walked, examined, walk_truncated, skipped = self._bounded_file_walk(
                directory
            )
            files: list[str] = []
            result_truncated = walk_truncated or skipped > 0
            for path in walked:
                if len(files) >= limit:
                    result_truncated = True
                    break
                relative = path.relative_to(self.root).as_posix()
                files.append(relative)
                prospective = {
                    "prefix": prefix,
                    "files": files,
                    "examined_entries": examined,
                    "skipped_entries": skipped,
                    "truncated": True,
                }
                if len(canonical_json_bytes(prospective)) > prepared.max_result_bytes:
                    files.pop()
                    result_truncated = True
                    break
            result = {
                "prefix": prefix,
                "files": files,
                "examined_entries": examined,
                "skipped_entries": skipped,
                "truncated": result_truncated or len(files) < len(walked),
            }
        elif tool_id == "workspace.search_text":
            prefix, directory = self._resolve(
                prepared.arguments["prefix"],
                directory=True,
            )
            query = prepared.arguments["query"]
            maximum = prepared.arguments["max_matches"]
            scanned = 0
            walked, examined, walk_truncated, skipped = self._bounded_file_walk(
                directory
            )
            matches: list[dict[str, object]] = []
            stop = False
            for path in walked:
                if stop or len(matches) >= maximum or scanned >= self.max_scan_bytes:
                    stop = True
                    break
                relative = path.relative_to(self.root).as_posix()
                try:
                    _, verified_path = self._resolve(relative, directory=False)
                    size = verified_path.stat().st_size
                except (HostedToolDeniedError, OSError):
                    skipped += 1
                    continue
                if size > self.max_file_bytes:
                    skipped += 1
                    continue
                if scanned + size > self.max_scan_bytes:
                    stop = True
                    break
                try:
                    with verified_path.open("rb") as handle:
                        raw = handle.read(self.max_file_bytes + 1)
                except OSError:
                    skipped += 1
                    continue
                if len(raw) > self.max_file_bytes:
                    skipped += 1
                    continue
                scanned += len(raw)
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    skipped += 1
                    continue
                for number, line in enumerate(text.splitlines(), start=1):
                    if query in line:
                        matches.append(
                            {
                                "path": relative,
                                "line": number,
                                "text": line[:4096],
                            }
                        )
                        prospective = {
                            "prefix": prefix,
                            "query": query,
                            "matches": matches,
                            "scanned_bytes": scanned,
                            "examined_entries": examined,
                            "skipped_entries": skipped,
                            "truncated": True,
                        }
                        if (
                            len(canonical_json_bytes(prospective))
                            > prepared.max_result_bytes
                        ):
                            matches.pop()
                            stop = True
                            break
                        if len(matches) >= maximum:
                            stop = True
                            break
                if stop:
                    break
            result = {
                "prefix": prefix,
                "query": query,
                "matches": matches,
                "scanned_bytes": scanned,
                "examined_entries": examined,
                "skipped_entries": skipped,
                "truncated": walk_truncated or stop or skipped > 0,
            }
        else:  # pragma: no cover - closed catalog
            raise HostedToolDeniedError("unknown hosted tool")
        encoded = canonical_json_bytes(result)
        if len(encoded) > prepared.max_result_bytes:
            raise HostedToolDeniedError("tool result exceeds cell result bound")
        return encoded


class HostedActionGate:
    def __init__(
        self,
        tools: HostedWorkspaceTools,
        authority_verifier: HostedActionAuthorityVerifier,
        ownership_verifier: AgentStoreOwnershipVerifier,
    ) -> None:
        self.tools = tools
        if not callable(getattr(authority_verifier, "verify", None)):
            raise ValueError("authority_verifier must implement verify")
        self.authority_verifier = authority_verifier
        if not isinstance(ownership_verifier, AgentStoreOwnershipVerifier):
            raise ValueError("ownership_verifier is invalid")
        self.ownership_verifier = ownership_verifier

    def compile(
        self,
        *,
        header: AgentRunHeader,
        agent_run_epoch: int,
        state: HostedAgentCellState,
        policy: HostedAgentCellPolicy,
        semantic_projection: SemanticContextProjection,
        model_decision: HostedModelDecision,
        context_envelope_digest: str,
    ) -> HostedToolAdmission:
        request = model_decision.tool_request
        if request is None:
            raise ValueError("model decision has no tool request")
        if request.tool_id not in policy.allowed_tool_ids:
            raise HostedToolDeniedError("tool is not allowed by cell policy")
        if state.tool_calls >= policy.max_tool_calls:
            raise HostedAgentCellBudgetError(
                "tool-call budget is exhausted before dispatch"
            )
        if state.active_wall_ms >= round(policy.max_active_wall_seconds * 1000):
            raise HostedAgentCellBudgetError(
                "active wall budget is exhausted before tool admission"
            )
        if state.currency_cost_usd > policy.max_currency_cost_usd:
            raise HostedAgentCellBudgetError(
                "currency budget is exceeded before tool admission"
            )
        prepared = self.tools.prepare(
            request,
            max_result_bytes=policy.max_tool_result_bytes,
        )
        if prepared.manifest.effect is not EffectName.REPOSITORY_READ:
            raise HostedToolDeniedError("MVP tool effect is not read-only")
        self.authority_verifier.verify(
            header.authority.reference,
            agent_run_id=header.identity.agent_run_id,
            tool=prepared.manifest,
            target_digest=request.arguments_digest,
            policy_digest=policy.policy_digest,
        )
        action_id = request.request_id
        effects = EffectSet((prepared.manifest.effect,))
        proposal = ActionProposal(
            action_id=action_id,
            agent_run_id=header.identity.agent_run_id,
            agent_run_epoch=agent_run_epoch,
            goal_ref=header.goal.ref,
            plan_ref=(
                header.active_plan.ref
                if header.active_plan is not None
                else f"hosted-plan:{semantic_projection.projection_digest}"
            ),
            task_ref=f"hosted-step:{state.next_step - 1}",
            operation=prepared.manifest.tool_id,
            target_ref=f"hosted-target:{request.arguments_digest}",
            parameters_ref=f"private-parameters:{request.arguments_digest}",
            declared_effects=effects,
            basis_refs=(
                f"hosted-context:{context_envelope_digest}",
                f"semantic-projection:{semantic_projection.projection_digest}",
            ),
            preconditions=("ownership_current", "read_only_scope_current"),
            expected_result_ref=f"hosted-tool-result:{action_id}",
            rollback_policy_ref="not_applicable:read_only",
            verification_policy_ref="local-read-result-digest-v1",
            provenance_ref=f"hosted-model-decision:{model_decision.decision_digest}",
        )
        capability = CapabilityRef(
            capability_id=prepared.manifest.tool_id,
            provider="macr.hosted.workspace",
            operation=prepared.manifest.tool_id,
            effect_profile_ref=f"effect:{effects.effect_digest}",
            adapter_version=prepared.manifest.adapter_version,
            availability_state=CapabilityAvailability.AVAILABLE,
        )
        admission = ActionAdmission(
            action_id=action_id,
            proposal_digest=proposal.proposal_digest,
            decision=AdmissionDecision.ALLOW_WITH_VERIFY,
            effective_effects=effects,
            capability_refs=(capability,),
            authorization=header.authority.reference,
            budget_digest=header.budget.digest,
            budget_revision=header.budget.revision,
            world_basis_digest=semantic_projection.projection_digest,
            policy_snapshot_digest=policy.policy_digest,
        )
        return HostedToolAdmission(prepared, proposal, admission)

    def _recheck_before_execute(
        self,
        *,
        header: AgentRunHeader,
        policy: HostedAgentCellPolicy,
        admitted: HostedToolAdmission,
        ownership: AgentOwnershipPermit,
        state: HostedAgentCellState,
        semantic_projection: SemanticContextProjection,
    ) -> None:
        if admitted.admission.authorization != header.authority.reference:
            raise HostedToolDeniedError("tool admission authority changed")
        if admitted.admission.policy_snapshot_digest != policy.policy_digest:
            raise HostedToolDeniedError("tool admission policy changed")
        if admitted.admission.budget_digest != header.budget.digest:
            raise HostedToolDeniedError("tool admission budget changed")
        if (
            admitted.admission.world_basis_digest
            != semantic_projection.projection_digest
        ):
            raise HostedToolDeniedError("tool admission world basis changed")
        if (
            ownership.agent_run_id != state.agent_run_id
            or ownership.epoch != admitted.proposal.agent_run_epoch
            or state.tool_calls > policy.max_tool_calls
            or state.provider_calls > policy.max_provider_calls
            or state.active_wall_ms >= round(policy.max_active_wall_seconds * 1000)
            or state.currency_cost_usd > policy.max_currency_cost_usd
        ):
            raise HostedToolDeniedError("tool execution state exceeds its admission")
        self.ownership_verifier.verify(ownership)
        self.authority_verifier.verify(
            header.authority.reference,
            agent_run_id=header.identity.agent_run_id,
            tool=admitted.prepared.manifest,
            target_digest=admitted.prepared.request.arguments_digest,
            policy_digest=policy.policy_digest,
        )

    def execute(
        self,
        admitted: HostedToolAdmission,
        execution_permit: HostedToolExecutionPermit,
        *,
        header: AgentRunHeader,
        policy: HostedAgentCellPolicy,
        ownership: AgentOwnershipPermit,
        state: HostedAgentCellState,
        semantic_projection: SemanticContextProjection,
    ) -> bytes:
        self._recheck_before_execute(
            header=header,
            policy=policy,
            admitted=admitted,
            ownership=ownership,
            state=state,
            semantic_projection=semantic_projection,
        )
        if (
            execution_permit.admission_digest != admitted.admission.admission_digest
            or execution_permit.action_id != admitted.proposal.action_id
            or execution_permit.request_digest
            != admitted.prepared.request.request_digest
            or execution_permit.ownership_lease_id != ownership.lease_id
            or execution_permit.ownership_fencing_token != ownership.fencing_token
            or execution_permit.cell_state_digest != state.state_digest
            or execution_permit.semantic_projection_digest
            != semantic_projection.projection_digest
        ):
            raise HostedToolDeniedError("tool execution admission digest conflicts")
        return self.tools._execute(admitted.prepared, execution_permit)
