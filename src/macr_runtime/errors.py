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
