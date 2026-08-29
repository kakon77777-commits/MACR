from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .canonical import sha256_id


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded versioned identifier")
    return value


def _controls(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("mutation_controls must be identifiers")
    normalized = tuple(
        _identifier("mutation control", item) for item in values
    )
    return tuple(sorted(set(normalized)))


class ProbeClass(str, Enum):
    P0_EXACT_OUTPUT = "P0_exact_output"
    P1_STRUCTURED_JSON = "P1_structured_json"
    P2_PURE_FUNCTION = "P2_pure_function"
    P3_BOUNDED_MODULE = "P3_bounded_module"
    P4_WHOLE_FILE_REWRITE = "P4_whole_file_rewrite"
    P5_CROSS_FILE_PAIR = "P5_cross_file_pair"
    P6_TOOL_CALL_CONTRACT = "P6_tool_call_contract"
    P7_COORDINATOR_DECOMPOSITION = "P7_coordinator_decomposition"
    P8_REVIEWER_DISCRIMINATION = "P8_reviewer_discrimination"
    P9_LONG_HORIZON_ITERATION = "P9_long_horizon_iteration"


@dataclass(frozen=True)
class ProbeDefinition:
    probe_digest: str
    probe_id: str
    probe_class: ProbeClass
    version: str
    role_digest: str
    context_class: str
    verifier_suite_digest: str
    task_pack_digest: str
    held_out_variant_count: int
    cost_ceiling_usd: float
    mutation_controls: tuple[str, ...]
    contamination_notes_digest: str | None

    def __post_init__(self) -> None:
        probe_digest = _digest("probe_digest", self.probe_digest)
        probe_id = _identifier("probe_id", self.probe_id)
        if not isinstance(self.probe_class, ProbeClass):
            raise ValueError("probe_class must be a ProbeClass")
        version = _identifier("version", self.version)
        role_digest = _digest("role_digest", self.role_digest)
        context_class = _identifier("context_class", self.context_class)
        verifier_suite_digest = _digest(
            "verifier_suite_digest",
            self.verifier_suite_digest,
        )
        task_pack_digest = _digest("task_pack_digest", self.task_pack_digest)
        if isinstance(self.held_out_variant_count, bool) or not isinstance(
            self.held_out_variant_count,
            int,
        ):
            raise ValueError("held_out_variant_count must be an integer")
        if not 1 <= self.held_out_variant_count <= 100_000:
            raise ValueError("held_out_variant_count is out of range")
        if isinstance(self.cost_ceiling_usd, bool) or not isinstance(
            self.cost_ceiling_usd,
            (int, float),
        ):
            raise ValueError("cost_ceiling_usd must be finite non-negative")
        cost = float(self.cost_ceiling_usd)
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("cost_ceiling_usd must be finite non-negative")
        controls = _controls(self.mutation_controls)
        contamination = self.contamination_notes_digest
        if contamination is not None:
            contamination = _digest(
                "contamination_notes_digest",
                contamination,
            )
        object.__setattr__(self, "probe_id", probe_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "role_digest", role_digest)
        object.__setattr__(self, "context_class", context_class)
        object.__setattr__(
            self,
            "verifier_suite_digest",
            verifier_suite_digest,
        )
        object.__setattr__(self, "task_pack_digest", task_pack_digest)
        object.__setattr__(self, "cost_ceiling_usd", cost)
        object.__setattr__(self, "mutation_controls", controls)
        object.__setattr__(
            self,
            "contamination_notes_digest",
            contamination,
        )
        expected = sha256_id("probe_definition_v1", self.canonical_identity())
        if probe_digest != expected:
            raise ValueError("probe_digest does not match canonical definition")

    @classmethod
    def create(
        cls,
        probe_id: str,
        probe_class: ProbeClass,
        version: str,
        *,
        role_digest: str,
        context_class: str,
        verifier_suite_digest: str,
        task_pack_digest: str,
        held_out_variant_count: int,
        cost_ceiling_usd: float,
        mutation_controls: Iterable[str] = (),
        contamination_notes_digest: str | None = None,
    ) -> "ProbeDefinition":
        if not isinstance(probe_class, ProbeClass):
            raise ValueError("probe_class must be a ProbeClass")
        if isinstance(held_out_variant_count, bool) or not isinstance(
            held_out_variant_count,
            int,
        ):
            raise ValueError("held_out_variant_count must be an integer")
        if not 1 <= held_out_variant_count <= 100_000:
            raise ValueError("held_out_variant_count is out of range")
        if isinstance(cost_ceiling_usd, bool) or not isinstance(
            cost_ceiling_usd,
            (int, float),
        ):
            raise ValueError("cost_ceiling_usd must be finite non-negative")
        cost = float(cost_ceiling_usd)
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("cost_ceiling_usd must be finite non-negative")
        canonical = {
            "probe_id": _identifier("probe_id", probe_id),
            "probe_class": probe_class.value,
            "version": _identifier("version", version),
            "role_digest": _digest("role_digest", role_digest),
            "context_class": _identifier("context_class", context_class),
            "verifier_suite_digest": _digest(
                "verifier_suite_digest",
                verifier_suite_digest,
            ),
            "task_pack_digest": _digest(
                "task_pack_digest",
                task_pack_digest,
            ),
            "held_out_variant_count": held_out_variant_count,
            "cost_ceiling_usd": cost,
            "mutation_controls": list(_controls(mutation_controls)),
            "contamination_notes_digest": (
                _digest(
                    "contamination_notes_digest",
                    contamination_notes_digest,
                )
                if contamination_notes_digest is not None
                else None
            ),
        }
        return cls(
            probe_digest=sha256_id("probe_definition_v1", canonical),
            probe_id=canonical["probe_id"],
            probe_class=probe_class,
            version=canonical["version"],
            role_digest=canonical["role_digest"],
            context_class=canonical["context_class"],
            verifier_suite_digest=canonical["verifier_suite_digest"],
            task_pack_digest=canonical["task_pack_digest"],
            held_out_variant_count=held_out_variant_count,
            cost_ceiling_usd=cost,
            mutation_controls=tuple(canonical["mutation_controls"]),
            contamination_notes_digest=canonical[
                "contamination_notes_digest"
            ],
        )

    def canonical_identity(self) -> dict[str, object]:
        return {
            "probe_id": self.probe_id,
            "probe_class": self.probe_class.value,
            "version": self.version,
            "role_digest": self.role_digest,
            "context_class": self.context_class,
            "verifier_suite_digest": self.verifier_suite_digest,
            "task_pack_digest": self.task_pack_digest,
            "held_out_variant_count": self.held_out_variant_count,
            "cost_ceiling_usd": self.cost_ceiling_usd,
            "mutation_controls": list(self.mutation_controls),
            "contamination_notes_digest": self.contamination_notes_digest,
        }


class ProbeRegistry:
    def __init__(self, definitions: Iterable[ProbeDefinition]) -> None:
        if isinstance(definitions, (str, bytes)):
            raise ValueError("probe definitions must be ProbeDefinition values")
        items = tuple(definitions)
        if any(not isinstance(item, ProbeDefinition) for item in items):
            raise ValueError("probe definitions must be ProbeDefinition values")
        digests = tuple(item.probe_digest for item in items)
        ids = tuple(item.probe_id for item in items)
        if len(set(digests)) != len(digests) or len(set(ids)) != len(ids):
            raise ValueError("duplicate probe definition")
        self._by_digest = {item.probe_digest: item for item in items}

    def get(self, probe_digest: str) -> ProbeDefinition:
        probe_digest = _digest("probe_digest", probe_digest)
        try:
            return self._by_digest[probe_digest]
        except KeyError as exc:
            raise KeyError(f"unknown probe: {probe_digest}") from exc

    def definitions(self) -> tuple[ProbeDefinition, ...]:
        return tuple(self._by_digest[key] for key in sorted(self._by_digest))


__all__ = ["ProbeClass", "ProbeDefinition", "ProbeRegistry"]
