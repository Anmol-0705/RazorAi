"""Tests for the AI-assisted layer (backend/app/ai/).

Uses a mocked AIProvider throughout — no live LLM call is made or
required. Route-level tests reuse the same dedicated `razorrecon_test`
PostgreSQL database pattern as test_api.py so they never touch dev
data; `app.ai.facts` unit tests exercise the deterministic
data-retrieval layer directly.
"""
import os
import unittest
from decimal import Decimal

os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:password@localhost:5432/razorrecon_test"
os.environ.pop("ANTHROPIC_API_KEY", None)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.ai import facts as ai_facts
from app.ai.anthropic_provider import AnthropicAIProvider, get_ai_provider
from app.ai.provider import AIProvider, AIResult
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


def _truncate_all():
    with _engine.begin() as conn:
        for table in _TABLES:
            conn.execute(text(f'TRUNCATE TABLE "{table.__tablename__}" CASCADE'))


class MockAIProvider(AIProvider):
    """Records calls and returns a canned AIResult, so tests can assert
    both the routing behavior (was the provider called at all, with
    what) and the response shape, without any network access."""

    def __init__(self, structured=None, available=True, error="mock provider unavailable"):
        self.structured = structured or {}
        self._available = available
        self._error = error
        self.calls = []

    def _result(self) -> AIResult:
        if not self._available:
            return AIResult(available=False, error=self._error)
        return AIResult(available=True, structured=self.structured)

    def explain_exception(self, facts):
        self.calls.append(("explain_exception", facts))
        return self._result()

    def recommend_resolution(self, facts):
        self.calls.append(("recommend_resolution", facts))
        return self._result()

    def answer_query(self, question, intent, facts):
        self.calls.append(("answer_query", question, intent, facts))
        return self._result()

    def summarize_reconciliation(self, facts):
        self.calls.append(("summarize_reconciliation", facts))
        return self._result()


class NeverCalledProvider(AIProvider):
    """Fails the test immediately if any method is invoked — used to
    prove the unsupported-question path never reaches the AI."""

    def _fail(self, *_args, **_kwargs):
        raise AssertionError("AI provider should not have been called")

    def explain_exception(self, facts):
        self._fail()

    def recommend_resolution(self, facts):
        self._fail()

    def answer_query(self, question, intent, facts):
        self._fail()

    def summarize_reconciliation(self, facts):
        self._fail()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


class AiApiTestCase(unittest.TestCase):
    def setUp(self):
        _truncate_all()
        app.dependency_overrides.pop(get_ai_provider, None)

    def tearDown(self):
        _truncate_all()
        app.dependency_overrides.pop(get_ai_provider, None)

    def _seed_run(self, seed=42, num_records=100):
        dataset_id = client.post("/datasets/demo", json={"seed": seed, "num_records": num_records}).json()[
            "dataset_id"
        ]
        run = client.post("/reconciliation/runs", json={"dataset_id": dataset_id}).json()
        return run["run_id"]

    def _first_exception_id(self, run_id, **filters):
        params = {"run_id": run_id, **filters}
        exceptions = client.get("/exceptions", params=params).json()
        self.assertGreater(len(exceptions), 0, f"no exceptions found for filters {filters}")
        return exceptions[0]["id"]


class ProviderUnavailableTests(AiApiTestCase):
    def test_real_provider_with_no_api_key_is_unavailable(self):
        provider = AnthropicAIProvider(api_key=None)
        self.assertFalse(provider.available)
        result = provider.explain_exception({"exception_type": "amount_mismatch"})
        self.assertFalse(result.available)
        self.assertIn("not configured", result.error)

    def test_missing_api_key_across_all_methods(self):
        provider = AnthropicAIProvider(api_key=None)
        for method in (
            lambda: provider.explain_exception({}),
            lambda: provider.recommend_resolution({}),
            lambda: provider.answer_query("q", "intent", {}),
            lambda: provider.summarize_reconciliation({}),
        ):
            result = method()
            self.assertFalse(result.available)

    def test_explain_endpoint_degrades_gracefully_without_key(self):
        run_id = self._seed_run()
        exc_id = self._first_exception_id(run_id, exception_type="amount_mismatch")
        app.dependency_overrides[get_ai_provider] = lambda: AnthropicAIProvider(api_key=None)

        resp = client.post(f"/ai/exceptions/{exc_id}/explain")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ai_available"])
        self.assertIsNotNone(body["error"])
        self.assertIsNotNone(body["facts"])

    def test_dashboard_and_reconciliation_unaffected_by_missing_ai_key(self):
        run_id = self._seed_run()
        self.assertEqual(client.get("/dashboard/summary").status_code, 200)
        self.assertEqual(client.get(f"/reconciliation/runs/{run_id}/results").status_code, 200)
        self.assertEqual(client.get("/exceptions", params={"run_id": run_id}).status_code, 200)


class ExceptionExplanationTests(AiApiTestCase):
    def test_explain_exception_uses_backend_derived_facts(self):
        run_id = self._seed_run()
        exc_id = self._first_exception_id(run_id, exception_type="amount_mismatch")

        mock = MockAIProvider(
            structured={
                "explanation": "The settlement amount differs from the expected payout.",
                "likely_cause": "Partial fee miscalculation upstream.",
                "recommended_next_action": "Request info from the settlement provider.",
                "uncertainty_note": None,
            }
        )
        app.dependency_overrides[get_ai_provider] = lambda: mock

        resp = client.post(f"/ai/exceptions/{exc_id}/explain")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertTrue(body["ai_available"])
        self.assertTrue(body["ai_generated"])
        self.assertEqual(body["explanation"], "The settlement amount differs from the expected payout.")
        # Facts passed to the mock must be backend-derived, matching the
        # exception's real persisted fields, not invented by the AI.
        self.assertEqual(len(mock.calls), 1)
        facts = mock.calls[0][1]
        self.assertEqual(facts["exception_type"], "amount_mismatch")
        detail = client.get(f"/exceptions/{exc_id}").json()
        self.assertEqual(facts["financial_impact"], detail["exception"]["financial_impact"])

    def test_explain_exception_not_found(self):
        app.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
        resp = client.post("/ai/exceptions/does-not-exist/explain")
        self.assertEqual(resp.status_code, 404)

    def test_recommend_resolution(self):
        run_id = self._seed_run()
        exc_id = self._first_exception_id(run_id, exception_type="fee_mismatch")
        mock = MockAIProvider(structured={"recommended_action": "auto_resolve", "rationale": "Small fee delta."})
        app.dependency_overrides[get_ai_provider] = lambda: mock

        resp = client.post(f"/ai/exceptions/{exc_id}/recommend")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["recommended_action"], "auto_resolve")


class ControllerQueryTests(AiApiTestCase):
    def test_numerical_query_answer_uses_backend_value_not_ai_computed_one(self):
        run_id = self._seed_run()
        summary = client.get("/dashboard/summary", params={"run_id": run_id}).json()
        at_risk = summary["amount_at_risk"]

        mock = MockAIProvider(structured={"answer": f"Currently, {at_risk} is classified as at risk.", "caveats": None})
        app.dependency_overrides[get_ai_provider] = lambda: mock

        resp = client.post("/ai/query", json={"question": "How much money is at risk?", "run_id": run_id})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["intent"], "amount_at_risk")
        self.assertTrue(body["ai_available"])
        self.assertEqual(body["facts"]["amount_at_risk"], at_risk)
        self.assertIn(at_risk, body["answer"])

    def test_unsupported_question_never_calls_provider(self):
        run_id = self._seed_run()
        app.dependency_overrides[get_ai_provider] = lambda: NeverCalledProvider()

        resp = client.post("/ai/query", json={"question": "What is the weather today?", "run_id": run_id})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["intent"], "unsupported")
        self.assertFalse(body["ai_generated"])
        self.assertIn("reconciliation data", body["answer"])

    def test_transaction_level_question_routes_to_explain_transaction(self):
        run_id = self._seed_run()
        first_txn = client.get(f"/reconciliation/runs/{run_id}/results").json()[0]["payment_reference"]
        mock = MockAIProvider(structured={"answer": "Explained.", "caveats": None})
        app.dependency_overrides[get_ai_provider] = lambda: mock

        resp = client.post("/ai/query", json={"question": f"Why was transaction {first_txn} not reconciled?", "run_id": run_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["intent"], "explain_transaction")


class ReconciliationSummaryTests(AiApiTestCase):
    def test_summary_uses_real_dashboard_facts(self):
        run_id = self._seed_run()
        summary = client.get("/dashboard/summary", params={"run_id": run_id}).json()
        mock = MockAIProvider(structured={
            "summary": "Run completed with several exceptions.",
            "largest_exception_categories": "missing_settlement, partial_settlement",
            "financial_exposure_note": "Exposure is moderate.",
            "unresolved_cases_note": "Several cases remain open.",
            "suggested_focus": "Prioritize missing settlements.",
        })
        app.dependency_overrides[get_ai_provider] = lambda: mock

        resp = client.post(f"/ai/runs/{run_id}/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ai_available"])
        self.assertEqual(body["facts"]["summary"]["total_transactions"], summary["total_transactions"])

    def test_summary_not_found_for_unknown_run(self):
        app.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
        resp = client.post("/ai/runs/does-not-exist/summary")
        self.assertEqual(resp.status_code, 404)


class HallucinationPreventionTests(AiApiTestCase):
    def test_fabricated_number_is_discarded_not_shown(self):
        run_id = self._seed_run()
        exc_id = self._first_exception_id(run_id, exception_type="amount_mismatch")

        # This financial figure does not appear anywhere in the facts
        # the mock was handed - a stand-in for a hallucinated number.
        mock = MockAIProvider(
            structured={
                "explanation": "The customer was overcharged by 987654.32 rupees due to a system error.",
                "likely_cause": "Unknown",
                "recommended_next_action": "Investigate",
                "uncertainty_note": None,
            }
        )
        app.dependency_overrides[get_ai_provider] = lambda: mock

        resp = client.post(f"/ai/exceptions/{exc_id}/explain")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertFalse(body["ai_available"])
        self.assertFalse(body["ai_generated"])
        self.assertIn("987654.32", body["error"])
        self.assertIsNone(body["explanation"])

    def test_number_present_in_facts_is_not_flagged(self):
        run_id = self._seed_run()
        exc_id = self._first_exception_id(run_id, exception_type="amount_mismatch")
        detail = client.get(f"/exceptions/{exc_id}").json()
        real_impact = detail["exception"]["financial_impact"]

        mock = MockAIProvider(
            structured={
                "explanation": f"The financial impact of this exception is {real_impact}.",
                "likely_cause": "Rounding difference.",
                "recommended_next_action": "Request info.",
                "uncertainty_note": None,
            }
        )
        app.dependency_overrides[get_ai_provider] = lambda: mock

        resp = client.post(f"/ai/exceptions/{exc_id}/explain")
        body = resp.json()
        self.assertTrue(body["ai_available"])
        self.assertIn(real_impact, body["explanation"])


class StructuredDataRetrievalTests(AiApiTestCase):
    """Direct unit tests on app.ai.facts — the deterministic,
    allowlisted layer the AI is only ever allowed to see."""

    def test_exception_counts_by_type_matches_total_exceptions(self):
        run_id = self._seed_run()
        with _TestSessionLocal() as db:
            counts = ai_facts.exception_counts_by_type(db, run_id)
            summary = ai_facts.dashboard_summary(db, run_id)
        self.assertEqual(sum(counts["counts_by_type"].values()), summary["exceptions"])

    def test_unresolved_high_severity_only_includes_open_high_severity(self):
        run_id = self._seed_run()
        with _TestSessionLocal() as db:
            result = ai_facts.unresolved_high_severity(db, run_id)
        for item in result["items"]:
            self.assertIn(item["severity"], ("high", "critical"))
            self.assertIn(item["review_status"], ("pending", "in_review"))

    def test_exception_rate_by_payment_method_is_bounded(self):
        run_id = self._seed_run()
        with _TestSessionLocal() as db:
            result = ai_facts.exception_rate_by_payment_method(db, run_id)
        for rate in result["exception_rate_by_method"].values():
            self.assertGreaterEqual(rate, 0.0)
            self.assertLessEqual(rate, 1.0)

    def test_explain_transaction_raises_not_found_for_unknown_transaction(self):
        from app.services.errors import NotFoundError

        run_id = self._seed_run()
        with _TestSessionLocal() as db:
            with self.assertRaises(NotFoundError):
                ai_facts.explain_transaction(db, run_id, "TXN-DOES-NOT-EXIST")

    def test_facts_are_json_serializable(self):
        import json

        run_id = self._seed_run()
        with _TestSessionLocal() as db:
            payload = {
                "summary": ai_facts.dashboard_summary(db, run_id),
                "by_type": ai_facts.exception_counts_by_type(db, run_id),
                "by_severity": ai_facts.exception_counts_by_severity(db, run_id),
                "by_method": ai_facts.exception_rate_by_payment_method(db, run_id),
                "auto_resolved": ai_facts.auto_resolved_count(db, run_id),
                "high_severity": ai_facts.unresolved_high_severity(db, run_id),
            }
        json.dumps(payload)  # must not raise


if __name__ == "__main__":
    unittest.main()
