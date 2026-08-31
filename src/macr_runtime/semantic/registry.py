from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Mapping

from .._v07_contracts import (
    canonical_record_digest,
    freeze_json_value,
    public_json_value,
    require_closed_mapping,
    require_non_empty,
    require_sha256,
    require_string_tuple,
)
from ..action.contracts import EffectName, VerificationVerdict
from ..canonical import canonical_json_bytes
from .contracts import (
    ClaimStatus,
    ResolutionStatus,
    SemanticLifecycleStatus,
    SemanticNodeType,
    SemanticRelationType,
)
from .errors import SemanticRegistryMismatchError, SemanticRegistryUnknownError


SEMANTIC_REGISTRY_SCHEMA_VERSION = "macr-semantic-registry/v1"
_FAILURE_TYPES = frozenset(
    {
        "MODEL_FAILURE", "PROVIDER_FAILURE", "CAPABILITY_MISSING",
        "AUTHORITY_DENIED", "BUDGET_EXHAUSTED", "WORLD_STALE",
        "PROJECTION_FAILED", "VERIFICATION_FAILED", "ACTION_DIVERGED",
        "CHECKPOINT_INVALID", "WAKE_INVALID", "DEPENDENCY_FAILED",
        "RECONCILIATION_REQUIRED", "HUMAN_DECISION_REQUIRED",
    }
)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate registry key: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class SemanticRegistry:
    schema_version: str
    registry_version: str
    node_types: tuple[str, ...]
    relation_rules: Mapping[str, object]
    effect_types: tuple[str, ...]
    status_types: tuple[str, ...]
    verdict_types: tuple[str, ...]
    failure_types: tuple[str, ...]
    registry_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != SEMANTIC_REGISTRY_SCHEMA_VERSION:
            raise SemanticRegistryMismatchError("semantic registry schema mismatch")
        object.__setattr__(
            self,
            "registry_version",
            require_non_empty("registry_version", self.registry_version, max_bytes=64),
        )
        object.__setattr__(
            self,
            "node_types",
            require_string_tuple("node_types", self.node_types, maximum=128),
        )
        if set(self.node_types) != {item.value for item in SemanticNodeType}:
            raise SemanticRegistryMismatchError("semantic registry node types mismatch")
        rules = self._validated_rules(self.relation_rules)
        object.__setattr__(self, "relation_rules", MappingProxyType(rules))
        expected_relations = {item.value for item in SemanticRelationType}
        if set(rules) != expected_relations:
            raise SemanticRegistryMismatchError("semantic registry relation types mismatch")
        object.__setattr__(
            self,
            "effect_types",
            require_string_tuple("effect_types", self.effect_types, maximum=128),
        )
        if set(self.effect_types) != {item.value for item in EffectName}:
            raise SemanticRegistryMismatchError("semantic registry effect types mismatch")
        object.__setattr__(
            self,
            "status_types",
            require_string_tuple("status_types", self.status_types, maximum=128),
        )
        expected_statuses = {
            *(item.value for item in SemanticLifecycleStatus),
            *(item.value for item in ClaimStatus),
            *(item.value for item in ResolutionStatus),
        }
        if set(self.status_types) != expected_statuses:
            raise SemanticRegistryMismatchError("semantic registry status types mismatch")
        object.__setattr__(
            self,
            "verdict_types",
            require_string_tuple("verdict_types", self.verdict_types, maximum=128),
        )
        if set(self.verdict_types) != {item.value for item in VerificationVerdict}:
            raise SemanticRegistryMismatchError("semantic registry verdict types mismatch")
        object.__setattr__(
            self,
            "failure_types",
            require_string_tuple("failure_types", self.failure_types, maximum=128),
        )
        if set(self.failure_types) != _FAILURE_TYPES:
            raise SemanticRegistryMismatchError("semantic registry failure types mismatch")
        object.__setattr__(
            self,
            "registry_digest",
            canonical_record_digest(
                "macr.semantic.registry.v1",
                self._identity_dict(),
            ),
        )

    def _validated_rules(self, value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise SemanticRegistryMismatchError("relation_rules must be an object")
        known_nodes = {item.value for item in SemanticNodeType}
        rules: dict[str, object] = {}
        for relation, rule in value.items():
            relation_name = require_non_empty("relation type", relation)
            parsed = require_closed_mapping(
                "relation rule",
                rule,
                required=frozenset({"source_types", "target_types"}),
                optional=frozenset(),
            )
            sources = require_string_tuple(
                "source_types", parsed["source_types"], maximum=128
            )
            targets = require_string_tuple(
                "target_types", parsed["target_types"], maximum=128
            )
            if not sources or not targets:
                raise SemanticRegistryMismatchError("relation direction sets cannot be empty")
            if any(item != "*" and item not in known_nodes for item in (*sources, *targets)):
                raise SemanticRegistryMismatchError("relation rule contains unknown node type")
            rules[relation_name] = MappingProxyType(
                {"source_types": sources, "target_types": targets}
            )
        return dict(sorted(rules.items()))

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "registry_version": self.registry_version,
            "node_types": list(self.node_types),
            "relation_rules": {
                key: {
                    "source_types": list(rule["source_types"]),
                    "target_types": list(rule["target_types"]),
                }
                for key, rule in self.relation_rules.items()
            },
            "effect_types": list(self.effect_types),
            "status_types": list(self.status_types),
            "verdict_types": list(self.verdict_types),
            "failure_types": list(self.failure_types),
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "registry_digest": self.registry_digest}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_public_dict())

    @property
    def relation_types(self) -> tuple[str, ...]:
        return tuple(self.relation_rules)

    @classmethod
    def from_builtin(cls) -> "SemanticRegistry":
        text = files("macr_runtime.semantic").joinpath(
            "schemas/registry-v1.json"
        ).read_text(encoding="utf-8")
        data = json.loads(text, object_pairs_hook=_strict_object)
        return cls._from_payload(data)

    @classmethod
    def _from_payload(cls, data: Mapping[str, Any]) -> "SemanticRegistry":
        parsed = require_closed_mapping(
            "SemanticRegistry payload",
            data,
            required=frozenset(
                {
                    "schema_version", "registry_version", "node_types",
                    "relation_rules", "effect_types", "status_types",
                    "verdict_types", "failure_types",
                }
            ),
            optional=frozenset(),
        )
        return cls(
            schema_version=parsed["schema_version"],
            registry_version=parsed["registry_version"],
            node_types=tuple(parsed["node_types"]),
            relation_rules=parsed["relation_rules"],
            effect_types=tuple(parsed["effect_types"]),
            status_types=tuple(parsed["status_types"]),
            verdict_types=tuple(parsed["verdict_types"]),
            failure_types=tuple(parsed["failure_types"]),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticRegistry":
        parsed = require_closed_mapping(
            "SemanticRegistry",
            data,
            required=frozenset(
                {
                    "schema_version", "registry_version", "node_types",
                    "relation_rules", "effect_types", "status_types",
                    "verdict_types", "failure_types", "registry_digest",
                }
            ),
            optional=frozenset(),
        )
        supplied = require_sha256("registry_digest", parsed.pop("registry_digest"))
        result = cls._from_payload(parsed)
        if result.registry_digest != supplied:
            raise SemanticRegistryMismatchError("semantic registry digest mismatch")
        return result

    def _require_member(self, name: str, value: object, allowed: tuple[str, ...]) -> str:
        selected = value.value if hasattr(value, "value") else value
        if not isinstance(selected, str) or selected not in allowed:
            raise SemanticRegistryUnknownError(f"unknown semantic {name}")
        return selected

    def require_node_type(self, value: object) -> str:
        return self._require_member("node type", value, self.node_types)

    def require_relation_type(self, value: object) -> str:
        return self._require_member("relation type", value, self.relation_types)

    def require_effect(self, value: object) -> str:
        return self._require_member("effect", value, self.effect_types)

    def require_status(self, value: object) -> str:
        return self._require_member("status", value, self.status_types)

    def require_verdict(self, value: object) -> str:
        return self._require_member("verdict", value, self.verdict_types)

    def require_failure(self, value: object) -> str:
        return self._require_member("failure", value, self.failure_types)

    def require_relation(
        self,
        source_type: object,
        relation_type: object,
        target_type: object,
    ) -> None:
        source = self.require_node_type(source_type)
        relation = self.require_relation_type(relation_type)
        target = self.require_node_type(target_type)
        rule = self.relation_rules[relation]
        sources = rule["source_types"]
        targets = rule["target_types"]
        if ("*" not in sources and source not in sources) or (
            "*" not in targets and target not in targets
        ):
            raise SemanticRegistryMismatchError(
                "semantic relation direction is not allowed"
            )
