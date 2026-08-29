from __future__ import annotations

import unittest
import sqlite3
from dataclasses import replace

from macr_runtime.accounting import AccountingStore, CostClass
from macr_runtime.errors import AccountingConflict, StoragePolicyError
from macr_runtime.execution import (
    AuthorizationReference,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
)
from macr_runtime.planning_contracts import BudgetMode, OperatorPolicyProfile

from tests.support import d_drive_tempdir


RUN_ID = "11111111-1111-4111-8111-111111111111"
CONTEXT = DispatchContext(
    run_id=RUN_ID,
    plane=InteractionPlane.DELEGATION,
    origin=DispatchOrigin("test", "process_id", "1234"),
    authorization=AuthorizationReference(
        source_kind="test",
        source_id="authority-1",
        digest="a" * 64,
        revision=1,
        epoch=1,
        scope="provider:glm_flash_worker",
    ),
    policy_snapshot_sha256="b" * 64,
)
NON_STOP_OBSERVATION = RawProviderObservation(
    provider_id="glm_flash_worker",
    model="glm-5.3-flash",
    response_id="response-1",
    finish_reason="length",
    usage=ProviderUsage(20, 10, 8, 0),
    currency_cost_usd=0.000008,
    cost_kind="estimated",
    pricing_basis_version="zai-2026-08-27",
    duration_ms=100,
    answer_bytes=b"PARTIAL PRIVATE ANSWER",
    provider_state=ProviderState.INCOMPLETE,
)
PLAN_DIGEST = "c" * 64
PRICING_BASIS = "d" * 64


class AccountingStoreTests(unittest.TestCase):
    def test_accounting_schema_one_upgrades_additively_without_invocation_rewrite(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "accounting.sqlite3"
            store = AccountingStore(database)
            store.record_dispatch(
                RUN_ID,
                CONTEXT,
                provider_id="glm_flash_worker",
                model="glm-5.3-flash",
                estimate_usd=0.01,
            )
            connection = sqlite3.connect(database)
            for table in (
                "bill_observation_outbox",
                "bill_observations",
                "plan_cost_outbox",
                "plan_costs",
            ):
                connection.execute(f"DROP TABLE {table}")
            connection.execute(
                "UPDATE accounting_schema_meta SET version = 1 "
                "WHERE component = 'accounting'"
            )
            connection.commit()
            connection.close()
            upgraded = AccountingStore(database)
            invocation = upgraded.read_invocation(RUN_ID)
            connection = sqlite3.connect(database)
            version = connection.execute(
                "SELECT version FROM accounting_schema_meta "
                "WHERE component = 'accounting'"
            ).fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            connection.close()

        self.assertEqual(version, 2)
        self.assertEqual(invocation["provider_id"], "glm_flash_worker")
        self.assertIn("plan_costs", tables)
        self.assertIn("bill_observations", tables)

    def test_plan_cost_classes_remain_separate_and_warn_mode_does_not_reject(self) -> None:
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            store.record_dispatch(
                RUN_ID,
                CONTEXT,
                provider_id="glm_flash_worker",
                model="glm-5.3-flash",
                estimate_usd=0.03,
            )
            probe = store.record_plan_cost(
                PLAN_DIGEST,
                RUN_ID,
                CostClass.PROBE_COST,
                0.01,
                "estimated",
                PRICING_BASIS,
                role_digest="e" * 64,
                route_id="f" * 64,
                idempotency_key="probe-one",
            )
            verification = store.record_plan_cost(
                PLAN_DIGEST,
                RUN_ID,
                CostClass.VERIFICATION_COST,
                0.02,
                "observed",
                PRICING_BASIS,
                role_digest="e" * 64,
                route_id="f" * 64,
                idempotency_key="verification-one",
            )
            totals = store.plan_costs(PLAN_DIGEST)
            warn = store.evaluate_budget(
                PLAN_DIGEST,
                OperatorPolicyProfile.owner_default(),
                warning_threshold_usd=0.015,
            )
            enforce_profile = replace(
                OperatorPolicyProfile.owner_default(),
                budget_mode=BudgetMode.ENFORCE,
            )
            enforced = store.evaluate_budget(
                PLAN_DIGEST,
                enforce_profile,
                warning_threshold_usd=0.015,
            )
            outbox = store.pending_plan_cost_outbox()

        self.assertNotEqual(probe.cost_id, verification.cost_id)
        self.assertEqual(totals[CostClass.PROBE_COST.value], 0.01)
        self.assertEqual(totals[CostClass.VERIFICATION_COST.value], 0.02)
        self.assertTrue(warn.allowed)
        self.assertIsNotNone(warn.warning)
        self.assertFalse(enforced.allowed)
        self.assertEqual(len(outbox), 2)

    def test_plan_cost_idempotency_conflict_cannot_overwrite_amount(self) -> None:
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            first = store.record_plan_cost(
                PLAN_DIGEST,
                None,
                CostClass.DISCOVERY_COST,
                0.001,
                "estimated",
                PRICING_BASIS,
                idempotency_key="discovery-snapshot-one",
            )
            repeated = store.record_plan_cost(
                PLAN_DIGEST,
                None,
                CostClass.DISCOVERY_COST,
                0.001,
                "estimated",
                PRICING_BASIS,
                idempotency_key="discovery-snapshot-one",
            )
            with self.assertRaisesRegex(AccountingConflict, "plan cost"):
                store.record_plan_cost(
                    PLAN_DIGEST,
                    None,
                    CostClass.DISCOVERY_COST,
                    1.0,
                    "estimated",
                    PRICING_BASIS,
                    idempotency_key="discovery-snapshot-one",
                )

        self.assertEqual(first, repeated)
    def test_rejected_non_stop_call_keeps_observed_cost(self) -> None:
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            store.record_dispatch(
                RUN_ID,
                CONTEXT,
                provider_id="glm_flash_worker",
                model="glm-5.3-flash",
                estimate_usd=0.002,
            )
            store.record_observation(RUN_ID, NON_STOP_OBSERVATION)
            store.record_terminal(
                RUN_ID,
                candidate_status="candidate_failure",
                billing_state="estimated",
            )

            row = store.read_invocation(RUN_ID)

        self.assertEqual(row["finish_reason"], "length")
        self.assertEqual(
            row["currency_cost_usd"],
            NON_STOP_OBSERVATION.currency_cost_usd,
        )
        self.assertEqual(row["candidate_status"], "candidate_failure")
        self.assertEqual(row["reasoning_tokens"], 8)

    def test_unknown_after_dispatch_never_defaults_to_zero(self) -> None:
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            store.record_dispatch(
                RUN_ID,
                CONTEXT,
                provider_id="grok",
                model="grok-4.6",
                estimate_usd=0.001,
            )
            store.record_terminal(
                RUN_ID,
                candidate_status="candidate_failure",
                billing_state="unknown_after_dispatch",
            )

            row = store.read_invocation(RUN_ID)

        self.assertIsNone(row["currency_cost_usd"])
        self.assertEqual(row["billing_state"], "unknown_after_dispatch")

    def test_answer_bytes_never_enter_accounting_database(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "accounting.sqlite3"
            store = AccountingStore(database)
            store.record_dispatch(
                RUN_ID,
                CONTEXT,
                provider_id="glm_flash_worker",
                model="glm-5.3-flash",
                estimate_usd=0.002,
            )
            store.record_observation(RUN_ID, NON_STOP_OBSERVATION)
            store.record_terminal(
                RUN_ID,
                candidate_status="candidate_failure",
                billing_state="estimated",
            )

            database_bytes = database.read_bytes()
            outbox = store.pending_outbox()

        self.assertNotIn(b"PARTIAL PRIVATE ANSWER", database_bytes)
        self.assertNotIn("PARTIAL PRIVATE ANSWER", str(outbox))

    def test_soft_warning_does_not_change_supplied_candidate_status(self) -> None:
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            store.record_dispatch(
                RUN_ID,
                CONTEXT,
                provider_id="glm_flash_worker",
                model="glm-5.3-flash",
                estimate_usd=0.002,
                soft_warning=True,
            )
            store.record_observation(RUN_ID, NON_STOP_OBSERVATION)
            store.record_terminal(
                RUN_ID,
                candidate_status="candidate_success",
                billing_state="estimated",
            )

            row = store.read_invocation(RUN_ID)

        self.assertEqual(row["soft_warning"], 1)
        self.assertEqual(row["candidate_status"], "candidate_success")

    def test_observation_is_idempotent_but_cannot_be_overwritten(self) -> None:
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            store.record_dispatch(
                RUN_ID,
                CONTEXT,
                provider_id="glm_flash_worker",
                model="glm-5.3-flash",
                estimate_usd=0.002,
            )
            store.record_observation(RUN_ID, NON_STOP_OBSERVATION)
            store.record_observation(RUN_ID, NON_STOP_OBSERVATION)

            with self.assertRaisesRegex(AccountingConflict, "observation"):
                store.record_observation(
                    RUN_ID,
                    replace(
                        NON_STOP_OBSERVATION,
                        currency_cost_usd=0.5,
                    ),
                )

    def test_provider_subaccounts_keep_funding_sources_separate(self) -> None:
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            cash = store.upsert_provider_account(
                provider_id="glm_flash_worker",
                funding_kind="cash",
                currency="USD",
                display_name="Z.ai cash",
            )
            promo = store.upsert_provider_account(
                provider_id="glm_flash_worker",
                funding_kind="promotion",
                currency="USD",
                display_name="Z.ai promotion",
            )
            store.append_accounting_entry(
                cash,
                run_id=None,
                entry_kind="credit",
                amount=5.0,
                source_kind="operator_opening_balance",
                source_digest="c" * 64,
            )
            store.append_accounting_entry(
                promo,
                run_id=None,
                entry_kind="credit",
                amount=2.0,
                source_kind="promotion",
                source_digest="d" * 64,
            )
            store.append_accounting_entry(
                cash,
                run_id=None,
                entry_kind="debit",
                amount=-0.25,
                source_kind="manual_adjustment",
                source_digest="e" * 64,
            )

            summary = store.account_summary()

        self.assertEqual(summary["USD"][cash], 4.75)
        self.assertEqual(summary["USD"][promo], 2.0)

    def test_reconciliation_is_append_only_and_idempotent(self) -> None:
        reconciliation_id = "22222222-2222-4222-8222-222222222222"
        with d_drive_tempdir() as temp:
            store = AccountingStore(temp / "accounting.sqlite3")
            store.record_dispatch(
                RUN_ID,
                CONTEXT,
                provider_id="glm_flash_worker",
                model="glm-5.3-flash",
                estimate_usd=0.002,
            )
            first = store.append_reconciliation(
                reconciliation_id=reconciliation_id,
                run_id=RUN_ID,
                authority_source="future-accounting-ai",
                amount=0.0018,
                currency="USD",
                payment_status="settled",
                payload_sha256="f" * 64,
                observed_at="2026-08-27T10:00:00+00:00",
            )
            second = store.append_reconciliation(
                reconciliation_id=reconciliation_id,
                run_id=RUN_ID,
                authority_source="future-accounting-ai",
                amount=0.0018,
                currency="USD",
                payment_status="settled",
                payload_sha256="f" * 64,
                observed_at="2026-08-27T10:00:00+00:00",
            )
            with self.assertRaisesRegex(AccountingConflict, "reconciliation"):
                store.append_reconciliation(
                    reconciliation_id=reconciliation_id,
                    run_id=RUN_ID,
                    authority_source="future-accounting-ai",
                    amount=9.0,
                    currency="USD",
                    payment_status="settled",
                    payload_sha256="f" * 64,
                    observed_at="2026-08-27T10:00:00+00:00",
                )

        self.assertTrue(first)
        self.assertFalse(second)

    def test_database_path_must_be_absolute_on_d(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "absolute on D"):
            AccountingStore(r"C:\temp\accounting.sqlite3")


if __name__ == "__main__":
    unittest.main()
