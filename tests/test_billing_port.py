from __future__ import annotations

import dataclasses
import unittest

from macr_runtime.accounting import AccountingStore
from macr_runtime.billing_port import (
    BillingPortError,
    BillingReconciliationPort,
)

from tests.support import d_drive_tempdir


def metadata(account_id: str) -> dict[str, object]:
    return {
        "provider_id": "glm_flash_worker",
        "provider_account_id": account_id,
        "funding_source_id": "1" * 64,
        "invoice_item_id": "2" * 64,
        "plan_digest": "3" * 64,
        "run_id": None,
        "amount": 5.25,
        "currency": "USD",
        "tax": 0.25,
        "credit": 0.0,
        "payment_status": "observed_unreconciled",
        "source_digest": "4" * 64,
        "observed_at": "2026-08-29T00:00:00+00:00",
        "metadata": {"billing_period_id": "5" * 64},
    }


class BillingPortTests(unittest.TestCase):
    def test_inspect_is_read_only_and_record_is_append_only_content_free(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "accounting.sqlite3"
            store = AccountingStore(database)
            account_id = store.upsert_provider_account(
                provider_id="glm_flash_worker",
                funding_kind="cash",
                currency="USD",
                display_name="Z.ai cash",
            )
            port = BillingReconciliationPort(store)
            report = port.inspect(metadata(account_id))
            count_before = store.bill_observation_count()
            first = port.record(report.observation)
            second = port.record(report.observation)
            count_after = store.bill_observation_count()
            outbox = store.pending_bill_outbox()
            raw_database = database.read_bytes()

        self.assertFalse(report.wrote)
        self.assertEqual(count_before, 0)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(count_after, 1)
        self.assertEqual(len(outbox), 1)
        self.assertNotIn("metadata", report.observation.to_public_dict())
        self.assertNotIn(b"PRIVATE INVOICE BODY", raw_database)
        with self.assertRaisesRegex(BillingPortError, "observation_id"):
            dataclasses.replace(report.observation, amount=999.0)

    def test_forbidden_invoice_content_keys_fail_before_write(self) -> None:
        forbidden = (
            "prompt",
            "answer",
            "path",
            "credential",
            "invoice_body",
            "remoteHTTPBody",
        )
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            account_id = store.upsert_provider_account(
                provider_id="glm_flash_worker",
                funding_kind="cash",
                currency="USD",
                display_name="Z.ai cash",
            )
            port = BillingReconciliationPort(store)
            for key in forbidden:
                document = metadata(account_id)
                document["metadata"] = {"nested": {key: "PRIVATE INVOICE BODY"}}
                with self.subTest(key=key), self.assertRaisesRegex(
                    BillingPortError,
                    "forbidden",
                ):
                    port.inspect(document)
            count = store.bill_observation_count()

        self.assertEqual(count, 0)

    def test_bill_observation_conflict_and_missing_account_fail_closed(self) -> None:
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            account_id = store.upsert_provider_account(
                provider_id="glm_flash_worker",
                funding_kind="cash",
                currency="USD",
                display_name="Z.ai cash",
            )
            port = BillingReconciliationPort(store)
            observation = port.inspect(metadata(account_id)).observation
            port.record(observation)
            changed = metadata(account_id)
            changed["amount"] = 99.0
            changed["source_digest"] = observation.source_digest
            with self.assertRaisesRegex(BillingPortError, "conflict"):
                port.record(port.inspect(changed).observation)
            missing = metadata("11111111-1111-4111-8111-111111111111")
            missing["source_digest"] = "6" * 64
            with self.assertRaisesRegex(BillingPortError, "account"):
                port.record(port.inspect(missing).observation)


if __name__ == "__main__":
    unittest.main()
