import re


_SAFE_DIAGNOSTIC_IDENTIFIER = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)


class MacrError(Exception):
    """Base exception for expected MACR failures."""


class _ProviderTransportDiagnostic:
    def __init__(
        self,
        message: str,
        *,
        network_attempted: bool | None = None,
        response_received: bool | None = None,
        provider_http_status: int | None = None,
        provider_error_code: str | int | None = None,
        transport_stage: str | None = None,
    ) -> None:
        super().__init__(message)
        for name, value in (
            ("network_attempted", network_attempted),
            ("response_received", response_received),
        ):
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean or None")
        if response_received is True and network_attempted is not True:
            raise ValueError("response_received requires network_attempted")
        if (
            provider_http_status is not None
            and (
                isinstance(provider_http_status, bool)
                or not isinstance(provider_http_status, int)
                or not 100 <= provider_http_status <= 599
            )
        ):
            raise ValueError("provider_http_status must be an HTTP status or None")
        if provider_http_status is not None and response_received is not True:
            raise ValueError("provider_http_status requires response_received")
        if isinstance(provider_error_code, bool):
            raise ValueError("provider_error_code must be bounded or None")
        normalized_error_code = (
            str(provider_error_code) if provider_error_code is not None else None
        )
        if (
            normalized_error_code is not None
            and not _SAFE_DIAGNOSTIC_IDENTIFIER.fullmatch(normalized_error_code)
        ):
            raise ValueError("provider_error_code must be bounded or None")
        if normalized_error_code is not None and response_received is not True:
            raise ValueError("provider_error_code requires response_received")
        if (
            transport_stage is not None
            and not _SAFE_DIAGNOSTIC_IDENTIFIER.fullmatch(transport_stage)
        ):
            raise ValueError("transport_stage must be bounded or None")
        self._transport_diagnostic = {
            "network_attempted": network_attempted,
            "response_received": response_received,
            "provider_http_status": provider_http_status,
            "provider_error_code": normalized_error_code,
            "transport_stage": transport_stage,
        }

    def safe_diagnostic(self) -> dict[str, object]:
        return dict(self._transport_diagnostic)


class ConfigurationError(MacrError):
    """Configuration is invalid or incomplete."""


class StoragePolicyError(MacrError):
    """A persistent path violates the configured storage policy."""


class ProviderUnavailableError(_ProviderTransportDiagnostic, MacrError):
    """The selected provider cannot currently be invoked."""


class ProviderPolicyError(MacrError):
    """Provider use is denied by an explicit policy gate."""


class ProviderPreNetworkError(ProviderPolicyError):
    """A known local provider prerequisite failed before network use."""

    def safe_diagnostic(self) -> dict[str, object]:
        return {
            "network_attempted": False,
            "response_received": False,
            "provider_http_status": None,
            "provider_error_code": None,
            "transport_stage": "pre_network",
        }


class ProviderTaskTypeError(ProviderPolicyError):
    """A task type is outside the active provider capability tier."""

    def __init__(
        self,
        *,
        requested_task_type: str,
        allowed_task_types: tuple[str, ...],
        provider_id: str,
        model_id: str,
        tier_id: str,
        tier_revision: int,
        tier_binding_digest: str,
    ) -> None:
        super().__init__("provider task type is not allowed by the active tier")
        self._diagnostic = {
            "code": "task_type_not_allowed",
            "requested_task_type": (
                requested_task_type
                if _SAFE_DIAGNOSTIC_IDENTIFIER.fullmatch(requested_task_type)
                else "unavailable"
            ),
            "provider_id": provider_id,
            "model_id": model_id,
            "tier_id": tier_id,
            "tier_revision": tier_revision,
            "tier_binding_digest": tier_binding_digest,
            "allowed_task_types": list(allowed_task_types),
        }

    def safe_diagnostic(self) -> dict[str, object]:
        return {
            **self._diagnostic,
            "allowed_task_types": list(self._diagnostic["allowed_task_types"]),
        }


class ProviderOutputBudgetTooSmallError(ProviderPolicyError):
    """A cloud task requests less output than the model quality floor."""

    def __init__(
        self,
        *,
        requested_max_output_tokens: int,
        minimum_max_output_tokens: int,
        provider_id: str,
        model_id: str,
        model_token_policy_digest: str,
        policy_source: str,
        recommended_max_output_tokens: int | None = None,
        output_budget_profile: str | None = None,
    ) -> None:
        super().__init__("cloud task output is below the model quality floor")
        self._diagnostic = {
            "code": "output_budget_below_quality_floor",
            "requested_max_output_tokens": requested_max_output_tokens,
            "minimum_max_output_tokens": minimum_max_output_tokens,
            "provider_id": provider_id,
            "model_id": model_id,
            "model_token_policy_digest": model_token_policy_digest,
            "policy_source": policy_source,
        }
        if recommended_max_output_tokens is not None:
            if (
                isinstance(recommended_max_output_tokens, bool)
                or not isinstance(recommended_max_output_tokens, int)
                or recommended_max_output_tokens < minimum_max_output_tokens
            ):
                raise ValueError(
                    "recommended_max_output_tokens must cover the minimum"
                )
            self._diagnostic["recommended_max_output_tokens"] = (
                recommended_max_output_tokens
            )
        if output_budget_profile is not None:
            if not _SAFE_DIAGNOSTIC_IDENTIFIER.fullmatch(output_budget_profile):
                raise ValueError("output_budget_profile must be a safe identifier")
            self._diagnostic["output_budget_profile"] = output_budget_profile

    def safe_diagnostic(self) -> dict[str, object]:
        return dict(self._diagnostic)


class ProviderProtocolError(_ProviderTransportDiagnostic, MacrError):
    """A provider response does not satisfy the adapter contract."""


class ProviderReasoningBudgetExhaustedError(ProviderProtocolError):
    """Reasoning consumed the provider output budget before visible content."""


class EventStoreConflict(MacrError):
    """A run or event would violate an append-only event invariant."""


class LegacyLedgerError(MacrError):
    """Legacy evidence cannot be imported as a complete source."""


class DispatchAuthorizationError(MacrError):
    """No current exact authority permits the requested dispatch."""


class DispatchLeaseError(MacrError):
    """The requested dispatch resource is held by another fenced run."""


class CandidateConflict(MacrError):
    """Candidate bytes or provenance conflict with a create-once capture."""


class TaskContradictionError(MacrError):
    """Structured task clauses contain an exact deterministic conflict."""


class AccountingConflict(MacrError):
    """An accounting write conflicts with append-only financial evidence."""


class DirectStoreConflict(MacrError):
    """Direct settings, conversation, or message state violates an invariant."""


class LegacyDirectTokenPolicyIncompatibleError(MacrError):
    """A cloud Direct conversation lacks the current token-policy contract."""


class ObservatoryConflict(MacrError):
    """An observatory record or private snapshot conflicts with append-only state."""


class CoordinatorPolicyError(MacrError):
    """A coordinator proposal exceeds its host-defined planning constraints."""


class LegacyPreTierIncompatibleError(MacrError):
    """Historical pre-tier authority/evidence cannot satisfy a new dispatch."""


class LegacyOutputPolicyIncompatibleError(MacrError):
    """Historical output-policy evidence cannot satisfy a current dispatch."""


class LegacyFixedWorkerTopologyIncompatibleError(MacrError):
    """Historical fixed-worker T1 evidence cannot satisfy dynamic dispatch."""


class ProviderAdmissionError(MacrError):
    """Provider-capacity admission cannot safely proceed."""


class ProviderAdmissionBusyError(ProviderAdmissionError):
    """Provider capacity is temporarily unavailable before dispatch."""


class ProviderAdmissionReconciliationError(ProviderAdmissionError):
    """Ambiguous provider capacity requires explicit reconciliation."""


class ProviderAdmissionConflict(ProviderAdmissionError):
    """Provider admission state or identity violates an invariant."""


class ProviderAdmissionRequiredError(ProviderAdmissionError):
    """A provider transport was reached without a valid one-use permit."""
