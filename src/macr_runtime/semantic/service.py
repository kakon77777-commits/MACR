from __future__ import annotations

from dataclasses import dataclass, field

from .._v07_contracts import (
    canonical_record_digest,
    normalize_timestamp,
    require_optional_non_empty,
    require_sha256,
)
from .errors import SemanticStateError
from .patch import SemanticPatchCompiler, SemanticPatchProposalRequest
from .store import SemanticStore


@dataclass(frozen=True)
class SemanticProposalRecord:
    proposal: SemanticPatchProposalRequest
    state: str
    compiled_digest: str | None
    failure_code: str | None
    created_at: str
    terminal_at: str | None
    record_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, SemanticPatchProposalRequest):
            raise ValueError("proposal must be SemanticPatchProposalRequest")
        if self.state not in {"proposed", "validation_failed", "committed"}:
            raise ValueError("semantic proposal state is invalid")
        if self.compiled_digest is not None:
            object.__setattr__(
                self,
                "compiled_digest",
                require_sha256("compiled_digest", self.compiled_digest),
            )
        object.__setattr__(
            self,
            "failure_code",
            require_optional_non_empty("failure_code", self.failure_code, max_bytes=128),
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp("created_at", self.created_at),
        )
        if self.terminal_at is not None:
            object.__setattr__(
                self,
                "terminal_at",
                normalize_timestamp("terminal_at", self.terminal_at),
            )
        if self.state == "proposed" and (
            self.compiled_digest is None
            or self.failure_code is not None
            or self.terminal_at is not None
        ):
            raise ValueError("proposed semantic record fields are inconsistent")
        if self.state == "validation_failed" and (
            self.compiled_digest is not None
            or self.failure_code is None
            or self.terminal_at is None
        ):
            raise ValueError("failed semantic record fields are inconsistent")
        object.__setattr__(
            self,
            "record_digest",
            canonical_record_digest(
                "macr.semantic.proposal-record.v1",
                {
                    "proposal_digest": self.proposal.proposal_digest,
                    "state": self.state,
                    "compiled_digest": self.compiled_digest,
                    "failure_code": self.failure_code,
                    "created_at": self.created_at,
                    "terminal_at": self.terminal_at,
                },
            ),
        )


class SemanticProposalService:
    """Agent/model-facing proposal persistence without commit authority."""

    def __init__(self, store: SemanticStore) -> None:
        if not isinstance(store, SemanticStore):
            raise ValueError("store must be a SemanticStore")
        self.store = store
        self.compiler = SemanticPatchCompiler(store.registry)

    def propose_patch(
        self,
        proposal: SemanticPatchProposalRequest,
        *,
        created_at: str,
    ) -> SemanticProposalRecord:
        if not isinstance(proposal, SemanticPatchProposalRequest):
            raise ValueError("proposal must be SemanticPatchProposalRequest")
        timestamp = normalize_timestamp("created_at", created_at)
        try:
            existing = self.store.get_proposal(proposal.proposal_id)
        except Exception as exc:
            from .errors import SemanticGraphNotFoundError

            if not isinstance(exc, SemanticGraphNotFoundError):
                raise
        else:
            if existing.proposal == proposal:
                return existing
            from .errors import SemanticPatchConflictError

            raise SemanticPatchConflictError(
                "semantic proposal ID conflicts with existing proposal"
            )

        head = self.store.get_graph_head(proposal.graph_id)
        nodes = self.store.get_active_nodes(proposal.graph_id)
        relations = self.store.get_active_relations(proposal.graph_id)
        try:
            compiled = self.compiler.compile(
                head=head,
                proposal=proposal,
                active_nodes=nodes,
                active_relations=relations,
            )
        except SemanticStateError as exc:
            record = SemanticProposalRecord(
                proposal=proposal,
                state="validation_failed",
                compiled_digest=None,
                failure_code=exc.code,
                created_at=timestamp,
                terminal_at=timestamp,
            )
        else:
            record = SemanticProposalRecord(
                proposal=proposal,
                state="proposed",
                compiled_digest=compiled.compiled_digest,
                failure_code=None,
                created_at=timestamp,
                terminal_at=None,
            )
        return self.store.save_proposal(record)

    def get_proposal(self, proposal_id: str) -> SemanticProposalRecord:
        return self.store.get_proposal(proposal_id)
