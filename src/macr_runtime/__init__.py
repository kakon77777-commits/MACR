"""Migration-first Multi-AI Collaboration Runtime.

Root exports are lazy so importing a bounded subpackage does not initialize
provider runtimes or optional media dependencies.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_MODULE_EXPORTS = {
    "contracts": (
        "DelegationClass", "EolNormalization", "EolScope", "ImportMode",
        "PrivacyLevel", "ProviderResult", "ReturnContract", "ReturnFormat",
        "RequiredImport", "ResultStatus", "TaskConstraints", "TaskContract",
        "TaskPolicyClauses", "VerificationSpec", "WorkspaceSpec",
    ),
    "runtime": ("MacrRuntime", "RuntimeServices"),
    "storage": ("StorageLayout",),
    "canonical": ("aware_iso8601", "canonical_json_bytes", "sha256_id"),
    "model_identity": (
        "ExecutionRouteIdentity", "IdentityStatus", "ModelSubject",
        "QualificationKey", "RoleDefinition",
    ),
    "planning_contracts": (
        "ApprovalMode", "BudgetMode", "ContextCapsule", "ContextSourceItem",
        "FallbackMode", "OperatorPolicyProfile",
    ),
    "observatory_db": ("ObservatoryDatabase",),
    "observatory": ("IngestReport", "ModelObservatory"),
    "model_passport": ("ModelPassport", "ModelPassportProjector"),
    "probe_registry": ("ProbeClass", "ProbeDefinition", "ProbeRegistry"),
    "qualification": (
        "QualificationDecision", "QualificationEngine", "QualificationPolicy",
        "QualificationState", "wilson_lower_bound",
    ),
    "evidence_import": ("EvidenceImporter", "ImportReport"),
    "coordination": (
        "BudgetEvaluation", "CoordinationPlan", "EligibleCandidate",
        "ExcludedCandidate", "FallbackRule", "ModelBinding",
        "PlanExecutionMode", "RoleSlot", "TopologyId",
    ),
    "verification_graph": ("VerifierGraph", "VerifierNode"),
    "planner": (
        "DynamicCoordinationPlanner", "EligibilityDecision", "ExclusionReason",
        "PlanningCandidate", "PlanningError", "PlanningInput", "PlanningState",
    ),
    "route_resolution": (
        "ExecutionProviderResolver", "ExecutionRouteProposal",
        "ExecutionRouteSnapshot", "RouteResolutionPolicy",
    ),
    "plan_runtime": ("PlanExecutionResult", "PlanRuntime", "VerificationReport"),
    "model_token_store": ("ModelTokenPolicyStore",),
    "token_policy": (
        "ModelTokenOverride", "ModelTokenPolicy", "ModelTokenPolicyResolver",
        "builtin_model_token_policies", "t1_glm_live_policy",
    ),
    "scheduler": ("PlanQueue", "QueueMemberState"),
    "t1_dispatcher": ("T1DispatchError", "T1DispatchResult", "T1Dispatcher"),
    "t1_manifest": (
        "T1AuthorityBundle", "T1ExecutionManifest", "T1ExecutionMember",
        "load_t1_manifest",
    ),
    "accounting": ("CostClass",),
    "billing_port": ("BillObservation", "BillingReconciliationPort"),
    "direct_contracts": (
        "DirectConversationSpec", "DirectMessage", "DirectProviderId",
        "DirectRunSettings", "DirectTurnResult", "canonical_policy_snapshot",
    ),
    "execution": (
        "AcceptanceState", "AuthorizationReference", "CaptureState",
        "DispatchContext", "DispatchOrigin", "InteractionPlane",
        "MaterializationState", "ProviderExecution", "ProviderState",
        "ProviderUsage", "RawProviderObservation", "ReturnContractState",
        "VerificationState",
    ),
}

_LAZY_EXPORTS = {
    name: (module_name, name)
    for module_name, names in _MODULE_EXPORTS.items()
    for name in names
}

__all__ = [
    "ApprovalMode", "BudgetMode", "BillObservation",
    "BillingReconciliationPort", "BudgetEvaluation", "ContextCapsule",
    "ContextSourceItem", "CostClass", "CoordinationPlan", "DelegationClass",
    "DirectConversationSpec", "DirectMessage", "DirectProviderId",
    "DirectRunSettings", "DirectTurnResult", "DynamicCoordinationPlanner",
    "EolNormalization", "EolScope", "ExecutionRouteIdentity",
    "ExecutionProviderResolver", "ExecutionRouteProposal",
    "ExecutionRouteSnapshot", "EvidenceImporter", "EligibilityDecision",
    "EligibleCandidate", "ExcludedCandidate", "ExclusionReason", "FallbackMode",
    "FallbackRule", "IdentityStatus", "IngestReport", "ImportMode",
    "AcceptanceState", "AuthorizationReference", "CaptureState",
    "DispatchContext", "DispatchOrigin", "InteractionPlane", "ImportReport",
    "MacrRuntime", "ModelSubject", "ModelTokenOverride", "ModelTokenPolicy",
    "ModelTokenPolicyResolver", "ModelTokenPolicyStore", "ModelBinding",
    "ModelObservatory", "ModelPassport", "ModelPassportProjector",
    "OperatorPolicyProfile", "PlanExecutionMode", "PlanExecutionResult",
    "PlanRuntime", "PlanQueue", "PlanningCandidate", "PlanningError",
    "PlanningInput", "PlanningState", "ObservatoryDatabase",
    "MaterializationState", "PrivacyLevel", "ProviderExecution",
    "ProviderResult", "ProbeClass", "ProbeDefinition", "ProbeRegistry",
    "QualificationKey", "QualificationDecision", "QualificationEngine",
    "QualificationPolicy", "QualificationState", "QueueMemberState",
    "ProviderState", "ProviderUsage", "RawProviderObservation", "ResultStatus",
    "ReturnContract", "ReturnFormat", "RoleDefinition", "RoleSlot",
    "RouteResolutionPolicy", "RequiredImport", "ReturnContractState",
    "RuntimeServices", "StorageLayout", "TaskConstraints", "TaskContract",
    "TaskPolicyClauses", "T1AuthorityBundle", "T1DispatchError",
    "T1DispatchResult", "T1Dispatcher", "T1ExecutionManifest",
    "T1ExecutionMember", "TopologyId", "VerifierGraph", "VerifierNode",
    "VerificationReport", "VerificationSpec", "VerificationState",
    "WorkspaceSpec", "aware_iso8601", "canonical_json_bytes",
    "canonical_policy_snapshot", "builtin_model_token_policies",
    "load_t1_manifest", "sha256_id", "t1_glm_live_policy",
    "wilson_lower_bound",
]

if set(__all__) != set(_LAZY_EXPORTS):  # pragma: no cover - import invariant
    raise RuntimeError("MACR lazy root export map is incomplete")


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(f".{module_name}", __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})


__version__ = "0.7.0a0"
