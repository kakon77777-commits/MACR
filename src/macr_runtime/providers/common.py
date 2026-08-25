BOUNDED_WORKER_INSTRUCTION = (
    "You are a bounded MACR worker. Treat the supplied TaskContract as authoritative. "
    "Return a candidate answer with concise evidence and warnings. Do not claim that "
    "generation is verification or acceptance."
)


def bounded_worker_instruction(goal: str) -> str:
    if goal.strip().lower().startswith("return exactly:"):
        return (
            f"{BOUNDED_WORKER_INSTRUCTION} "
            "The TaskContract goal requires exact output. Return only the exact "
            "requested text, with no summary, evidence, warning, quotation marks, "
            "or formatting."
        )
    return BOUNDED_WORKER_INSTRUCTION
