from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

from ..canonical import canonical_json_bytes, sha256_id
from ..config import DiscoveryProviderConfig
from ..errors import MacrError
from ..model_identity import (
    ExecutionRouteIdentity,
    IdentityStatus,
    ModelSubject,
)
from ..providers.http_json import JsonTransport, UrllibJsonTransport
from .base import DiscoveryQuery, DiscoverySnapshot, ModelObservation


PARSER_VERSION = "openrouter-models-v1"
SOURCE_ID = "openrouter_models"
PUBLIC_MODELS_URL = "https://openrouter.ai/api/v1/models"
_PRICE_FIELDS = frozenset(
    {
        "prompt",
        "completion",
        "request",
        "image",
        "audio",
        "web_search",
        "internal_reasoning",
        "input_cache_read",
        "input_cache_write",
        "input_audio_cache",
    }
)


class OpenRouterDiscoveryError(MacrError):
    """OpenRouter discovery bytes do not satisfy the reviewed parser contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _object(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpenRouterDiscoveryError(f"{name} must be an object")
    return value


def _text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpenRouterDiscoveryError(f"{name} must be non-empty text")
    normalized = value.strip()
    if len(normalized.encode("utf-8")) > maximum:
        raise OpenRouterDiscoveryError(f"{name} is too long")
    return normalized


def _optional_text(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _text(name, value)


def _non_negative_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpenRouterDiscoveryError(
            f"{name} must be a non-negative integer, not a boolean"
        )
    return value


def _string_array(name: str, value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise OpenRouterDiscoveryError(f"{name} must be an array of strings")
    normalized = tuple(_text(f"{name} item", item, maximum=128) for item in value)
    if len(set(normalized)) != len(normalized):
        raise OpenRouterDiscoveryError(f"{name} contains duplicate values")
    return tuple(sorted(normalized))


def _price(name: str, value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise OpenRouterDiscoveryError(f"{name} price must be finite and non-negative")
    if isinstance(value, float) and not math.isfinite(value):
        raise OpenRouterDiscoveryError(f"{name} price must be finite and non-negative")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise OpenRouterDiscoveryError(
            f"{name} price must be finite and non-negative"
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise OpenRouterDiscoveryError(f"{name} price must be finite and non-negative")
    return str(value)


def _strict_document(raw_bytes: bytes) -> Mapping[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise OpenRouterDiscoveryError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise OpenRouterDiscoveryError(f"non-finite JSON constant: {value}")

    try:
        decoded = raw_bytes.decode("utf-8")
        document = json.loads(
            decoded,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except OpenRouterDiscoveryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise OpenRouterDiscoveryError(
            "OpenRouter snapshot must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(document, Mapping):
        raise OpenRouterDiscoveryError("OpenRouter root must be an object")
    return document


def _architecture(value: object) -> dict[str, object]:
    data = _object("architecture", value)
    return {
        "modality": _text("architecture.modality", data.get("modality")),
        "input_modalities": list(
            _string_array(
                "architecture.input_modalities",
                data.get("input_modalities"),
            )
        ),
        "output_modalities": list(
            _string_array(
                "architecture.output_modalities",
                data.get("output_modalities"),
            )
        ),
        "tokenizer": _text("architecture.tokenizer", data.get("tokenizer")),
        "instruct_type": _optional_text(
            "architecture.instruct_type",
            data.get("instruct_type"),
        ),
    }


def _pricing(value: object) -> list[dict[str, str]]:
    data = _object("pricing", value)
    normalized = {
        key: _price(f"pricing.{key}", data[key])
        for key in sorted(_PRICE_FIELDS & set(data))
    }
    for required in ("prompt", "completion"):
        if required not in normalized:
            raise OpenRouterDiscoveryError(
                f"pricing.{required} is required"
            )
    return [
        {"price_kind": key, "usd_per_unit": normalized[key]}
        for key in sorted(normalized)
    ]


def _top_provider(value: object) -> dict[str, object]:
    data = _object("top_provider", value)
    moderated = data.get("is_moderated")
    if not isinstance(moderated, bool):
        raise OpenRouterDiscoveryError("top_provider.is_moderated must be boolean")
    maximum = data.get("max_completion_tokens")
    if maximum is not None:
        maximum = _non_negative_integer(
            "top_provider.max_completion_tokens",
            maximum,
        )
    return {
        "context_length": _non_negative_integer(
            "top_provider.context_length",
            data.get("context_length"),
        ),
        "max_completion_tokens": maximum,
        "is_moderated": moderated,
    }


def _expiration(value: object) -> str | None:
    if value is None:
        return None
    text = _text("expiration_date", value, maximum=32)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise OpenRouterDiscoveryError(
            "expiration_date must be an ISO date"
        ) from exc
    return text


class OpenRouterModelNormalizer:
    parser_version = PARSER_VERSION

    def normalize(
        self,
        snapshot: DiscoverySnapshot,
    ) -> tuple[ModelObservation, ...]:
        if not isinstance(snapshot, DiscoverySnapshot):
            raise OpenRouterDiscoveryError(
                "snapshot must be a DiscoverySnapshot"
            )
        if snapshot.parser_version != self.parser_version:
            raise OpenRouterDiscoveryError("parser schema version is unsupported")
        document = _strict_document(snapshot.raw_bytes)
        fixture_meta = document.get("fixture_metadata")
        if fixture_meta is not None:
            schema = _object("fixture_metadata", fixture_meta).get(
                "response_schema"
            )
            if schema != self.parser_version:
                raise OpenRouterDiscoveryError(
                    "fixture response schema is unsupported"
                )
        raw_models = document.get("data")
        if not isinstance(raw_models, list):
            raise OpenRouterDiscoveryError("OpenRouter data must be an array")

        seen_ids: set[str] = set()
        observations: list[ModelObservation] = []
        for index, raw_model in enumerate(raw_models):
            record = _object(f"data[{index}]", raw_model)
            model_id = _text(f"data[{index}].id", record.get("id"))
            if model_id in seen_ids:
                raise OpenRouterDiscoveryError(
                    f"duplicate model id: {model_id}"
                )
            seen_ids.add(model_id)
            canonical_slug = _text(
                f"data[{index}].canonical_slug",
                record.get("canonical_slug"),
            )
            clean_id = model_id.lstrip("~")
            if "/" not in clean_id:
                raise OpenRouterDiscoveryError(
                    f"data[{index}].id must contain vendor/model"
                )
            vendor = clean_id.split("/", 1)[0]
            alias_target = record.get("alias_target")
            is_alias = (
                model_id.startswith("~")
                or alias_target is not None
                or canonical_slug == model_id
                and "latest" in model_id.lower()
            )
            if alias_target is not None:
                alias_target = dict(_object("alias_target", alias_target))
            identity_status = (
                IdentityStatus.UNRESOLVED
                if is_alias
                else IdentityStatus.CLAIMED
            )
            concrete_revision = None if is_alias else canonical_slug
            subject = ModelSubject.create(
                vendor,
                model_id,
                concrete_revision,
                identity_status,
                snapshot.snapshot_id,
            )

            supported_parameters = _string_array(
                "supported_parameters",
                record.get("supported_parameters"),
            )
            defaults = record.get("default_parameters")
            if defaults is None:
                defaults = {}
            defaults = dict(_object("default_parameters", defaults))
            try:
                defaults_digest = hashlib.sha256(
                    canonical_json_bytes(defaults)
                ).hexdigest()
            except ValueError as exc:
                raise OpenRouterDiscoveryError(
                    "default_parameters must contain finite JSON"
                ) from exc
            parameter_profile_digest = sha256_id(
                "openrouter_parameter_claim_v1",
                {
                    "supported_parameters": list(supported_parameters),
                    "default_parameters_digest": defaults_digest,
                },
            )
            privacy_claim = {
                "source_snapshot_id": snapshot.snapshot_id,
                "privacy_status": "unknown_conservative",
                "execution_authority": "none_discovery_only",
            }
            data_policy_snapshot_id = sha256_id(
                "openrouter_data_policy_claim_v1",
                privacy_claim,
            )
            route = ExecutionRouteIdentity.create(
                subject.subject_id,
                "openrouter_discovery_claim",
                "https://openrouter.ai/api/v1",
                model_id,
                parameter_profile_digest,
                "unbound-v1",
                data_policy_snapshot_id,
            )

            benchmarks = record.get("benchmarks")
            benchmark_digest = None
            market_signal_kind = None
            if benchmarks is not None:
                try:
                    benchmark_digest = hashlib.sha256(
                        canonical_json_bytes(
                            dict(_object("benchmarks", benchmarks))
                        )
                    ).hexdigest()
                except ValueError as exc:
                    raise OpenRouterDiscoveryError(
                        "benchmarks must contain finite JSON"
                    ) from exc
                market_signal_kind = "external_benchmark_claim"

            payload: dict[str, object] = {
                "source_catalog": "openrouter",
                "canonical_slug_digest": hashlib.sha256(
                    canonical_slug.encode("utf-8")
                ).hexdigest(),
                "identity_status": identity_status.value,
                "created": _non_negative_integer(
                    "created",
                    record.get("created"),
                ),
                "context_length": _non_negative_integer(
                    "context_length",
                    record.get("context_length"),
                ),
                "architecture": _architecture(record.get("architecture")),
                "pricing": _pricing(record.get("pricing")),
                "top_provider": _top_provider(record.get("top_provider")),
                "supported_parameters": list(supported_parameters),
                "default_parameters_digest": defaults_digest,
                "expiration_date": _expiration(
                    record.get("expiration_date")
                ),
                "privacy_status": "unknown_conservative",
                "execution_authority": "none_discovery_only",
            }
            if alias_target is not None:
                payload["alias_target_digest"] = hashlib.sha256(
                    canonical_json_bytes(alias_target)
                ).hexdigest()
            if benchmark_digest is not None:
                payload["benchmark_digest"] = benchmark_digest
            description = record.get("description")
            if description is not None:
                description = _text("description", description, maximum=1024 * 1024)
            observations.append(
                ModelObservation.create(
                    model_subject=subject,
                    execution_route=route,
                    snapshot_id=snapshot.snapshot_id,
                    kind="openrouter_model_catalog",
                    observed_at=snapshot.observed_at,
                    payload=payload,
                    external_description=description,
                    market_signal_kind=market_signal_kind,
                )
            )
        return tuple(observations)


class OpenRouterApiDiscoveryProvider:
    provider_id = "openrouter_api_discovery"

    def __init__(
        self,
        config: DiscoveryProviderConfig,
        *,
        transport: JsonTransport | None = None,
        observed_at: Callable[[], str] = _utc_now,
    ) -> None:
        if not isinstance(config, DiscoveryProviderConfig):
            raise ValueError("config must be a DiscoveryProviderConfig")
        if config.kind != "openrouter_models_api":
            raise ValueError("config kind must be openrouter_models_api")
        if not config.enabled:
            raise ValueError("OpenRouter discovery config is disabled")
        if config.url != PUBLIC_MODELS_URL:
            raise ValueError("OpenRouter discovery URL must be exact")
        self.config = config
        self._transport = transport or UrllibJsonTransport(
            max_response_bytes=config.max_response_bytes
        )
        self._observed_at = observed_at

    def default_query(self) -> DiscoveryQuery:
        return DiscoveryQuery.create(
            SOURCE_ID,
            {
                "method": "GET",
                "url": self.config.url,
                "authentication": "none",
                "response_schema": PARSER_VERSION,
            },
            max_response_bytes=self.config.max_response_bytes,
        )

    def snapshot(self, query: DiscoveryQuery) -> DiscoverySnapshot:
        expected = self.default_query()
        if query != expected:
            raise ValueError("query does not match exact OpenRouter API discovery")
        document = self._transport.get_json(
            self.config.url,
            headers={"Accept": "application/json"},
            timeout_s=30.0,
        )
        raw_bytes = canonical_json_bytes(dict(document))
        return DiscoverySnapshot.from_bytes(
            SOURCE_ID,
            self._observed_at(),
            query,
            raw_bytes,
            PARSER_VERSION,
        )


class OpenRouterWebDiscoveryProvider:
    provider_id = "openrouter_operator_snapshot"

    def __init__(
        self,
        raw_bytes: bytes,
        *,
        observed_at: str,
        expected_sha256: str,
    ) -> None:
        if not isinstance(raw_bytes, bytes):
            raise ValueError("raw_bytes must be bytes")
        if len(raw_bytes) > 64 * 1024 * 1024:
            raise OpenRouterDiscoveryError("operator snapshot is too large")
        actual = hashlib.sha256(raw_bytes).hexdigest()
        if expected_sha256 != actual:
            raise OpenRouterDiscoveryError("operator snapshot hash mismatch")
        self._raw_bytes = raw_bytes
        self._observed_at = observed_at
        self._sha256 = actual

    def default_query(self) -> DiscoveryQuery:
        return DiscoveryQuery.create(
            SOURCE_ID,
            {
                "method": "operator_supplied_snapshot",
                "source_url": PUBLIC_MODELS_URL,
                "expected_sha256": self._sha256,
                "response_schema": PARSER_VERSION,
            },
            max_response_bytes=max(1, len(self._raw_bytes)),
        )

    def snapshot(self, query: DiscoveryQuery) -> DiscoverySnapshot:
        if query != self.default_query():
            raise ValueError("query does not match operator snapshot")
        return DiscoverySnapshot.from_bytes(
            SOURCE_ID,
            self._observed_at,
            query,
            self._raw_bytes,
            PARSER_VERSION,
        )


__all__ = [
    "OpenRouterApiDiscoveryProvider",
    "OpenRouterDiscoveryError",
    "OpenRouterModelNormalizer",
    "OpenRouterWebDiscoveryProvider",
    "PARSER_VERSION",
    "PUBLIC_MODELS_URL",
    "SOURCE_ID",
]
