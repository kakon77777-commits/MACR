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


class ProviderProtocolError(MacrError):
    """A provider response does not satisfy the adapter contract."""


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
