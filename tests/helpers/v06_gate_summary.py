from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macr_runtime.accounting import AccountingStore
from macr_runtime import __version__
from macr_runtime.canonical import canonical_json_bytes, sha256_id
from macr_runtime.direct_store import DirectConversationStore
from macr_runtime.differential import DifferentialProbePack
from macr_runtime.observatory_db import ObservatoryDatabase
from macr_runtime.planner import DynamicCoordinationPlanner
from macr_runtime.runtime_db import RuntimeDatabase
from macr_runtime.model_token_store import ModelTokenPolicyStore
from macr_runtime.token_policy import (
    builtin_model_token_policies,
    t1_glm_live_policy,
)

from tests.support import d_drive_tempdir
from tests.test_planner import (
    DIGESTS,
    candidate,
    capsule,
    planning_input,
    route,
    state,
)


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments],
        text=True,
        encoding="utf-8",
    ).strip()


def _tables(path: Path) -> tuple[str, ...]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(row[0] for row in rows)


def _planner_replay_digest() -> str:
    route_a = route("v06_summary_a", DIGESTS["params-a"])
    route_b = route("v06_summary_b", DIGESTS["params-b"])
    context = capsule((route_a.route_id, route_b.route_id))
    candidate_a = candidate(route_a)
    candidate_b = candidate(route_b)
    planner = DynamicCoordinationPlanner(
        plan_id_factory=lambda: "11111111-1111-4111-8111-111111111111"
    )
    first = planner.plan(
        planning_input(context),
        state((candidate_b, candidate_a), context),
    )
    second = planner.plan(
        planning_input(context),
        state((candidate_a, candidate_b), context),
    )
    if first.plan_digest != second.plan_digest:
        raise AssertionError("planner replay digest changed with candidate order")
    return first.plan_digest


def main() -> int:
    with d_drive_tempdir() as temp:
        runtime_path = temp / "runtime.sqlite3"
        observatory_path = temp / "observatory.sqlite3"
        accounting_path = temp / "accounting.sqlite3"
        RuntimeDatabase(runtime_path)
        ObservatoryDatabase(observatory_path, temp / "snapshots")
        AccountingStore(accounting_path)
        schema_fingerprint = sha256_id(
            "v06_schema_fingerprint_v1",
            {
                "runtime": list(_tables(runtime_path)),
                "observatory": list(_tables(observatory_path)),
                "accounting": list(_tables(accounting_path)),
            },
        )

    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"),
        top_level_dir=str(ROOT),
    )
    pack = DifferentialProbePack.from_dict(
        json.loads(
            (ROOT / "examples" / "probes" / "v06-canonical-probe-pack.json")
            .read_text(encoding="utf-8")
        )
    )
    clean = _git("status", "--porcelain") == ""
    summary = {
        "version": __version__,
        "checkpoint_commit": _git("rev-parse", "HEAD"),
        "checkpoint_tree": _git("rev-parse", "HEAD^{tree}"),
        "git_clean": clean,
        "test_count": suite.countTestCases(),
        "platform_skip_allowance": 2,
        "runtime_schema_version": RuntimeDatabase.SCHEMA_VERSION,
        "observatory_schema_version": ObservatoryDatabase.SCHEMA_VERSION,
        "accounting_schema_version": AccountingStore.SCHEMA_VERSION,
        "direct_conversation_schema_version": DirectConversationStore.SCHEMA_VERSION,
        "model_token_policy_schema_version": ModelTokenPolicyStore.SCHEMA_VERSION,
        "model_token_policy_count": len(builtin_model_token_policies()),
        "model_token_policy_digest": sha256_id(
            "model_token_policy_set_v1",
            [item.to_dict() for item in builtin_model_token_policies()],
        ),
        "t1_live_policy_digest": t1_glm_live_policy().policy_digest,
        "schema_fingerprint": schema_fingerprint,
        "planner_replay_digest": _planner_replay_digest(),
        "canonical_probe_pack_digest": pack.pack_digest,
        "queue_worker_counts": [1, 2, 3, 4, 8],
        "sqlite_bootstrap_processes": 32,
        "t1_complete_path_processes": 3,
        "quiet_census_samples": 5,
        "network_activity": False,
        "provider_generation": False,
    }
    summary["summary_digest"] = hashlib.sha256(
        canonical_json_bytes(summary)
    ).hexdigest()
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
