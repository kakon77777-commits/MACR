from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .canonical import sha256_id
from .execution import AcceptanceState, MaterializationState, VerificationState
from .verification_graph import CrossFileVerifierComposition, VerifierGraph


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True)
class CrossFileCandidate:
    member_digest: str
    target_key: str
    candidate_sha256: str
    shared_contract_digest: str

    def __post_init__(self) -> None:
        for name in (
            "member_digest",
            "target_key",
            "candidate_sha256",
            "shared_contract_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "member_digest": self.member_digest,
            "target_key": self.target_key,
            "candidate_sha256": self.candidate_sha256,
            "shared_contract_digest": self.shared_contract_digest,
        }


@dataclass(frozen=True)
class CrossFileVerificationRequest:
    plan_digest: str
    repository_id: str
    shared_contract_digest: str
    candidates: tuple[CrossFileCandidate, ...]
    verifier: CrossFileVerifierComposition

    def __post_init__(self) -> None:
        for name in (
            "plan_digest",
            "repository_id",
            "shared_contract_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        if isinstance(self.candidates, (str, bytes)):
            raise ValueError("cross-file candidates must be an array")
        candidates = tuple(self.candidates)
        if len(candidates) < 2 or any(
            not isinstance(item, CrossFileCandidate) for item in candidates
        ):
            raise ValueError("cross-file verification requires at least two candidates")
        candidates = tuple(sorted(candidates, key=lambda item: item.member_digest))
        if len({item.member_digest for item in candidates}) != len(candidates):
            raise ValueError("cross-file candidates contain duplicate members")
        if any(
            item.shared_contract_digest != self.shared_contract_digest
            for item in candidates
        ):
            raise ValueError("cross-file candidates do not share the shared contract")
        if not isinstance(self.verifier, CrossFileVerifierComposition):
            raise ValueError("verifier must be a CrossFileVerifierComposition")
        object.__setattr__(self, "candidates", candidates)

    @property
    def request_digest(self) -> str:
        return sha256_id(
            "crossfile_verification_request_v1",
            {
                "plan_digest": self.plan_digest,
                "repository_id": self.repository_id,
                "shared_contract_digest": self.shared_contract_digest,
                "candidates": [item.to_dict() for item in self.candidates],
                "verifier_composition_digest": self.verifier.composition_digest,
            },
        )


@dataclass(frozen=True)
class VerifierStageObservation:
    graph_digest: str
    state: VerificationState
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "graph_digest",
            _digest("graph_digest", self.graph_digest),
        )
        if self.state not in {VerificationState.PASSED, VerificationState.FAILED}:
            raise ValueError("verifier stage state must be passed or failed")
        object.__setattr__(
            self,
            "evidence_digest",
            _digest("evidence_digest", self.evidence_digest),
        )


class CrossFileVerifierBackend(Protocol):
    def verify(
        self,
        graph: VerifierGraph,
        *,
        candidate_sha256s: Iterable[str],
        shared_contract_digest: str,
        repository_id: str,
    ) -> VerifierStageObservation: ...


@dataclass(frozen=True)
class CrossFileVerificationResult:
    request_digest: str
    candidate_set_digest: str
    individual_states: tuple[str, ...]
    individual_evidence_digests: tuple[str, ...]
    integration_state: str
    integration_evidence_digest: str | None
    verifier_composition_digest: str
    acceptance_state: AcceptanceState = AcceptanceState.PENDING
    materialization_state: MaterializationState = MaterializationState.NONE
    automatic_materialization: bool = False

    def __post_init__(self) -> None:
        for name in (
            "request_digest",
            "candidate_set_digest",
            "verifier_composition_digest",
        ):
            _digest(name, getattr(self, name))
        if self.acceptance_state is not AcceptanceState.PENDING:
            raise ValueError("cross-file acceptance must remain pending")
        if self.materialization_state is not MaterializationState.NONE:
            raise ValueError("cross-file verification cannot materialize candidates")
        if self.automatic_materialization is not False:
            raise ValueError("automatic materialization must remain disabled")


class CrossFileVerifier:
    def __init__(self, backend: CrossFileVerifierBackend) -> None:
        if not callable(getattr(backend, "verify", None)):
            raise ValueError("backend must implement verify")
        self.backend = backend

    def verify(
        self,
        request: CrossFileVerificationRequest,
    ) -> CrossFileVerificationResult:
        if not isinstance(request, CrossFileVerificationRequest):
            raise ValueError("request must be a CrossFileVerificationRequest")
        individual: list[VerifierStageObservation] = []
        for candidate in request.candidates:
            observation = self.backend.verify(
                request.verifier.individual_graph,
                candidate_sha256s=(candidate.candidate_sha256,),
                shared_contract_digest=request.shared_contract_digest,
                repository_id=request.repository_id,
            )
            self._validate_observation(
                observation,
                request.verifier.individual_graph,
            )
            individual.append(observation)
        integration: VerifierStageObservation | None = None
        if all(item.state is VerificationState.PASSED for item in individual):
            integration = self.backend.verify(
                request.verifier.integration_graph,
                candidate_sha256s=tuple(
                    item.candidate_sha256 for item in request.candidates
                ),
                shared_contract_digest=request.shared_contract_digest,
                repository_id=request.repository_id,
            )
            self._validate_observation(
                integration,
                request.verifier.integration_graph,
            )
        candidate_set_digest = sha256_id(
            "crossfile_candidate_set_v1",
            [item.to_dict() for item in request.candidates],
        )
        return CrossFileVerificationResult(
            request_digest=request.request_digest,
            candidate_set_digest=candidate_set_digest,
            individual_states=tuple(item.state.value for item in individual),
            individual_evidence_digests=tuple(
                item.evidence_digest for item in individual
            ),
            integration_state=(
                VerificationState.NOT_RUN.value
                if integration is None
                else integration.state.value
            ),
            integration_evidence_digest=(
                None if integration is None else integration.evidence_digest
            ),
            verifier_composition_digest=request.verifier.composition_digest,
        )

    @staticmethod
    def _validate_observation(
        observation: VerifierStageObservation,
        graph: VerifierGraph,
    ) -> None:
        if not isinstance(observation, VerifierStageObservation):
            raise TypeError("cross-file backend returned invalid observation")
        if observation.graph_digest != graph.graph_digest:
            raise ValueError("cross-file verifier graph mismatch")


__all__ = [
    "CrossFileCandidate",
    "CrossFileVerificationRequest",
    "CrossFileVerificationResult",
    "CrossFileVerifier",
    "CrossFileVerifierBackend",
    "VerifierStageObservation",
]
