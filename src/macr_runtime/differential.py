from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import sha256_id
from .execution import AcceptanceState, VerificationState
from .verification_graph import VerifierGraph, VerifierNode


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PACK_KEYS = frozenset({"schema_version", "pack_id", "version", "cases"})
_CASE_KEYS = frozenset(
    {
        "case_id",
        "task_digest",
        "verifier_graph_digest",
        "context_class",
        "cost_ceiling_usd",
    }
)


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _cost(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite non-negative")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be finite non-negative")
    return normalized


def _positive_int(name: str, value: object, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _exact_keys(name: str, value: Mapping[str, Any], expected: frozenset[str]) -> None:
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} keys must be strings")
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        raise ValueError(f"{name} fields must be exact")


@dataclass(frozen=True)
class DifferentialProbeCase:
    case_id: str
    task_digest: str
    verifier_graph_digest: str
    context_class: str
    cost_ceiling_usd: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _identifier("case_id", self.case_id))
        object.__setattr__(
            self,
            "task_digest",
            _digest("task_digest", self.task_digest),
        )
        object.__setattr__(
            self,
            "verifier_graph_digest",
            _digest("verifier_graph_digest", self.verifier_graph_digest),
        )
        object.__setattr__(
            self,
            "context_class",
            _identifier("context_class", self.context_class),
        )
        object.__setattr__(
            self,
            "cost_ceiling_usd",
            _cost("cost_ceiling_usd", self.cost_ceiling_usd),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "task_digest": self.task_digest,
            "verifier_graph_digest": self.verifier_graph_digest,
            "context_class": self.context_class,
            "cost_ceiling_usd": self.cost_ceiling_usd,
        }


@dataclass(frozen=True)
class DifferentialProbePack:
    schema_version: int
    pack_id: str
    version: str
    cases: tuple[DifferentialProbeCase, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("probe pack schema_version must be 1")
        object.__setattr__(self, "pack_id", _identifier("pack_id", self.pack_id))
        object.__setattr__(self, "version", _identifier("version", self.version))
        if isinstance(self.cases, (str, bytes)):
            raise ValueError("probe pack cases must be an array")
        cases = tuple(self.cases)
        if not cases or any(
            not isinstance(item, DifferentialProbeCase) for item in cases
        ):
            raise ValueError("probe pack must contain probe cases")
        cases = tuple(sorted(cases, key=lambda item: item.case_id))
        if len({item.case_id for item in cases}) != len(cases):
            raise ValueError("probe pack contains duplicate case_id")
        object.__setattr__(self, "cases", cases)

    @property
    def pack_digest(self) -> str:
        return sha256_id("differential_probe_pack_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "pack_id": self.pack_id,
            "version": self.version,
            "cases": [item.to_dict() for item in self.cases],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DifferentialProbePack":
        if not isinstance(data, Mapping):
            raise ValueError("probe pack must be an object")
        _exact_keys("probe pack", data, _PACK_KEYS)
        raw_cases = data.get("cases")
        if not isinstance(raw_cases, list):
            raise ValueError("probe pack cases must be an array")
        cases = []
        for raw in raw_cases:
            if not isinstance(raw, Mapping):
                raise ValueError("probe case must be an object")
            _exact_keys("probe case", raw, _CASE_KEYS)
            cases.append(
                DifferentialProbeCase(
                    case_id=raw["case_id"],
                    task_digest=raw["task_digest"],
                    verifier_graph_digest=raw["verifier_graph_digest"],
                    context_class=raw["context_class"],
                    cost_ceiling_usd=raw["cost_ceiling_usd"],
                )
            )
        return cls(
            schema_version=data["schema_version"],
            pack_id=data["pack_id"],
            version=data["version"],
            cases=tuple(cases),
        )


@dataclass(frozen=True)
class DifferentialRouteCandidate:
    qualification_key: str
    route_proposal_digest: str
    route_id: str
    cost_ceiling_usd: float

    def __post_init__(self) -> None:
        for name in (
            "qualification_key",
            "route_proposal_digest",
            "route_id",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "cost_ceiling_usd",
            _cost("cost_ceiling_usd", self.cost_ceiling_usd),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "qualification_key": self.qualification_key,
            "route_proposal_digest": self.route_proposal_digest,
            "route_id": self.route_id,
            "cost_ceiling_usd": self.cost_ceiling_usd,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DifferentialRouteCandidate":
        if not isinstance(data, Mapping) or set(data) != {
            "qualification_key",
            "route_proposal_digest",
            "route_id",
            "cost_ceiling_usd",
        }:
            raise ValueError("differential route candidate fields must be exact")
        return cls(**data)


@dataclass(frozen=True)
class DifferentialCostPolicy:
    per_candidate_cost_ceiling_usd: float
    aggregate_cost_ceiling_usd: float
    minimum_candidate_routes: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "per_candidate_cost_ceiling_usd",
            _cost(
                "per_candidate_cost_ceiling_usd",
                self.per_candidate_cost_ceiling_usd,
            ),
        )
        object.__setattr__(
            self,
            "aggregate_cost_ceiling_usd",
            _cost(
                "aggregate_cost_ceiling_usd",
                self.aggregate_cost_ceiling_usd,
            ),
        )
        object.__setattr__(
            self,
            "minimum_candidate_routes",
            _positive_int(
                "minimum_candidate_routes",
                self.minimum_candidate_routes,
                maximum=32,
            ),
        )
        if self.minimum_candidate_routes < 3:
            raise ValueError("minimum candidate routes must be at least three")

    @property
    def policy_digest(self) -> str:
        return sha256_id("differential_cost_policy_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "per_candidate_cost_ceiling_usd": (
                self.per_candidate_cost_ceiling_usd
            ),
            "aggregate_cost_ceiling_usd": self.aggregate_cost_ceiling_usd,
            "minimum_candidate_routes": self.minimum_candidate_routes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DifferentialCostPolicy":
        if not isinstance(data, Mapping) or set(data) != {
            "per_candidate_cost_ceiling_usd",
            "aggregate_cost_ceiling_usd",
            "minimum_candidate_routes",
        }:
            raise ValueError("differential cost policy fields must be exact")
        return cls(**data)


@dataclass(frozen=True)
class DifferentialManifestMember:
    case_id: str
    candidate_id: str
    member_digest: str
    task_digest: str
    context_class: str
    qualification_key: str
    route_proposal_digest: str
    route_id: str
    verifier_graph_digest: str
    cost_ceiling_usd: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _identifier("case_id", self.case_id))
        object.__setattr__(
            self,
            "context_class",
            _identifier("context_class", self.context_class),
        )
        for name in (
            "candidate_id",
            "member_digest",
            "task_digest",
            "qualification_key",
            "route_proposal_digest",
            "route_id",
            "verifier_graph_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "cost_ceiling_usd",
            _cost("cost_ceiling_usd", self.cost_ceiling_usd),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "candidate_id": self.candidate_id,
            "member_digest": self.member_digest,
            "task_digest": self.task_digest,
            "context_class": self.context_class,
            "qualification_key": self.qualification_key,
            "route_proposal_digest": self.route_proposal_digest,
            "route_id": self.route_id,
            "verifier_graph_digest": self.verifier_graph_digest,
            "cost_ceiling_usd": self.cost_ceiling_usd,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DifferentialManifestMember":
        if not isinstance(data, Mapping) or set(data) != {
            "case_id",
            "candidate_id",
            "member_digest",
            "task_digest",
            "context_class",
            "qualification_key",
            "route_proposal_digest",
            "route_id",
            "verifier_graph_digest",
            "cost_ceiling_usd",
        }:
            raise ValueError("differential manifest member fields must be exact")
        return cls(**data)


@dataclass(frozen=True)
class DifferentialRunManifest:
    probe_pack_digest: str
    verifier_graph_digest: str
    cost_policy_digest: str
    per_candidate_cost_ceiling_usd: float
    aggregate_cost_ceiling_usd: float
    minimum_candidate_routes: int
    members: tuple[DifferentialManifestMember, ...]
    authority_issued: bool = False
    network_activity: bool = False
    execution_performed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "probe_pack_digest",
            "verifier_graph_digest",
            "cost_policy_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "per_candidate_cost_ceiling_usd",
            _cost(
                "per_candidate_cost_ceiling_usd",
                self.per_candidate_cost_ceiling_usd,
            ),
        )
        object.__setattr__(
            self,
            "aggregate_cost_ceiling_usd",
            _cost(
                "aggregate_cost_ceiling_usd",
                self.aggregate_cost_ceiling_usd,
            ),
        )
        minimum = _positive_int(
            "minimum_candidate_routes",
            self.minimum_candidate_routes,
            maximum=32,
        )
        if minimum < 3:
            raise ValueError("minimum candidate routes must be at least three")
        expected_policy = DifferentialCostPolicy(
            per_candidate_cost_ceiling_usd=(
                self.per_candidate_cost_ceiling_usd
            ),
            aggregate_cost_ceiling_usd=self.aggregate_cost_ceiling_usd,
            minimum_candidate_routes=minimum,
        )
        if expected_policy.policy_digest != self.cost_policy_digest:
            raise ValueError(
                "differential manifest cost policy digest mismatch"
            )
        if isinstance(self.members, (str, bytes)):
            raise ValueError("differential manifest members must be an array")
        members = tuple(self.members)
        if not members or any(
            not isinstance(item, DifferentialManifestMember) for item in members
        ):
            raise ValueError("differential manifest must contain members")
        members = tuple(sorted(members, key=lambda item: (item.case_id, item.candidate_id)))
        keys = tuple((item.case_id, item.candidate_id) for item in members)
        if len(keys) != len(set(keys)):
            raise ValueError("differential manifest contains duplicate members")
        if len({item.candidate_id for item in members}) < minimum:
            raise ValueError("differential manifest has too few candidate routes")
        if any(
            item.verifier_graph_digest != self.verifier_graph_digest
            or item.cost_ceiling_usd > self.per_candidate_cost_ceiling_usd + 1e-12
            for item in members
        ):
            raise ValueError("differential manifest member contract mismatch")
        for item in members:
            expected_candidate = sha256_id(
                "differential_blind_candidate_v1",
                {
                    "probe_pack_digest": self.probe_pack_digest,
                    "qualification_key": item.qualification_key,
                    "route_proposal_digest": item.route_proposal_digest,
                    "route_id": item.route_id,
                },
            )
            member_data = {
                "case_id": item.case_id,
                "candidate_id": item.candidate_id,
                "task_digest": item.task_digest,
                "context_class": item.context_class,
                "qualification_key": item.qualification_key,
                "route_proposal_digest": item.route_proposal_digest,
                "route_id": item.route_id,
                "verifier_graph_digest": item.verifier_graph_digest,
                "cost_ceiling_usd": item.cost_ceiling_usd,
            }
            expected_member = sha256_id(
                "differential_manifest_member_v1",
                member_data,
            )
            if (
                item.candidate_id != expected_candidate
                or item.member_digest != expected_member
            ):
                raise ValueError(
                    "differential manifest member digest mismatch"
                )
        cases_by_candidate: dict[str, set[str]] = {}
        for item in members:
            cases_by_candidate.setdefault(item.candidate_id, set()).add(
                item.case_id
            )
        case_sets = {tuple(sorted(value)) for value in cases_by_candidate.values()}
        if len(case_sets) != 1:
            raise ValueError(
                "differential manifest is not an exact candidate-case matrix"
            )
        if sum(item.cost_ceiling_usd for item in members) > self.aggregate_cost_ceiling_usd + 1e-12:
            raise ValueError("differential manifest aggregate cost exceeds policy")
        if self.authority_issued or self.network_activity or self.execution_performed:
            raise ValueError("differential manifest cannot execute or issue authority")
        object.__setattr__(self, "minimum_candidate_routes", minimum)
        object.__setattr__(self, "members", members)

    @property
    def manifest_digest(self) -> str:
        return sha256_id("differential_run_manifest_v1", self.canonical_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {
            "probe_pack_digest": self.probe_pack_digest,
            "verifier_graph_digest": self.verifier_graph_digest,
            "cost_policy_digest": self.cost_policy_digest,
            "per_candidate_cost_ceiling_usd": (
                self.per_candidate_cost_ceiling_usd
            ),
            "aggregate_cost_ceiling_usd": self.aggregate_cost_ceiling_usd,
            "minimum_candidate_routes": self.minimum_candidate_routes,
            "members": [item.to_dict() for item in self.members],
            "authority_issued": self.authority_issued,
            "network_activity": self.network_activity,
            "execution_performed": self.execution_performed,
        }

    def to_dict(self) -> dict[str, object]:
        return {"manifest_digest": self.manifest_digest, **self.canonical_dict()}

    @classmethod
    def build(
        cls,
        probe_pack: DifferentialProbePack,
        route_candidates: Iterable[DifferentialRouteCandidate],
        verifier_graph: VerifierGraph,
        cost_policy: DifferentialCostPolicy,
    ) -> "DifferentialRunManifest":
        if not isinstance(probe_pack, DifferentialProbePack):
            raise ValueError("probe_pack must be a DifferentialProbePack")
        if not isinstance(verifier_graph, VerifierGraph):
            raise ValueError("verifier_graph must be a VerifierGraph")
        if not isinstance(cost_policy, DifferentialCostPolicy):
            raise ValueError("cost_policy must be a DifferentialCostPolicy")
        if isinstance(route_candidates, (str, bytes)):
            raise ValueError("route_candidates must contain candidate routes")
        routes = tuple(route_candidates)
        if any(not isinstance(item, DifferentialRouteCandidate) for item in routes):
            raise ValueError("route_candidates must contain candidate routes")
        routes = tuple(sorted(routes, key=lambda item: item.route_id))
        if len(routes) < cost_policy.minimum_candidate_routes:
            raise ValueError("too few candidate routes for differential run")
        for name, values in (
            ("route", (item.route_id for item in routes)),
            ("qualification", (item.qualification_key for item in routes)),
            ("route proposal", (item.route_proposal_digest for item in routes)),
        ):
            values = tuple(values)
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {name} in differential candidates")
        if any(
            item.verifier_graph_digest != verifier_graph.graph_digest
            for item in probe_pack.cases
        ):
            raise ValueError("probe pack verifier graph does not match exact graph")
        members = []
        for case in probe_pack.cases:
            for route in routes:
                if (
                    route.cost_ceiling_usd > case.cost_ceiling_usd + 1e-12
                    or route.cost_ceiling_usd
                    > cost_policy.per_candidate_cost_ceiling_usd + 1e-12
                ):
                    raise ValueError(
                        "differential candidate cost exceeds hard ceiling"
                    )
                candidate_id = sha256_id(
                    "differential_blind_candidate_v1",
                    {
                        "probe_pack_digest": probe_pack.pack_digest,
                        "qualification_key": route.qualification_key,
                        "route_proposal_digest": route.route_proposal_digest,
                        "route_id": route.route_id,
                    },
                )
                member_data = {
                    "case_id": case.case_id,
                    "candidate_id": candidate_id,
                    "task_digest": case.task_digest,
                    "context_class": case.context_class,
                    "qualification_key": route.qualification_key,
                    "route_proposal_digest": route.route_proposal_digest,
                    "route_id": route.route_id,
                    "verifier_graph_digest": verifier_graph.graph_digest,
                    "cost_ceiling_usd": route.cost_ceiling_usd,
                }
                members.append(
                    DifferentialManifestMember(
                        member_digest=sha256_id(
                            "differential_manifest_member_v1",
                            member_data,
                        ),
                        **member_data,
                    )
                )
        return cls(
            probe_pack_digest=probe_pack.pack_digest,
            verifier_graph_digest=verifier_graph.graph_digest,
            cost_policy_digest=cost_policy.policy_digest,
            per_candidate_cost_ceiling_usd=(
                cost_policy.per_candidate_cost_ceiling_usd
            ),
            aggregate_cost_ceiling_usd=(
                cost_policy.aggregate_cost_ceiling_usd
            ),
            minimum_candidate_routes=cost_policy.minimum_candidate_routes,
            members=tuple(members),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DifferentialRunManifest":
        if not isinstance(data, Mapping):
            raise ValueError("differential manifest must be an object")
        expected = {
            "manifest_digest",
            "probe_pack_digest",
            "verifier_graph_digest",
            "cost_policy_digest",
            "per_candidate_cost_ceiling_usd",
            "aggregate_cost_ceiling_usd",
            "minimum_candidate_routes",
            "members",
            "authority_issued",
            "network_activity",
            "execution_performed",
        }
        if set(data) != expected or not isinstance(data.get("members"), list):
            raise ValueError("differential manifest fields must be exact")
        manifest = cls(
            probe_pack_digest=data["probe_pack_digest"],
            verifier_graph_digest=data["verifier_graph_digest"],
            cost_policy_digest=data["cost_policy_digest"],
            per_candidate_cost_ceiling_usd=data[
                "per_candidate_cost_ceiling_usd"
            ],
            aggregate_cost_ceiling_usd=data["aggregate_cost_ceiling_usd"],
            minimum_candidate_routes=data["minimum_candidate_routes"],
            members=tuple(
                DifferentialManifestMember.from_dict(item)
                for item in data["members"]
            ),
            authority_issued=data["authority_issued"],
            network_activity=data["network_activity"],
            execution_performed=data["execution_performed"],
        )
        if data["manifest_digest"] != manifest.manifest_digest:
            raise ValueError("differential manifest digest mismatch")
        return manifest


@dataclass(frozen=True)
class DifferentialCandidateResult:
    manifest_digest: str
    case_id: str
    candidate_id: str
    candidate_sha256: str
    verifier_state: VerificationState
    verifier_evidence_digest: str
    observed_cost_usd: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "manifest_digest",
            _digest("manifest_digest", self.manifest_digest),
        )
        object.__setattr__(self, "case_id", _identifier("case_id", self.case_id))
        for name in (
            "candidate_id",
            "candidate_sha256",
            "verifier_evidence_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        if self.verifier_state not in {
            VerificationState.PASSED,
            VerificationState.FAILED,
        }:
            raise ValueError("differential verifier state must be passed or failed")
        object.__setattr__(
            self,
            "observed_cost_usd",
            _cost("observed_cost_usd", self.observed_cost_usd),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "case_id": self.case_id,
            "candidate_id": self.candidate_id,
            "candidate_sha256": self.candidate_sha256,
            "verifier_state": self.verifier_state.value,
            "verifier_evidence_digest": self.verifier_evidence_digest,
            "observed_cost_usd": self.observed_cost_usd,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DifferentialCandidateResult":
        if not isinstance(data, Mapping) or set(data) != {
            "manifest_digest",
            "case_id",
            "candidate_id",
            "candidate_sha256",
            "verifier_state",
            "verifier_evidence_digest",
            "observed_cost_usd",
        }:
            raise ValueError("differential result fields must be exact")
        try:
            state = VerificationState(data["verifier_state"])
        except (TypeError, ValueError) as exc:
            raise ValueError("differential result verifier_state is invalid") from exc
        return cls(
            manifest_digest=data["manifest_digest"],
            case_id=data["case_id"],
            candidate_id=data["candidate_id"],
            candidate_sha256=data["candidate_sha256"],
            verifier_state=state,
            verifier_evidence_digest=data["verifier_evidence_digest"],
            observed_cost_usd=data["observed_cost_usd"],
        )


@dataclass(frozen=True)
class DifferentialPublicRow:
    candidate_id: str
    passed_count: int
    failed_count: int
    observed_cost_usd: float
    evidence_set_digest: str
    model_label: None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _digest("candidate_id", self.candidate_id),
        )
        for name in ("passed_count", "failed_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        object.__setattr__(
            self,
            "observed_cost_usd",
            _cost("observed_cost_usd", self.observed_cost_usd),
        )
        object.__setattr__(
            self,
            "evidence_set_digest",
            _digest("evidence_set_digest", self.evidence_set_digest),
        )
        if self.model_label is not None:
            raise ValueError("differential public row model label must remain hidden")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "model_label": None,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "observed_cost_usd": self.observed_cost_usd,
            "evidence_set_digest": self.evidence_set_digest,
        }


@dataclass(frozen=True)
class DifferentialComparison:
    manifest_digest: str
    replay_digest: str
    public_rows: tuple[DifferentialPublicRow, ...]
    aggregate_observed_cost_usd: float
    acceptance_state: AcceptanceState = AcceptanceState.PENDING
    execution_performed: bool = False

    def __post_init__(self) -> None:
        _digest("manifest_digest", self.manifest_digest)
        _digest("replay_digest", self.replay_digest)
        if self.acceptance_state is not AcceptanceState.PENDING:
            raise ValueError("differential acceptance must remain pending")
        if self.execution_performed is not False:
            raise ValueError("differential replay cannot execute providers")

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "replay_digest": self.replay_digest,
            "public_rows": [item.to_dict() for item in self.public_rows],
            "aggregate_observed_cost_usd": self.aggregate_observed_cost_usd,
            "acceptance_state": self.acceptance_state.value,
            "execution_performed": self.execution_performed,
        }


def compare_differential_results(
    manifest: DifferentialRunManifest,
    results: Iterable[DifferentialCandidateResult],
    probe_pack: DifferentialProbePack,
) -> DifferentialComparison:
    if not isinstance(manifest, DifferentialRunManifest):
        raise ValueError("manifest must be a DifferentialRunManifest")
    if not isinstance(probe_pack, DifferentialProbePack):
        raise ValueError("probe_pack must be a DifferentialProbePack")
    if probe_pack.pack_digest != manifest.probe_pack_digest:
        raise ValueError("differential manifest does not match exact probe pack")
    cases = {item.case_id: item for item in probe_pack.cases}
    manifest_case_ids = {item.case_id for item in manifest.members}
    if manifest_case_ids != set(cases):
        raise ValueError(
            "differential manifest case matrix does not match exact probe pack"
        )
    for member in manifest.members:
        probe_case = cases[member.case_id]
        if (
            member.task_digest != probe_case.task_digest
            or member.context_class != probe_case.context_class
            or member.verifier_graph_digest
            != probe_case.verifier_graph_digest
            or member.cost_ceiling_usd > probe_case.cost_ceiling_usd + 1e-12
        ):
            raise ValueError(
                "differential manifest member does not match exact probe pack"
            )
    if isinstance(results, (str, bytes)):
        raise ValueError("results must contain differential results")
    observations = tuple(results)
    if any(not isinstance(item, DifferentialCandidateResult) for item in observations):
        raise ValueError("results must contain differential results")
    keys = tuple((item.case_id, item.candidate_id) for item in observations)
    if len(keys) != len(set(keys)):
        raise ValueError("differential results contain duplicate members")
    expected = {(item.case_id, item.candidate_id): item for item in manifest.members}
    actual = {(item.case_id, item.candidate_id): item for item in observations}
    if set(actual) != set(expected):
        raise ValueError("differential results do not match the exact manifest")
    ordered = tuple(actual[key] for key in sorted(actual))
    for item in ordered:
        member = expected[(item.case_id, item.candidate_id)]
        if item.manifest_digest != manifest.manifest_digest:
            raise ValueError("differential result manifest digest mismatch")
        if item.observed_cost_usd > member.cost_ceiling_usd + 1e-12:
            raise ValueError("differential result cost exceeds member ceiling")
    aggregate = sum(item.observed_cost_usd for item in ordered)
    if aggregate > manifest.aggregate_cost_ceiling_usd + 1e-12:
        raise ValueError("differential aggregate observed cost exceeds ceiling")
    grouped: dict[str, list[DifferentialCandidateResult]] = {}
    for item in ordered:
        grouped.setdefault(item.candidate_id, []).append(item)
    rows = []
    for candidate_id, items in grouped.items():
        rows.append(
            DifferentialPublicRow(
                candidate_id=candidate_id,
                passed_count=sum(
                    item.verifier_state is VerificationState.PASSED
                    for item in items
                ),
                failed_count=sum(
                    item.verifier_state is VerificationState.FAILED
                    for item in items
                ),
                observed_cost_usd=sum(item.observed_cost_usd for item in items),
                evidence_set_digest=sha256_id(
                    "differential_evidence_set_v1",
                    [
                        {
                            "case_id": item.case_id,
                            "candidate_sha256": item.candidate_sha256,
                            "verifier_state": item.verifier_state.value,
                            "verifier_evidence_digest": (
                                item.verifier_evidence_digest
                            ),
                        }
                        for item in items
                    ],
                ),
            )
        )
    rows = sorted(
        rows,
        key=lambda item: (
            -item.passed_count,
            item.failed_count,
            item.observed_cost_usd,
            item.candidate_id,
        ),
    )
    replay_digest = sha256_id(
        "differential_replay_v1",
        {
            "manifest_digest": manifest.manifest_digest,
            "results": [item.to_dict() for item in ordered],
        },
    )
    return DifferentialComparison(
        manifest_digest=manifest.manifest_digest,
        replay_digest=replay_digest,
        public_rows=tuple(rows),
        aggregate_observed_cost_usd=aggregate,
    )


def verifier_graph_from_dict(data: Mapping[str, Any]) -> VerifierGraph:
    if not isinstance(data, Mapping) or set(data) != {"graph_digest", "nodes"}:
        raise ValueError("verifier graph fields must be exact")
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("verifier graph nodes must be an array")
    nodes = []
    expected_node_keys = {
        "node_id",
        "tool",
        "version",
        "input_digests",
        "depends_on",
        "config_digest",
        "required",
    }
    for raw in raw_nodes:
        if not isinstance(raw, Mapping) or set(raw) != expected_node_keys:
            raise ValueError("verifier graph node fields must be exact")
        nodes.append(
            VerifierNode(
                node_id=raw["node_id"],
                tool=raw["tool"],
                version=raw["version"],
                input_digests=tuple(raw["input_digests"]),
                depends_on=tuple(raw["depends_on"]),
                config_digest=raw["config_digest"],
                required=raw["required"],
            )
        )
    return VerifierGraph(nodes=tuple(nodes), graph_digest=data["graph_digest"])


def build_differential_manifest(data: Mapping[str, Any]) -> DifferentialRunManifest:
    if not isinstance(data, Mapping) or set(data) != {
        "probe_pack",
        "route_candidates",
        "verifier_graph",
        "cost_policy",
    }:
        raise ValueError("differential plan input fields must be exact")
    raw_routes = data.get("route_candidates")
    if not isinstance(raw_routes, list):
        raise ValueError("route_candidates must be an array")
    return DifferentialRunManifest.build(
        DifferentialProbePack.from_dict(data["probe_pack"]),
        tuple(DifferentialRouteCandidate.from_dict(item) for item in raw_routes),
        verifier_graph_from_dict(data["verifier_graph"]),
        DifferentialCostPolicy.from_dict(data["cost_policy"]),
    )


def strict_json_bytes(data: bytes) -> Any:
    if not isinstance(data, bytes) or len(data) > 8 * 1024 * 1024:
        raise ValueError("differential JSON must be bounded bytes")

    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("differential JSON has duplicate keys")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except UnicodeDecodeError as exc:
        raise ValueError("differential JSON must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("differential JSON is invalid") from exc


__all__ = [
    "DifferentialCandidateResult",
    "DifferentialComparison",
    "DifferentialCostPolicy",
    "DifferentialManifestMember",
    "DifferentialProbeCase",
    "DifferentialProbePack",
    "DifferentialPublicRow",
    "DifferentialRouteCandidate",
    "DifferentialRunManifest",
    "build_differential_manifest",
    "compare_differential_results",
    "strict_json_bytes",
    "verifier_graph_from_dict",
]
