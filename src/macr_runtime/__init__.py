"""Migration-first Multi-AI Collaboration Runtime."""

from .contracts import (
    DelegationClass,
    PrivacyLevel,
    ProviderResult,
    ReturnContract,
    ReturnFormat,
    ResultStatus,
    TaskConstraints,
    TaskContract,
    VerificationSpec,
    WorkspaceSpec,
)
from .runtime import MacrRuntime
from .storage import StorageLayout
from .execution import (
    AcceptanceState,
    AuthorizationReference,
    CaptureState,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
    MaterializationState,
    ProviderExecution,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
    ReturnContractState,
    VerificationState,
)

__all__ = [
    "DelegationClass",
    "AcceptanceState",
    "AuthorizationReference",
    "CaptureState",
    "DispatchContext",
    "DispatchOrigin",
    "InteractionPlane",
    "MacrRuntime",
    "MaterializationState",
    "PrivacyLevel",
    "ProviderExecution",
    "ProviderResult",
    "ProviderState",
    "ProviderUsage",
    "RawProviderObservation",
    "ResultStatus",
    "ReturnContract",
    "ReturnFormat",
    "ReturnContractState",
    "StorageLayout",
    "TaskConstraints",
    "TaskContract",
    "VerificationSpec",
    "VerificationState",
    "WorkspaceSpec",
]

__version__ = "0.4.0"
