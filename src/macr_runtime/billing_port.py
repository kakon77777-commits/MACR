from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from .canonical import aware_iso8601, canonical_json_bytes, sha256_id
from .errors import AccountingConflict, MacrError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_EXPECTED_KEYS = frozenset(
    {
        "provider_id",
        "provider_account_id",
        "funding_source_id",
        "invoice_item_id",
        "plan_digest",
        "run_id",
        "amount",
        "currency",
        "tax",
        "credit",
        "payment_status",
        "source_digest",
        "observed_at",
        "metadata",
    }
)
_ALLOWED_METADATA_KEYS = frozenset(
    {"billing_period_id", "statement_id", "source_kind"}
)
_FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "api_key",
        "authorization",
        "body",
        "content",
        "credential",
        "invoice_body",
        "path",
        "paths",
        "private_key",
        "prompt",
        "raw_response",
        "remote_response",
    }
)


class BillingPortError(MacrError):
    """Bill metadata violates the content-free reconciliation boundary."""


def _normalize_key(key: str) -> str:
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key.strip())
    return re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        "_",
        separated,
    ).lower().replace("-", "_")


def _reject_forbidden(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise BillingPortError("bill metadata keys must be strings")
            normalized = _normalize_key(key)
            if (
                normalized in _FORBIDDEN_KEYS
                or normalized.endswith(("_body", "_content", "_path", "_paths"))
            ):
                raise BillingPortError(f"forbidden bill metadata key: {key}")
            _reject_forbidden(child)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden(child)


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise BillingPortError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise BillingPortError(f"{name} must be a bounded identifier")
    return value


def _uuid(name: str, value: object) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise BillingPortError(f"{name} must be a canonical UUID") from exc
    if str(parsed) != str(value).lower():
        raise BillingPortError(f"{name} must be a canonical UUID")
    return str(parsed)


def _number(name: str, value: object, *, signed: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BillingPortError(f"{name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or (not signed and normalized < 0):
        raise BillingPortError(f"{name} must be a finite number")
    return normalized


@dataclass(frozen=True)
class BillObservation:
    observation_id: str
    provider_id: str
    provider_account_id: str
    funding_source_id: str
    invoice_item_id: str
    plan_digest: str | None
    run_id: str | None
    amount: float
    currency: str
    tax: float | None
    credit: float | None
    payment_status: str
    source_digest: str
    metadata_digest: str
    observed_at: str

    def __post_init__(self) -> None:
        provider_id = _identifier("provider_id", self.provider_id)
        provider_account_id = _uuid(
            "provider_account_id",
            self.provider_account_id,
        )
        funding_source_id = _digest(
            "funding_source_id",
            self.funding_source_id,
        )
        invoice_item_id = _digest("invoice_item_id", self.invoice_item_id)
        plan_digest = (
            _digest("plan_digest", self.plan_digest)
            if self.plan_digest is not None
            else None
        )
        run_id = _uuid("run_id", self.run_id) if self.run_id is not None else None
        amount = _number("amount", self.amount, signed=True)
        currency = _identifier("currency", self.currency).upper()
        tax = (
            _number("tax", self.tax, signed=False)
            if self.tax is not None
            else None
        )
        credit = (
            _number("credit", self.credit, signed=False)
            if self.credit is not None
            else None
        )
        payment_status = _identifier(
            "payment_status",
            self.payment_status,
        )
        source_digest = _digest("source_digest", self.source_digest)
        metadata_digest = _digest("metadata_digest", self.metadata_digest)
        observed_at = aware_iso8601("observed_at", self.observed_at)
        canonical = {
            "provider_id": provider_id,
            "provider_account_id": provider_account_id,
            "funding_source_id": funding_source_id,
            "invoice_item_id": invoice_item_id,
            "plan_digest": plan_digest,
            "run_id": run_id,
            "amount": amount,
            "currency": currency,
            "tax": tax,
            "credit": credit,
            "payment_status": payment_status,
            "source_digest": source_digest,
            "metadata_digest": metadata_digest,
            "observed_at": observed_at,
        }
        if self.observation_id != sha256_id("bill_observation_v1", canonical):
            raise BillingPortError(
                "observation_id does not match canonical bill observation"
            )
        for field_name, value in canonical.items():
            object.__setattr__(self, field_name, value)

    def to_public_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "provider_id": self.provider_id,
            "provider_account_id": self.provider_account_id,
            "funding_source_id": self.funding_source_id,
            "invoice_item_id": self.invoice_item_id,
            "plan_digest": self.plan_digest,
            "run_id": self.run_id,
            "amount": self.amount,
            "currency": self.currency,
            "tax": self.tax,
            "credit": self.credit,
            "payment_status": self.payment_status,
            "source_digest": self.source_digest,
            "metadata_digest": self.metadata_digest,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class BillInspectionReport:
    observation: BillObservation
    blind_spots: tuple[str, ...]
    wrote: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "observation": self.observation.to_public_dict(),
            "blind_spots": list(self.blind_spots),
            "wrote": self.wrote,
        }


class BillingReconciliationPort:
    def __init__(self, store: object) -> None:
        from .accounting import AccountingStore

        if not isinstance(store, AccountingStore):
            raise ValueError("store must be an AccountingStore")
        self.store = store

    def inspect(self, value: Mapping[str, Any]) -> BillInspectionReport:
        if not isinstance(value, Mapping):
            raise BillingPortError("bill observation must be an object")
        _reject_forbidden(value)
        missing = sorted(_EXPECTED_KEYS - set(value))
        unknown = sorted(set(value) - _EXPECTED_KEYS)
        if missing:
            raise BillingPortError(f"bill observation missing key: {missing[0]}")
        if unknown:
            raise BillingPortError(f"bill observation unknown key: {unknown[0]}")
        metadata = value.get("metadata")
        if not isinstance(metadata, Mapping):
            raise BillingPortError("metadata must be an object")
        unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_KEYS)
        if unknown_metadata:
            raise BillingPortError(
                f"metadata key is not allowed: {unknown_metadata[0]}"
            )
        normalized_metadata: dict[str, str] = {}
        for key, item in metadata.items():
            if key.endswith("_id"):
                normalized_metadata[key] = _digest(key, item)
            else:
                normalized_metadata[key] = _identifier(key, item)
        metadata_digest = hashlib.sha256(
            canonical_json_bytes(normalized_metadata)
        ).hexdigest()
        plan = value.get("plan_digest")
        if plan is not None:
            plan = _digest("plan_digest", plan)
        run = value.get("run_id")
        if run is not None:
            run = _uuid("run_id", run)
        tax = value.get("tax")
        if tax is not None:
            tax = _number("tax", tax, signed=False)
        credit = value.get("credit")
        if credit is not None:
            credit = _number("credit", credit, signed=False)
        canonical = {
            "provider_id": _identifier("provider_id", value.get("provider_id")),
            "provider_account_id": _uuid(
                "provider_account_id",
                value.get("provider_account_id"),
            ),
            "funding_source_id": _digest(
                "funding_source_id",
                value.get("funding_source_id"),
            ),
            "invoice_item_id": _digest(
                "invoice_item_id",
                value.get("invoice_item_id"),
            ),
            "plan_digest": plan,
            "run_id": run,
            "amount": _number("amount", value.get("amount"), signed=True),
            "currency": _identifier("currency", value.get("currency")).upper(),
            "tax": tax,
            "credit": credit,
            "payment_status": _identifier(
                "payment_status",
                value.get("payment_status"),
            ),
            "source_digest": _digest(
                "source_digest",
                value.get("source_digest"),
            ),
            "metadata_digest": metadata_digest,
            "observed_at": aware_iso8601(
                "observed_at",
                value.get("observed_at"),
            ),
        }
        observation_id = sha256_id("bill_observation_v1", canonical)
        return BillInspectionReport(
            observation=BillObservation(
                observation_id=observation_id,
                **canonical,
            ),
            blind_spots=(
                "invoice_body_not_ingested",
                "payment_not_performed",
                "accounting_acceptance_not_inferred",
            ),
        )

    def record(self, observation: BillObservation) -> bool:
        if not isinstance(observation, BillObservation):
            raise ValueError("observation must be a BillObservation")
        try:
            return self.store.record_bill_observation(observation)
        except AccountingConflict as exc:
            detail = str(exc).lower()
            if "account" in detail:
                raise BillingPortError("bill observation account is unavailable") from exc
            raise BillingPortError("bill observation conflict") from exc


__all__ = [
    "BillInspectionReport",
    "BillObservation",
    "BillingPortError",
    "BillingReconciliationPort",
]
