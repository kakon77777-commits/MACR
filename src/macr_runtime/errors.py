import re


_SAFE_DIAGNOSTIC_IDENTIFIER = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)


class MacrError(Exception):
    """Base exception for expected MACR failures."""


class ConfigurationError(MacrError):
    """Configuration is invalid or incomplete."""


class StoragePolicyError(MacrError):
    """A persistent path violates the configured storage policy."""


class ProviderUnavailableError(MacrError):
    """The selected provider cannot currently be invoked."""


class ProviderPolicyError(MacrError):
    """Provider use is denied by an explicit policy gate."""


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

    def safe_diagnostic(self) -> dict[str, object]:
        return dict(self._diagnostic)


class ProviderProtocolError(MacrError):
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
