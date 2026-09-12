from __future__ import annotations

import unittest

from macr_runtime.agent.cell import (
    HostedAgentBlobStore,
    HostedBlobRef,
    HostedBlobRole,
    HostedToolRequest,
    HostedWorkspaceTools,
)
from macr_runtime.agent.cell.errors import HostedToolDeniedError
from macr_runtime.errors import StoragePolicyError
from tests.support import d_drive_tempdir


RUN_ONE = "11111111-1111-4111-8111-111111111111"
RUN_TWO = "22222222-2222-4222-8222-222222222222"


class HostedAgentBlobAndToolTests(unittest.TestCase):
    def test_tool_catalog_binds_root_digest_and_traversal_limits(self) -> None:
        with d_drive_tempdir() as temp:
            first_root = temp / "project-a"
            second_root = temp / "project-b"
            (first_root / "docs").mkdir(parents=True)
            (second_root / "docs").mkdir(parents=True)
            first = HostedWorkspaceTools(
                first_root,
                allowed_prefixes=("docs",),
                max_walk_entries=10,
            )
            other_root = HostedWorkspaceTools(
                second_root,
                allowed_prefixes=("docs",),
                max_walk_entries=10,
            )
            other_limit = HostedWorkspaceTools(
                first_root,
                allowed_prefixes=("docs",),
                max_walk_entries=11,
            )

        self.assertNotEqual(
            first.execution_profile_digest,
            other_root.execution_profile_digest,
        )
        self.assertNotEqual(
            first.catalog.catalog_digest,
            other_root.catalog.catalog_digest,
        )
        self.assertNotEqual(
            first.catalog.catalog_digest,
            other_limit.catalog.catalog_digest,
        )

    def test_blob_refs_are_run_scoped_create_once_and_missing_read_is_pure(
        self,
    ) -> None:
        with d_drive_tempdir() as temp:
            store = HostedAgentBlobStore(temp / "agent-cells")
            first = store.write(RUN_ONE, HostedBlobRole.CONTEXT, b"same")
            repeated = store.write(RUN_ONE, HostedBlobRole.CONTEXT, b"same")
            second = store.write(RUN_TWO, HostedBlobRole.CONTEXT, b"same")
            before = tuple(
                sorted(path.relative_to(temp).as_posix() for path in temp.rglob("*"))
            )
            missing = HostedBlobRef(
                RUN_ONE,
                HostedBlobRole.PROJECTION,
                "f" * 64,
                1,
            )
            with self.assertRaises(StoragePolicyError):
                store.read(missing)
            after = tuple(
                sorted(path.relative_to(temp).as_posix() for path in temp.rglob("*"))
            )
            first_bytes = store.read(first)
            second_bytes = store.read(second)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first.blob_ref, second.blob_ref)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first_bytes, b"same")
        self.assertEqual(second_bytes, b"same")
        self.assertEqual(before, after)

    def test_projection_cache_is_the_only_deletable_blob_role(self) -> None:
        with d_drive_tempdir() as temp:
            store = HostedAgentBlobStore(temp / "agent-cells")
            context = store.write(RUN_ONE, HostedBlobRole.CONTEXT, b"context")
            cache = store.write(RUN_ONE, HostedBlobRole.PROJECTION, b"cache")
            with self.assertRaises(StoragePolicyError):
                store.delete_projection_cache(context)
            self.assertTrue(store.delete_projection_cache(cache))
            self.assertFalse(store.exists(cache))
            self.assertEqual(store.read(context), b"context")

    def test_workspace_tools_deny_escape_and_secret_traversal(self) -> None:
        with d_drive_tempdir() as temp:
            workspace = temp / "workspace"
            (workspace / "docs").mkdir(parents=True)
            (workspace / "docs" / "ok.txt").write_text("needle\n", encoding="utf-8")
            (workspace / "docs" / ".env").write_text("SECRET_CANARY", encoding="utf-8")
            (workspace / "docs" / "hidden.pem").write_text(
                "SECRET_CANARY", encoding="utf-8"
            )
            tools = HostedWorkspaceTools(workspace, allowed_prefixes=("docs",))
            escape = HostedToolRequest(
                "33333333-3333-4333-8333-333333333333",
                "workspace.read_text",
                {"path": "../outside.txt"},
            )
            with self.assertRaises(HostedToolDeniedError):
                tools.prepare(escape, max_result_bytes=1024)
            denied_request = HostedToolRequest(
                "44444444-4444-4444-8444-444444444444",
                "workspace.read_text",
                {"path": "docs/.env"},
            )
            with self.assertRaises(HostedToolDeniedError):
                tools.prepare(denied_request, max_result_bytes=1024)
            listing = HostedToolRequest(
                "55555555-5555-4555-8555-555555555555",
                "workspace.list_files",
                {"prefix": "docs", "limit": 20},
            )
            prepared = tools.prepare(listing, max_result_bytes=4096)
            with self.assertRaisesRegex(
                HostedToolDeniedError,
                "host permit",
            ):
                tools._execute(prepared, object())

        self.assertFalse(hasattr(tools, "execute"))
        self.assertEqual(prepared.arguments["prefix"], "docs")


if __name__ == "__main__":
    unittest.main()
