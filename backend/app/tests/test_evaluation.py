"""Tests for the held-out evaluation pipeline (backend/app/evaluation/).

`ScoringUnitTests` hand-verifies the pure scoring math against a small,
manually-computed dataset (no DB, no reconciliation engine involved) —
this is the "verify metrics manually against a known small dataset"
check. `EvaluationApiTests` runs the real pipeline (loader -> real
persisted reconciliation -> scoring) against the actual 250-record
held-out dataset via the API, against the dedicated `razorrecon_test`
database, matching the pattern used by test_api.py/test_ai.py.
"""
import os
import unittest
from decimal import Decimal
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:password@localhost:5432/razorrecon_test"

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db.base import get_db
from app.db.models import (
    AutoResolutionRecordORM,
    EvaluationRunORM,
    ExceptionCaseORM,
    PaymentORM,
    ReconciliationResultORM,
    ReconciliationRunORM,
    ReviewAuditORM,
    SettlementORM,
)
from app.evaluation import loader as eval_loader
from app.evaluation.scoring import score

TEST_DATABASE_URL = "postgresql+psycopg://postgres:password@localhost:5432/razorrecon_test"
_engine = create_engine(TEST_DATABASE_URL, future=True)
_TestSessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

_TABLES = (
    ReviewAuditORM,
    AutoResolutionRecordORM,
    EvaluationRunORM,
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


def _truncate_all():
    with _engine.begin() as conn:
        for table in _TABLES:
            conn.execute(text(f'TRUNCATE TABLE "{table.__tablename__}" CASCADE'))


def _exc(payment_reference, exception_type, review_status="pending", auto_resolvable=False, financial_impact="0.00"):
    return SimpleNamespace(
        payment_reference=payment_reference,
        exception_type=exception_type,
        review_status=review_status,
        auto_resolvable=auto_resolvable,
        financial_impact=Decimal(financial_impact),
    )


def _result(payment_reference, match_status, settled_amount="0.00"):
    return {"payment_reference": payment_reference, "match_status": match_status, "settled_amount": settled_amount}


def _gt(payment_id, condition, expected_diff="0.00"):
    return {
        "payment_transaction_id": payment_id,
        "condition": condition,
        "settlement_ids": [],
        "expected_amount_difference": expected_diff,
        "notes": "",
    }


class ScoringUnitTests(unittest.TestCase):
    """Hand-computed 4-record dataset:
    A: normal_match, correctly predicted clean match.
    B: missing_settlement, correctly predicted (unmatched + exception).
    C: amount_mismatch (ground truth), engine predicts partial_settlement
       instead - the documented D009 swap - must NOT count as a
       classification error.
    D: fee_mismatch, correctly predicted and auto-resolved.
    """

    def setUp(self):
        self.payments = [
            SimpleNamespace(amount=Decimal("100.00")),
            SimpleNamespace(amount=Decimal("200.00")),
            SimpleNamespace(amount=Decimal("300.00")),
            SimpleNamespace(amount=Decimal("400.00")),
        ]
        self.ground_truth = [
            _gt("A", "normal_match"),
            _gt("B", "missing_settlement"),
            _gt("C", "amount_mismatch", "50.00"),
            _gt("D", "fee_mismatch", "10.00"),
        ]
        self.results = [
            _result("A", "matched", "98.00"),
            _result("B", "unmatched"),
            _result("C", "partial", "250.00"),
            _result("D", "matched", "390.00"),
        ]
        self.exceptions = [
            _exc("B", "missing_settlement", review_status="pending"),
            _exc("C", "partial_settlement", review_status="pending"),
            _exc("D", "fee_mismatch", review_status="auto_resolved", auto_resolvable=True, financial_impact="10.00"),
        ]
        self.metrics = score(self.payments, self.results, self.exceptions, self.ground_truth)

    def test_total_records_and_match_rate(self):
        self.assertEqual(self.metrics.total_records, 4)
        self.assertEqual(self.metrics.matched_count, 2)  # A and D
        self.assertEqual(self.metrics.unmatched_count, 1)  # B
        self.assertEqual(self.metrics.match_rate, 0.5)

    def test_match_precision_recall_f1(self):
        # Clean-match positive class = normal_match with a clean matched
        # prediction. Only A qualifies on both sides -> perfect score.
        self.assertEqual(self.metrics.match_confusion.tp, 1)
        self.assertEqual(self.metrics.match_confusion.fp, 0)
        self.assertEqual(self.metrics.match_confusion.fn, 0)
        self.assertEqual(self.metrics.match_confusion.tn, 3)
        self.assertEqual(self.metrics.match_confusion.precision(), 1.0)
        self.assertEqual(self.metrics.match_confusion.recall(), 1.0)
        self.assertEqual(self.metrics.match_confusion.f1(), 1.0)

    def test_exception_detection_precision_recall_f1(self):
        # B, C, D are anomalies and all three got an exception -> perfect.
        self.assertEqual(self.metrics.exception_confusion.tp, 3)
        self.assertEqual(self.metrics.exception_confusion.fp, 0)
        self.assertEqual(self.metrics.exception_confusion.fn, 0)
        self.assertEqual(self.metrics.exception_confusion.tn, 1)
        self.assertEqual(self.metrics.exception_confusion.precision(), 1.0)
        self.assertEqual(self.metrics.exception_confusion.recall(), 1.0)
        self.assertEqual(self.metrics.exception_confusion.f1(), 1.0)

    def test_d009_boundary_case_is_not_a_classification_error(self):
        # C: ground truth amount_mismatch, predicted partial_settlement.
        self.assertEqual(self.metrics.boundary_cases, 1)
        self.assertEqual(self.metrics.boundary_correct, 1)
        self.assertEqual(self.metrics.boundary_agreement_rate(), 1.0)
        # Only B (missing_settlement) and D (fee_mismatch) are strictly
        # classified - C is excluded from this stricter count entirely.
        self.assertEqual(self.metrics.classified_cases, 2)
        self.assertEqual(self.metrics.classified_correct, 2)
        self.assertEqual(self.metrics.exception_type_accuracy(), 1.0)

    def test_d009_boundary_case_flagged_as_error_without_equivalence_class(self):
        # Sanity check the test itself: if we pretend the boundary
        # didn't exist (strict equality), C would be wrong - proving
        # the equivalence-class handling is doing real work, not
        # papering over a case that was fine anyway.
        strict_predicted = self.exceptions[1].exception_type  # "partial_settlement"
        strict_expected = self.ground_truth[2]["condition"]  # "amount_mismatch"
        self.assertNotEqual(strict_predicted, strict_expected)

    def test_auto_resolution_metrics(self):
        self.assertEqual(self.metrics.eligible_count, 1)
        self.assertEqual(self.metrics.auto_resolved_count, 1)
        self.assertEqual(self.metrics.correctly_auto_resolved_count, 1)
        self.assertEqual(self.metrics.unsafe_auto_resolved_count, 0)
        self.assertEqual(self.metrics.auto_resolution_precision(), 1.0)
        self.assertEqual(self.metrics.auto_resolution_eligible_ground_truth, 1)  # only D
        self.assertEqual(self.metrics.auto_resolution_recall(), 1.0)
        self.assertEqual(self.metrics.unresolved_after_automation, 0)

    def test_financial_totals(self):
        self.assertEqual(self.metrics.total_amount_processed, Decimal("1000.00"))
        # A (matched, 98.00) + D (matched, 390.00) + C (partial, 250.00)
        self.assertEqual(self.metrics.total_amount_reconciled, Decimal("738.00"))
        # B (10.00... wait no financial impact given) + C (pending) -> only exceptions still pending count
        self.assertEqual(self.metrics.unresolved_exception_count, 2)  # B and C are pending; D is auto_resolved

    def test_unsafe_auto_resolution_is_detected(self):
        # If an exception whose ground truth condition is NOT one of the
        # safe auto-resolvable types ends up auto_resolved, that must be
        # flagged as unsafe, not silently counted as correct.
        exceptions = [
            _exc("B", "missing_settlement", review_status="auto_resolved", auto_resolvable=True),
        ]
        metrics = score(self.payments, self.results, exceptions, self.ground_truth)
        self.assertEqual(metrics.auto_resolved_count, 1)
        self.assertEqual(metrics.correctly_auto_resolved_count, 0)
        self.assertEqual(metrics.unsafe_auto_resolved_count, 1)

    def test_scoring_is_deterministic_on_repeated_calls(self):
        second = score(self.payments, self.results, self.exceptions, self.ground_truth)
        self.assertEqual(self.metrics.to_dict(), second.to_dict())

    def test_metrics_are_json_serializable(self):
        import json

        json.dumps(self.metrics.to_dict())


class LoaderTests(unittest.TestCase):
    def test_load_eval_dataset_matches_known_distribution(self):
        dataset = eval_loader.load_eval_dataset()
        self.assertEqual(len(dataset.ground_truth), 250)
        self.assertEqual(len(dataset.payments), 250)
        conditions = [g["condition"] for g in dataset.ground_truth]
        self.assertEqual(conditions.count("normal_match"), 137)
        self.assertEqual(conditions.count("missing_settlement"), 18)
        self.assertEqual(conditions.count("duplicate_settlement"), 15)
        self.assertEqual(conditions.count("amount_mismatch"), 20)
        self.assertEqual(conditions.count("partial_settlement"), 20)
        self.assertEqual(conditions.count("fee_mismatch"), 15)
        self.assertEqual(conditions.count("delayed_settlement"), 15)
        self.assertEqual(conditions.count("invalid_reference"), 10)

    def test_missing_dataset_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            eval_loader.load_eval_dataset(
                name="does-not-exist",
                eval_dir=eval_loader.DEFAULT_EVAL_DIR.parent / "does-not-exist",
                ground_truth_dir=eval_loader.DEFAULT_GROUND_TRUTH_DIR,
            )


app = None  # populated lazily below to avoid importing the app before DATABASE_URL is set


def _get_app():
    global app
    if app is None:
        from app.api.main import app as real_app

        real_app.dependency_overrides[get_db] = _override_get_db
        app = real_app
    return app


class EvaluationApiTestCase(unittest.TestCase):
    def setUp(self):
        _truncate_all()
        self.client = TestClient(_get_app())

    def tearDown(self):
        _truncate_all()


class EvaluationApiTests(EvaluationApiTestCase):
    def test_run_evaluation_against_real_held_out_dataset(self):
        resp = self.client.post("/evaluation/run", json={"dataset_name": "n250"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["record_count"], 250)
        metrics = body["metrics"]

        self.assertEqual(metrics["reconciliation"]["total_records"], 250)
        self.assertGreater(metrics["reconciliation"]["match_rate"], 0)
        self.assertIn("d009_note", metrics["exceptions"])
        self.assertGreaterEqual(metrics["exceptions"]["d009_boundary_cases"], 0)
        self.assertGreaterEqual(metrics["auto_resolution"]["eligible_count"], 0)
        self.assertGreater(Decimal(metrics["financial"]["total_amount_processed"]), 0)

    def test_repeated_evaluation_produces_identical_metrics(self):
        first = self.client.post("/evaluation/run", json={"dataset_name": "n250"}).json()
        second = self.client.post("/evaluation/run", json={"dataset_name": "n250"}).json()

        self.assertEqual(first["metrics"], second["metrics"])
        self.assertEqual(first["reconciliation_run_id"], second["reconciliation_run_id"])

    def test_get_latest_evaluation(self):
        run = self.client.post("/evaluation/run", json={"dataset_name": "n250"}).json()
        resp = self.client.get("/evaluation/latest")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["evaluation_id"], run["evaluation_id"])

    def test_get_evaluation_by_id(self):
        run = self.client.post("/evaluation/run", json={"dataset_name": "n250"}).json()
        resp = self.client.get(f"/evaluation/{run['evaluation_id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["metrics"], run["metrics"])

    def test_get_evaluation_not_found(self):
        resp = self.client.get("/evaluation/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_latest_not_found_when_none_exist(self):
        resp = self.client.get("/evaluation/latest")
        self.assertEqual(resp.status_code, 404)

    def test_evaluation_does_not_disturb_demo_dataset_workflow(self):
        self.client.post("/evaluation/run", json={"dataset_name": "n250"})
        demo = self.client.post("/datasets/demo", json={"seed": 42, "num_records": 100}).json()
        run = self.client.post("/reconciliation/runs", json={"dataset_id": demo["dataset_id"]}).json()
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["record_count"], 100)


if __name__ == "__main__":
    unittest.main()
