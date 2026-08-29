from __future__ import annotations

import re
from dataclasses import dataclass
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


def _digest_set(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain SHA-256 digests")
    normalized = tuple(_digest(f"{name} item", item) for item in values)
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _identifier_set(
    name: str,
    values: Iterable[str],
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain identifiers")
    normalized = tuple(_identifier(f"{name} item", item) for item in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class VerifierNode:
    node_id: str
    tool: str
    version: str
    input_digests: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    config_digest: str | None = None
    required: bool = True

    def __post_init__(self) -> None:
        node_id = _identifier("node_id", self.node_id)
        tool = _identifier("tool", self.tool)
        version = _identifier("version", self.version)
        input_digests = _digest_set("input_digests", self.input_digests)
        depends_on = _identifier_set("depends_on", self.depends_on)
        if node_id in depends_on:
            raise ValueError("verifier node may not depend on itself")
        config_digest = self.config_digest
        if config_digest is not None:
            config_digest = _digest("config_digest", config_digest)
        if not isinstance(self.required, bool):
            raise ValueError("required must be boolean")
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "tool", tool)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "input_digests", input_digests)
        object.__setattr__(self, "depends_on", depends_on)
        object.__setattr__(self, "config_digest", config_digest)

    @property
    def node_digest(self) -> str:
        return sha256_id("verifier_node_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "tool": self.tool,
            "version": self.version,
            "input_digests": list(self.input_digests),
            "depends_on": list(self.depends_on),
            "config_digest": self.config_digest,
            "required": self.required,
        }


@dataclass(frozen=True)
class VerifierGraph:
    nodes: tuple[VerifierNode, ...]
    graph_digest: str

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("verifier graph must not be empty")
        if any(not isinstance(item, VerifierNode) for item in self.nodes):
            raise ValueError("verifier graph nodes must be VerifierNode values")
        expected_nodes = self._topological_nodes(self.nodes)
        if self.nodes != expected_nodes:
            raise ValueError("verifier graph nodes are not in canonical topology order")
        expected = sha256_id(
            "verifier_graph_v1",
            {"nodes": [item.to_dict() for item in self.nodes]},
        )
        if self.graph_digest != expected:
            raise ValueError("verifier graph digest does not match graph")

    @classmethod
    def build(cls, nodes: Iterable[VerifierNode]) -> "VerifierGraph":
        if isinstance(nodes, (str, bytes)):
            raise ValueError("verifier graph nodes must be VerifierNode values")
        canonical = cls._topological_nodes(tuple(nodes))
        return cls(
            nodes=canonical,
            graph_digest=sha256_id(
                "verifier_graph_v1",
                {"nodes": [item.to_dict() for item in canonical]},
            ),
        )

    @staticmethod
    def _topological_nodes(
        nodes: tuple[VerifierNode, ...],
    ) -> tuple[VerifierNode, ...]:
        if not nodes:
            raise ValueError("verifier graph must not be empty")
        if any(not isinstance(item, VerifierNode) for item in nodes):
            raise ValueError("verifier graph nodes must be VerifierNode values")
        by_id = {item.node_id: item for item in nodes}
        if len(by_id) != len(nodes):
            raise ValueError("verifier graph contains duplicate node_id")
        for item in nodes:
            missing = sorted(set(item.depends_on) - set(by_id))
            if missing:
                raise ValueError(
                    f"verifier graph missing dependency: {missing[0]}"
                )
        remaining = {key: set(item.depends_on) for key, item in by_id.items()}
        ordered: list[VerifierNode] = []
        while remaining:
            ready = sorted(
                node_id for node_id, dependencies in remaining.items()
                if not dependencies
            )
            if not ready:
                raise ValueError("verifier graph contains a cycle")
            for node_id in ready:
                ordered.append(by_id[node_id])
                del remaining[node_id]
            for dependencies in remaining.values():
                dependencies.difference_update(ready)
        return tuple(ordered)

    def to_dict(self) -> dict[str, object]:
        return {
            "graph_digest": self.graph_digest,
            "nodes": [item.to_dict() for item in self.nodes],
        }


__all__ = ["VerifierGraph", "VerifierNode"]
