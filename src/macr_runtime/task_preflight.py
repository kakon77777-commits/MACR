from __future__ import annotations

from .contracts import EolNormalization, EolScope, ImportMode, TaskContract
from .errors import TaskContradictionError


def validate_task_consistency(task: TaskContract) -> tuple[()]:
    if not isinstance(task, TaskContract):
        raise ValueError("task must be a TaskContract")
    clauses = task.policy_clauses
    if clauses.import_mode is ImportMode.NONE and clauses.required_imports:
        raise TaskContradictionError("imports_none_but_required")
    if clauses.import_mode is ImportMode.TYPE_ONLY and any(
        item.kind == ImportMode.RUNTIME.value
        for item in clauses.required_imports
    ):
        raise TaskContradictionError(
            "type_only_mode_but_runtime_required"
        )
    if (
        clauses.eol_scope is EolScope.OUT_OF_SCOPE
        and clauses.eol_normalization is not EolNormalization.NONE
    ):
        raise TaskContradictionError(
            "eol_out_of_scope_but_normalized"
        )
    return ()
