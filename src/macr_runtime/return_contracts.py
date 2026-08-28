from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .contracts import ReturnFormat, TaskContract
from .execution import ReturnContractState


BOUNDED_WORKER_INSTRUCTION = (
    "You are a bounded MACR worker. Treat the supplied TaskContract as authoritative. "
    "Return a candidate answer with concise evidence and warnings. Do not claim that "
    "generation is verification or acceptance."
)
_BOUNDARY_INSTRUCTION = (
    "You are a bounded MACR worker. Treat the supplied TaskContract as authoritative. "
    "Return only a candidate; generation is not verification or acceptance."
)
_LANGUAGE_LABELS = {
    "csharp": "C#",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
}
_PLAIN_SOURCE_WRAPPER = re.compile(
    r"""(?ix)\A\s*(?:
        here(?:['’]s|\s+is)\b
        | below\s+is\b
        | the\s+following\b
        | (?:plain\s+)?(?:source|code)\s*:\s*(?:\r?\n|\Z)
    )"""
)


class _DuplicateJsonKey(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


@dataclass(frozen=True)
class ReturnContractValidation:
    state: ReturnContractState
    reason_code: str


def compile_worker_instruction(task: TaskContract) -> str:
    if not isinstance(task, TaskContract):
        raise ValueError("task must be a TaskContract")
    contract = task.return_contract
    if (
        contract.format is ReturnFormat.FREE_TEXT
        and contract.summary
        and contract.evidence
        and not contract.patch
    ):
        return BOUNDED_WORKER_INSTRUCTION
    directives: list[str] = [_BOUNDARY_INSTRUCTION]
    if contract.format is ReturnFormat.EXACT_TEXT:
        encoded = json.dumps(contract.exact_text, ensure_ascii=False)
        directives.append(
            "Return exactly the UTF-8 text represented by this JSON string: "
            f"{encoded}. Do not add a newline, quotation marks, summary, evidence, "
            "warning, or formatting."
        )
    elif contract.format is ReturnFormat.PLAIN_SOURCE:
        language = contract.language or "source"
        label = _LANGUAGE_LABELS.get(language, language)
        directives.append(
            f"Return only plain {label} source with no Markdown fence, prose, "
            "summary, evidence, or warnings."
        )
    elif contract.format is ReturnFormat.JSON_OBJECT:
        directives.append(
            "Return exactly one JSON object with no Markdown fence or surrounding prose."
        )
    else:
        if contract.summary:
            directives.append("Include a concise summary.")
        else:
            directives.append("Do not add a summary.")
        if contract.evidence:
            directives.append("Include concise evidence and warnings.")
        else:
            directives.append("Do not add evidence or warnings.")
        if contract.patch:
            directives.append("Include the explicitly authorized patch result.")
    return " ".join(directives)


def _has_plain_source_wrapper(task: TaskContract, answer: str) -> bool:
    if _PLAIN_SOURCE_WRAPPER.search(answer):
        return True
    language = task.return_contract.language
    if language is None:
        return False
    labels = {language, _LANGUAGE_LABELS.get(language, language)}
    for label in labels:
        pattern = re.compile(
            rf"\A\s*{re.escape(label)}"
            r"(?:\s+(?:source|code))?\s*:\s*(?:\r?\n|\Z)",
            flags=re.IGNORECASE,
        )
        if pattern.search(answer):
            return True
    return False


def validate_return_contract(
    task: TaskContract,
    answer: str,
) -> ReturnContractValidation:
    if not isinstance(task, TaskContract):
        raise ValueError("task must be a TaskContract")
    if not isinstance(answer, str) or not answer.strip():
        return ReturnContractValidation(
            ReturnContractState.INVALID,
            "answer_blank",
        )
    contract = task.return_contract
    if contract.format is ReturnFormat.EXACT_TEXT:
        return ReturnContractValidation(
            (
                ReturnContractState.VALID
                if answer == contract.exact_text
                else ReturnContractState.INVALID
            ),
            "exact_text_match" if answer == contract.exact_text else "exact_text_mismatch",
        )
    if contract.format is ReturnFormat.PLAIN_SOURCE:
        prohibited = (
            re.search(
                r"```|^\s*(?:evidence|warnings?)\s*:",
                answer,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            or _has_plain_source_wrapper(task, answer)
        )
        return ReturnContractValidation(
            (
                ReturnContractState.INVALID
                if prohibited
                else ReturnContractState.VALID
            ),
            (
                "plain_source_has_fence_or_prose"
                if prohibited
                else "plain_source_valid"
            ),
        )
    if contract.format is ReturnFormat.JSON_OBJECT:
        try:
            value = json.loads(answer, object_pairs_hook=_strict_object)
        except _DuplicateJsonKey:
            return ReturnContractValidation(
                ReturnContractState.INVALID,
                "json_duplicate_key",
            )
        except json.JSONDecodeError:
            return ReturnContractValidation(
                ReturnContractState.INVALID,
                "json_invalid",
            )
        if not isinstance(value, dict):
            return ReturnContractValidation(
                ReturnContractState.INVALID,
                "json_not_object",
            )
        return ReturnContractValidation(
            ReturnContractState.VALID,
            "json_object_valid",
        )
    return ReturnContractValidation(
        ReturnContractState.VALID,
        "free_text_nonblank",
    )
