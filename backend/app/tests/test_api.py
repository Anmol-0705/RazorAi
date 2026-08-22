"""API/integration tests for the Phase 4 FastAPI backend.

Runs against a dedicated PostgreSQL test database (`razorrecon_test`,
distinct from the dev `razorrecon` database) so these tests never
touch dev data. The test database must already have the Alembic
schema applied — see docs/api.md.
"""
import os
import unittest
from decimal import Decimal
from unittest import mock

os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:password@localhost:5432/razorrecon_test"

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.base import get_db
from app.db.models import (
    ActionExecutionORM,
    AutoResolutionRecordORM,
    ExceptionCaseORM,
    PaymentORM,
    ReconciliationResultORM,
    ReconciliationRunORM,
    ReviewAuditORM,
    SettlementORM,
)

TEST_DATABASE_URL = "postgresql+psycopg://postgres:password@localhost:5432/razorrecon_test"
_engine = create_engine(TEST_DATABASE_URL, future=True)
_TestSessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

_TABLES = (
    ActionExecutionORM,
    ReviewAuditORM,
    AutoResolutionRecordORM,
    ExceptionCaseORM,
    ReconciliationResultORM,
    ReconciliationRunORM,
    SettlementORM,
    PaymentORM,
)


def _override_get_db():
    db = _TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


def _truncate_all():
    with _engine.begin() as conn:
        for table in _TABLES:
            conn.execute(text(f'TRUNCATE TABLE "{table.__tablename__}" CASCADE'))


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        _truncate_all()

    def tearDown(self):
        _truncate_all()

    def _create_dataset(self, seed=42, num_records=100):
        resp = client.post("/datasets/demo", json={"seed": seed, "num_records": num_records})
        self.assertIn(resp.status_code, (200, 201))
        return resp.json()["dataset_id"]

    def _run_reconciliation(self, dataset_id, run_id=None):
        payload = {"dataset_id": dataset_id}
        if run_id:
            payload["run_id"] = run_id
        resp = client.post("/reconciliation/runs", json=payload)
        return resp


class HealthTests(ApiTestCase):
    def test_health_reports_ok_and_connected(self):
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "connected")

    def test_health_supports_head(self):
        resp = client.head("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"")


class DemoDatasetTests(ApiTestCase):
    def test_generate_demo_dataset_creates_rows(self):
        resp = client.post("/datasets/demo", json={"seed": 42, "num_records": 100})
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["dataset_id"], "demo-seed42-n100")
        self.assertEqual(body["payment_count"], 100)
        self.assertTrue(body["created"])

    def test_repeated_generation_is_idempotent(self):
        first = client.post("/datasets/demo", json={"seed": 7, "num_records": 50})
        second = client.post("/datasets/demo", json={"seed": 7, "num_records": 50})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(first.json()["dataset_id"], second.json()["dataset_id"])
        self.assertEqual(second.json()["payment_count"], first.json()["payment_count"])

    def test_repeated_generation_does_not_duplicate_payment_rows_in_db(self):
        client.post("/datasets/demo", json={"seed": 11, "num_records": 30})
        client.post("/datasets/demo", json={"seed": 11, "num_records": 30})
        client.post("/datasets/demo", json={"seed": 11, "num_records": 30})

        db = _TestSessionLocal()
        try:
            all_payments = db.execute(
                select(PaymentORM).where(PaymentORM.dataset_id == "demo-seed11-n30")
            ).scalars().all()
            self.assertEqual(len(all_payments), 30)
            self.assertEqual(len({p.transaction_id for p in all_payments}), 30)
        finally:
            db.close()

    def test_repeated_generation_does_not_duplicate_settlement_rows_in_db(self):
        first = client.post("/datasets/demo", json={"seed": 12, "num_records": 30}).json()
        client.post("/datasets/demo", json={"seed": 12, "num_records": 30})

        db = _TestSessionLocal()
        try:
            all_settlements = db.execute(
                select(SettlementORM).where(SettlementORM.dataset_id == "demo-seed12-n30")
            ).scalars().all()
            self.assertEqual(len(all_settlements), first["settlement_count"])
            self.assertEqual(
                len({s.settlement_id for s in all_settlements}), len(all_settlements)
            )
        finally:
            db.close()

    def test_same_dataset_id_reused_across_repeated_calls(self):
        responses = [
            client.post("/datasets/demo", json={"seed": 13, "num_records": 30}).json()
            for _ in range(3)
        ]
        dataset_ids = {r["dataset_id"] for r in responses}
        self.assertEqual(dataset_ids, {"demo-seed13-n30"})
        self.assertEqual([r["created"] for r in responses], [True, False, False])

    def test_different_seed_creates_a_different_dataset(self):
        first = client.post("/datasets/demo", json={"seed": 20, "num_records": 30})
        second = client.post("/datasets/demo", json={"seed": 21, "num_records": 30})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.json()["dataset_id"], second.json()["dataset_id"])
        self.assertTrue(first.json()["created"])
        self.assertTrue(second.json()["created"])

    def test_same_seed_different_num_records_now_coexist_safely(self):
        # Identifiers derived from (seed, index) (transaction_id,
        # order_id) or from the shared rng stream (payment.id,
        # settlement.id, settlement_id) are namespaced/reseeded by
        # num_records (app.data_generation.generator), so datasets
        # sharing a seed no longer collide -- each size succeeds
        # independently and all three coexist.
        first = client.post("/datasets/demo", json={"seed": 30, "num_records": 30})
        second = client.post("/datasets/demo", json={"seed": 30, "num_records": 60})
        third = client.post("/datasets/demo", json={"seed": 30, "num_records": 90})

        self.assertEqual([r.status_code for r in (first, second, third)], [201, 201, 201])
        self.assertEqual(
            {r.json()["dataset_id"] for r in (first, second, third)},
            {"demo-seed30-n30", "demo-seed30-n60", "demo-seed30-n90"},
        )

        db = _TestSessionLocal()
        try:
            by_size = {}
            for n in (30, 60, 90):
                rows = db.execute(
                    select(PaymentORM).where(PaymentORM.dataset_id == f"demo-seed30-n{n}")
                ).scalars().all()
                self.assertEqual(len(rows), n)
                by_size[n] = rows

            # No transaction_id, order_id, or payment.id collides
            # across any pair of differently-sized same-seed datasets.
            for field in ("transaction_id", "order_id", "id"):
                for a, b in ((30, 60), (30, 90), (60, 90)):
                    values_a = {getattr(r, field) for r in by_size[a]}
                    values_b = {getattr(r, field) for r in by_size[b]}
                    self.assertEqual(
                        values_a & values_b, set(), f"{field} collided between n{a} and n{b}"
                    )
        finally:
            db.close()

    def test_repeated_request_for_one_of_several_coexisting_sizes_is_idempotent(self):
        client.post("/datasets/demo", json={"seed": 31, "num_records": 30})
        client.post("/datasets/demo", json={"seed": 31, "num_records": 60})

        first_60 = client.post("/datasets/demo", json={"seed": 31, "num_records": 60})
        second_60 = client.post("/datasets/demo", json={"seed": 31, "num_records": 60})

        self.assertEqual(first_60.status_code, 200)  # already existed from the setup call above
        self.assertEqual(second_60.status_code, 200)
        self.assertFalse(second_60.json()["created"])
        self.assertEqual(first_60.json()["payment_count"], second_60.json()["payment_count"])

        db = _TestSessionLocal()
        try:
            rows = db.execute(
                select(PaymentORM).where(PaymentORM.dataset_id == "demo-seed31-n60")
            ).scalars().all()
            self.assertEqual(len(rows), 60)
        finally:
            db.close()

    def test_pre_existing_legacy_format_dataset_is_reused_not_regenerated(self):
        # Simulates data already hosted before this fix: a dataset_id
        # row set inserted directly (bypassing today's generator/
        # namespacing entirely), matching what production already has
        # persisted under the old, unnamespaced identifier format.
        # Requesting this exact dataset_id again must reuse it exactly
        # as stored -- never regenerate or alter it.
        from app.data_generation.config import GeneratorConfig
        from app.data_generation.generator import _build_payment
        import random

        legacy_rng = random.Random(99)
        legacy_payment = _build_payment(legacy_rng, 0, GeneratorConfig(seed=99, num_records=1))
        # Force the pre-fix (unnamespaced) shape regardless of what the
        # current generator now produces, to faithfully model already-
        # hosted legacy rows.
        legacy_txn_id = "TXN-99-000000"

        db = _TestSessionLocal()
        try:
            db.add(
                PaymentORM(
                    id=legacy_payment.id,
                    dataset_id="demo-seed99-n1",
                    transaction_id=legacy_txn_id,
                    order_id="ORD-99-000000",
                    customer_reference=legacy_payment.customer_reference,
                    amount=legacy_payment.amount,
                    currency=legacy_payment.currency.value,
                    payment_method=legacy_payment.payment_method.value,
                    payment_status=legacy_payment.payment_status.value,
                    created_at=legacy_payment.created_at,
                )
            )
            db.commit()
        finally:
            db.close()

        resp = client.post("/datasets/demo", json={"seed": 99, "num_records": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["created"])
        self.assertEqual(resp.json()["payment_count"], 1)

        db = _TestSessionLocal()
        try:
            row = db.execute(
                select(PaymentORM).where(PaymentORM.dataset_id == "demo-seed99-n1")
            ).scalar_one()
            self.assertEqual(row.transaction_id, legacy_txn_id, "legacy row must not be regenerated/altered")
        finally:
            db.close()

    def test_concurrent_duplicate_request_reuses_winner_instead_of_crashing(self):
        # Simulate two requests racing to generate the same dataset: by
        # the time our own insert reaches db.commit(), a "concurrent"
        # request has already committed the identical rows first (this
        # is exactly the state a genuine race leaves behind, without
        # relying on real thread timing to reproduce reliably).
        from app.services import dataset_service

        winner_committed = {"done": False}
        real_generate_dataset = dataset_service.generate_dataset

        def _generate_then_let_concurrent_winner_commit_first(config):
            bundle = real_generate_dataset(config)
            if not winner_committed["done"]:
                winner_committed["done"] = True
                concurrent_db = _TestSessionLocal()
                try:
                    dataset_service.generate_and_persist_demo_dataset(
                        concurrent_db, seed=config.seed, num_records=config.num_records
                    )
                finally:
                    concurrent_db.close()
            return bundle

        with mock.patch.object(
            dataset_service, "generate_dataset", side_effect=_generate_then_let_concurrent_winner_commit_first
        ):
            resp = client.post("/datasets/demo", json={"seed": 40, "num_records": 30})

        self.assertEqual(resp.status_code, 200)  # not created by us -- the concurrent winner created it
        body = resp.json()
        self.assertEqual(body["dataset_id"], "demo-seed40-n30")
        self.assertFalse(body["created"])
        self.assertEqual(body["payment_count"], 30)

        db = _TestSessionLocal()
        try:
            all_payments = db.execute(
                select(PaymentORM).where(PaymentORM.dataset_id == "demo-seed40-n30")
            ).scalars().all()
            self.assertEqual(len(all_payments), 30)
            self.assertEqual(len({p.transaction_id for p in all_payments}), 30)
        finally:
            db.close()


class ReconciliationRunTests(ApiTestCase):
    def test_run_persists_results_and_exceptions(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        resp = self._run_reconciliation(dataset_id)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["record_count"], 100)
        self.assertIn("match_status", body["summary"])

        results_resp = client.get(f"/reconciliation/runs/{body['run_id']}/results")
        self.assertEqual(results_resp.status_code, 200)
        self.assertEqual(len(results_resp.json()), sum(body["summary"]["match_status"].values()))

    def test_run_against_unknown_dataset_returns_404(self):
        resp = self._run_reconciliation("does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_filter_results_by_status(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        run_id = self._run_reconciliation(dataset_id).json()["run_id"]

        resp = client.get(f"/reconciliation/runs/{run_id}/results", params={"status": "matched"})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()
        self.assertTrue(all(r["match_status"] == "matched" for r in results))
        self.assertGreater(len(results), 0)

    def test_results_are_enriched_with_payment_and_settlement_fields(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        run_id = self._run_reconciliation(dataset_id).json()["run_id"]

        results = client.get(f"/reconciliation/runs/{run_id}/results", params={"status": "matched"}).json()
        sample = results[0]
        self.assertIsNotNone(sample["order_id"])
        self.assertIsNotNone(sample["payment_amount"])
        self.assertIsNotNone(sample["payment_method"])
        self.assertIsNotNone(sample["settlement_status"])

    def test_get_run_not_found(self):
        resp = client.get("/reconciliation/runs/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_list_runs(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        self._run_reconciliation(dataset_id)

        resp = client.get("/reconciliation/runs")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)


class RepeatedReconciliationTests(ApiTestCase):
    def test_repeating_same_run_id_is_idempotent(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        first = self._run_reconciliation(dataset_id, run_id="fixed-run-1")
        second = self._run_reconciliation(dataset_id, run_id="fixed-run-1")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["completed_at"], second.json()["completed_at"])

        results = client.get("/reconciliation/runs/fixed-run-1/results").json()
        # No duplicate rows from the second (no-op) call.
        result_ids = [r["id"] for r in results]
        self.assertEqual(len(result_ids), len(set(result_ids)))

    def test_omitting_run_id_creates_a_new_run_each_time(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        first = self._run_reconciliation(dataset_id).json()
        second = self._run_reconciliation(dataset_id).json()
        self.assertNotEqual(first["run_id"], second["run_id"])


class FailureHandlingTests(ApiTestCase):
    def test_reconciliation_failure_leaves_no_partial_results(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)

        import app.services.reconciliation_service as svc

        original = svc.reconcile

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated failure")

        svc.reconcile = _boom
        try:
            resp = self._run_reconciliation(dataset_id, run_id="will-fail")
        finally:
            svc.reconcile = original

        self.assertEqual(resp.status_code, 500)

        with _TestSessionLocal() as db:
            run = db.get(ReconciliationRunORM, "will-fail")
            self.assertIsNotNone(run)
            self.assertEqual(run.status, "failed")
            self.assertIsNotNone(run.error)

        results = client.get("/reconciliation/runs/will-fail/results").json()
        self.assertEqual(results, [])


class DashboardSummaryTests(ApiTestCase):
    def test_summary_reflects_real_persisted_data(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        run = self._run_reconciliation(dataset_id).json()

        resp = client.get("/dashboard/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["run_id"], run["run_id"])
        self.assertEqual(body["total_transactions"], 100)
        self.assertEqual(body["matched"], run["summary"]["match_status"].get("matched", 0))
        self.assertEqual(body["exceptions"], run["summary"]["exception_count"])
        self.assertGreater(Decimal(body["amount_reconciled"]), Decimal("0"))

    def test_summary_with_no_runs_is_all_zero(self):
        resp = client.get("/dashboard/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body["run_id"])
        self.assertEqual(body["total_transactions"], 0)


class ExceptionListingTests(ApiTestCase):
    def test_list_and_filter_exceptions(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        self._run_reconciliation(dataset_id)

        resp = client.get("/exceptions", params={"exception_type": "fee_mismatch"})
        self.assertEqual(resp.status_code, 200)
        exceptions = resp.json()
        self.assertGreater(len(exceptions), 0)
        self.assertTrue(all(e["exception_type"] == "fee_mismatch" for e in exceptions))

    def test_get_exception_detail_includes_audit_trails(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        self._run_reconciliation(dataset_id)

        exc_id = client.get("/exceptions").json()[0]["id"]
        resp = client.get(f"/exceptions/{exc_id}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["exception"]["id"], exc_id)
        self.assertIn("auto_resolutions", body)
        self.assertIn("review_audits", body)

    def test_get_exception_detail_includes_enriched_payment_and_settlement_fields(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        self._run_reconciliation(dataset_id)

        exc = client.get("/exceptions", params={"exception_type": "amount_mismatch"}).json()[0]
        detail = client.get(f"/exceptions/{exc['id']}").json()

        result = detail["result"]
        self.assertIsNotNone(result)
        self.assertEqual(result["match_strategy"], "reference_amount")
        self.assertIsNotNone(result["payment_amount"])
        self.assertIsNotNone(result["settled_amount"])
        self.assertIsNotNone(result["order_id"])

    def test_get_exception_not_found(self):
        resp = client.get("/exceptions/does-not-exist")
        self.assertEqual(resp.status_code, 404)


class ReviewActionTests(ApiTestCase):
    def _pending_exception_id(self, dataset_id):
        self._run_reconciliation(dataset_id)
        exceptions = client.get("/exceptions", params={"status": "pending"}).json()
        self.assertGreater(len(exceptions), 0)
        return exceptions[0]["id"]

    def test_approve_action_persists_status_and_audit(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        exc_id = self._pending_exception_id(dataset_id)

        resp = client.post(
            f"/exceptions/{exc_id}/approve", json={"reviewer": "reviewer@example.com", "note": "ok"}
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["exception"]["review_status"], "approved")
        self.assertEqual(body["audit"]["action"], "approve")
        self.assertEqual(body["audit"]["previous_status"], "pending")
        self.assertEqual(body["audit"]["new_status"], "approved")

        detail = client.get(f"/exceptions/{exc_id}").json()
        self.assertEqual(len(detail["review_audits"]), 1)

    def test_reject_action(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        exc_id = self._pending_exception_id(dataset_id)

        resp = client.post(f"/exceptions/{exc_id}/reject", json={"reviewer": "r@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["exception"]["review_status"], "rejected")

    def test_add_note_does_not_change_status(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        exc_id = self._pending_exception_id(dataset_id)

        resp = client.post(
            f"/exceptions/{exc_id}/add-note", json={"reviewer": "r@example.com", "note": "checking"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["exception"]["review_status"], "pending")
        self.assertEqual(resp.json()["audit"]["note"], "checking")

    def test_review_action_on_unknown_exception_returns_404(self):
        resp = client.post("/exceptions/does-not-exist/approve", json={"reviewer": "r@example.com"})
        self.assertEqual(resp.status_code, 404)


class ControllerActionExecutionTests(ApiTestCase):
    def _exception_id_by_type(self, dataset_id, exception_type):
        self._run_reconciliation(dataset_id)
        exceptions = client.get("/exceptions", params={"exception_type": exception_type}).json()
        self.assertGreater(len(exceptions), 0, f"no {exception_type} exceptions in this dataset")
        return exceptions[0]["id"]

    def test_eligible_action_executes_and_persists(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        exc_id = self._exception_id_by_type(dataset_id, "fee_mismatch")

        detail_before = client.get(f"/exceptions/{exc_id}").json()
        self.assertTrue(detail_before["controller_action"]["eligible"])
        self.assertEqual(
            detail_before["controller_action"]["action_type"], "settlement_adjustment_instruction"
        )

        resp = client.post(f"/exceptions/{exc_id}/execute-action")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["eligible"])
        self.assertFalse(body["already_executed"])
        self.assertIsNotNone(body["action"])
        self.assertEqual(body["action"]["action_type"], "settlement_adjustment_instruction")
        self.assertEqual(body["action"]["status"], "completed")
        self.assertTrue(body["action"]["resulting_reference"].startswith("SYN-SAI-"))
        self.assertIsNotNone(body["audit"])
        self.assertEqual(body["audit"]["action"], "controller_action")

        detail_after = client.get(f"/exceptions/{exc_id}").json()
        self.assertEqual(len(detail_after["action_executions"]), 1)
        self.assertEqual(
            detail_after["action_executions"][0]["resulting_reference"], body["action"]["resulting_reference"]
        )

    def test_non_eligible_action_is_rejected_without_persisting(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        exc_id = self._exception_id_by_type(dataset_id, "amount_mismatch")

        resp = client.post(f"/exceptions/{exc_id}/execute-action")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["eligible"])
        self.assertIsNone(body["action"])
        self.assertIsNone(body["audit"])
        self.assertIn("human review", body["reason"])

        detail = client.get(f"/exceptions/{exc_id}").json()
        self.assertEqual(len(detail["action_executions"]), 0)

    def test_high_impact_missing_settlement_is_rejected(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        exc_id = self._exception_id_by_type(dataset_id, "missing_settlement")

        resp = client.post(f"/exceptions/{exc_id}/execute-action")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["eligible"])
        self.assertIsNone(body["action"])

    def test_duplicate_execution_is_idempotent(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        exc_id = self._exception_id_by_type(dataset_id, "fee_mismatch")

        first = client.post(f"/exceptions/{exc_id}/execute-action").json()
        second = client.post(f"/exceptions/{exc_id}/execute-action").json()

        self.assertFalse(first["already_executed"])
        self.assertTrue(second["already_executed"])
        self.assertEqual(first["action"]["id"], second["action"]["id"])
        self.assertEqual(first["action"]["resulting_reference"], second["action"]["resulting_reference"])
        self.assertIsNone(second["audit"])  # no duplicate audit entry on replay

        detail = client.get(f"/exceptions/{exc_id}").json()
        self.assertEqual(len(detail["action_executions"]), 1)
        self.assertEqual(
            len([a for a in detail["review_audits"] if a["action"] == "controller_action"]), 1
        )

    def test_pending_exception_status_moves_to_approved_on_execution(self):
        dataset_id = self._create_dataset(seed=42, num_records=100)
        exc_id = self._exception_id_by_type(dataset_id, "fee_mismatch")
        exc_before = client.get(f"/exceptions/{exc_id}").json()["exception"]

        resp = client.post(f"/exceptions/{exc_id}/execute-action").json()

        if exc_before["review_status"] == "pending":
            self.assertEqual(resp["exception"]["review_status"], "approved")
        else:
            # Most fee_mismatch cases are already auto_resolved by the
            # time a normal reconciliation run completes; the action
            # engine must not disturb that status.
            self.assertEqual(resp["exception"]["review_status"], exc_before["review_status"])

    def test_execute_action_on_unknown_exception_returns_404(self):
        resp = client.post("/exceptions/does-not-exist/execute-action")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
