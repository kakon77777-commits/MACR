"""Migration-first Multi-AI Collaboration Runtime."""

from .contracts import (
    DelegationClass,
    PrivacyLevel,
    ProviderResult,
    ResultStatus,
    TaskConstraints,
    TaskContract,
    VerificationSpec,
    WorkspaceSpec,
)
from .runtime import MacrRuntime
from .storage import StorageLayout

__all__ = [
    "DelegationClass",
    "MacrRuntime",
    "PrivacyLevel",
    "ProviderResult",
    "ResultStatus",
    "StorageLayout",
    "TaskConstraints",
    "TaskContract",
    "VerificationSpec",
    "WorkspaceSpec",
]

__version__ = "0.4.0"
