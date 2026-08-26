"""Migration-first Multi-AI Collaboration Runtime."""

from .contracts import (
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

__version__ = "0.3.0"
