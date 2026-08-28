from __future__ import annotations

import unittest

from macr_runtime.direct_contracts import DirectConversationSpec
from macr_runtime.direct_settings import operator_managed_settings
from macr_runtime.direct_store import DirectConversationStore
from macr_runtime.errors import DirectStoreConflict, StoragePolicyError
from tests.support import d_drive_tempdir


QWYTHOS_MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"
CONVERSATION_ID = "00000000-0000-4000-8000-000000000011"
RUN_ID = "00000000-0000-4000-8000-000000000012"


def qwythos_spec() -> DirectConversationSpec:
    return DirectConversationSpec.create(
        provider_id="ollama_qwythos",
        model=QWYTHOS_MODEL,
        model_digest="b" * 64,
        system_prompt="Visible system prompt",
        settings=operator_managed_settings(),
    )


class DirectConversationStoreTests(unittest.TestCase):
    def test_create_pins_identity_and_exact_private_metadata(self) -> None:
        with d_drive_tempdir() as root:
            store = DirectConversationStore(root / "conversations.sqlite3")
            created = store.create(
                qwythos_spec(),
                title="Qwythos test",
                conversation_id=CONVERSATION_ID,
            )

            self.assertEqual(created["conversation_id"], CONVERSATION_ID)
            self.assertEqual(created["provider_id"], "ollama_qwythos")
            self.assertEqual(created["model"], QWYTHOS_MODEL)
            self.assertEqual(created["model_digest"], "b" * 64)
            self.assertEqual(created["system_prompt"], "Visible system prompt")
            self.assertEqual(created["dataset_role"], "eval_only")
            self.assertFalse(created["training_eligible"])
            self.assertEqual(created["encryption"], "none")
            self.assertFalse(created["archived"])

            store.assert_identity(
                CONVERSATION_ID,
                provider_id="ollama_qwythos",
                model=QWYTHOS_MODEL,
            )
            with self.assertRaisesRegex(DirectStoreConflict, "identity"):
                store.assert_identity(
                    CONVERSATION_ID,
                    provider_id="grok",
                    model="grok-4.6",
                )

    def test_messages_runs_and_completion_commit_atomically(self) -> None:
        with d_drive_tempdir() as root:
            store = DirectConversationStore(root / "conversations.sqlite3")
            store.create(qwythos_spec(), conversation_id=CONVERSATION_ID)
            user = store.append_user(
                CONVERSATION_ID,
                "  exact user text  ",
                run_id=RUN_ID,
            )
            self.assertEqual(user["ordinal"], 1)
            self.assertEqual(user["content"], "  exact user text  ")
            store.start_run(
                run_id=RUN_ID,
                conversation_id=CONVERSATION_ID,
                user_ordinal=1,
            )

            assistant = store.append_assistant_atomic(
                conversation_id=CONVERSATION_ID,
                run_id=RUN_ID,
                content="exact assistant text\n",
                observation_id="response-local-1",
                context_estimate=321,
                context_warning=False,
            )

            self.assertEqual(assistant["ordinal"], 2)
            self.assertEqual(assistant["content"], "exact assistant text\n")
            self.assertEqual(
                [(item["role"], item["content"]) for item in store.messages(CONVERSATION_ID)],
                [
                    ("user", "  exact user text  "),
                    ("assistant", "exact assistant text\n"),
                ],
            )
            run = store.read_run(RUN_ID)
            self.assertEqual(run["state"], "completed")
            self.assertEqual(run["context_estimate"], 321)
            self.assertFalse(run["context_warning"])

            with self.assertRaisesRegex(DirectStoreConflict, "terminal"):
                store.append_assistant_atomic(
                    conversation_id=CONVERSATION_ID,
                    run_id=RUN_ID,
                    content="duplicate",
                    observation_id="response-local-2",
                    context_estimate=322,
                    context_warning=False,
                )
            self.assertEqual(len(store.messages(CONVERSATION_ID)), 2)

    def test_history_search_archive_and_restore_survive_reopen(self) -> None:
        with d_drive_tempdir() as root:
            path = root / "conversations.sqlite3"
            store = DirectConversationStore(path)
            store.create(
                qwythos_spec(),
                title="Long research thread",
                conversation_id=CONVERSATION_ID,
            )
            store.append_user(CONVERSATION_ID, "Hard-Zeta Lemma", run_id=RUN_ID)
            store.start_run(
                run_id=RUN_ID,
                conversation_id=CONVERSATION_ID,
                user_ordinal=1,
            )
            store.fail_run(RUN_ID, state="failed_after_dispatch", failure_type="Synthetic")
            store.archive(CONVERSATION_ID)

            reopened = DirectConversationStore(path)
            self.assertEqual(reopened.list(), ())
            archived = reopened.list(include_archived=True)
            self.assertEqual(len(archived), 1)
            self.assertTrue(archived[0]["archived"])
            self.assertEqual(
                reopened.search("hard-zeta", include_archived=True)[0]["conversation_id"],
                CONVERSATION_ID,
            )
            reopened.restore(CONVERSATION_ID)
            self.assertFalse(reopened.get(CONVERSATION_ID)["archived"])
            self.assertEqual(
                [item["content"] for item in reopened.messages(CONVERSATION_ID)],
                ["Hard-Zeta Lemma"],
            )
            self.assertEqual(reopened.read_run(RUN_ID)["state"], "failed_after_dispatch")

    def test_database_path_must_be_absolute_on_d_before_creation(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "absolute on D"):
            DirectConversationStore("conversations.sqlite3")
        with self.assertRaisesRegex(StoragePolicyError, "absolute on D"):
            DirectConversationStore(r"C:\MACR\conversations.sqlite3")


if __name__ == "__main__":
    unittest.main()
