"""API/integration tests for the Phase 4 FastAPI backend.

Runs against a dedicated PostgreSQL test database (`razorrecon_test`,
distinct from the dev `razorrecon` database) so these tests never
touch dev data. The test database must already have the Alembic
schema applied — see docs/api.md.
"""
import os
import unittest
from decimal import Decimal

os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:password@localhost:5432/razorrecon_test"

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.api.main import app
from app.db.base import get_db
from app.db.models import (
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


if __name__ == "__main__":
    unittest.main()
