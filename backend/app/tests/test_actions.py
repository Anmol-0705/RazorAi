import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.actions.engine import check_eligibility, execute_action
from app.models.enums import ActionType, ExceptionType, RecommendedAction, ReviewStatus, Severity
from app.models.exception_case import ExceptionCase

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _exception(
    exception_type,
    financial_impact="0.00",
    auto_resolvable=True,
    review_status=ReviewStatus.AUTO_RESOLVED,
    exc_id="exc-1",
):
    return ExceptionCase(
        id=exc_id,
        reconciliation_result_id="result-1",
        exception_type=exception_type,
        severity=Severity.LOW,
        confidence=0.8,
        financial_impact=Decimal(financial_impact),
        recommended_action=RecommendedAction.AUTO_RESOLVE if auto_resolvable else RecommendedAction.ESCALATE,
        auto_resolvable=auto_resolvable,
        review_status=review_status,
        created_at=NOW,
    )


class EligibleActionExecutionTests(unittest.TestCase):
    def test_fee_mismatch_within_cap_is_eligible_and_executes(self):
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="10.00")
        eligibility, record = execute_action(exc, now=NOW)

        self.assertTrue(eligibility.eligible)
        self.assertIsNotNone(record)
        self.assertEqual(record.action_type, ActionType.SETTLEMENT_ADJUSTMENT_INSTRUCTION)
        self.assertEqual(record.exception_case_id, "exc-1")
        self.assertEqual(record.status.value, "completed")
        self.assertTrue(record.resulting_reference.startswith("SYN-SAI-"))
        self.assertEqual(record.created_at, NOW)
        self.assertEqual(record.completed_at, NOW)

    def test_delayed_settlement_maps_to_followup_instruction(self):
        exc = _exception(ExceptionType.DELAYED_SETTLEMENT, financial_impact="0.00")
        eligibility, record = execute_action(exc, now=NOW)

        self.assertTrue(eligibility.eligible)
        self.assertEqual(record.action_type, ActionType.SETTLEMENT_FOLLOWUP_INSTRUCTION)
        self.assertTrue(record.resulting_reference.startswith("SYN-SFI-"))

    def test_exact_duplicate_settlement_maps_to_review_instruction(self):
        exc = _exception(ExceptionType.DUPLICATE_SETTLEMENT, financial_impact="0.00")
        eligibility, record = execute_action(exc, now=NOW)

        self.assertTrue(eligibility.eligible)
        self.assertEqual(record.action_type, ActionType.DUPLICATE_SETTLEMENT_REVIEW_INSTRUCTION)
        self.assertTrue(record.resulting_reference.startswith("SYN-DRI-"))

    def test_eligible_exception_already_pending_is_also_eligible(self):
        # The action engine's eligibility does not require the
        # exception to already be AUTO_RESOLVED — it reuses the same
        # type/impact bounds regardless of current workflow state.
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="5.00", review_status=ReviewStatus.PENDING)
        eligibility, record = execute_action(exc, now=NOW)
        self.assertTrue(eligibility.eligible)
        self.assertIsNotNone(record)


class NonEligibleActionTests(unittest.TestCase):
    def test_amount_mismatch_is_not_eligible(self):
        exc = _exception(ExceptionType.AMOUNT_MISMATCH, financial_impact="500.00", auto_resolvable=False)
        eligibility, record = execute_action(exc, now=NOW)

        self.assertFalse(eligibility.eligible)
        self.assertIsNone(record)
        self.assertIsNone(eligibility.action_type)
        self.assertIn("human review", eligibility.reason)

    def test_missing_settlement_is_not_eligible(self):
        exc = _exception(ExceptionType.MISSING_SETTLEMENT, financial_impact="1000.00", auto_resolvable=False)
        eligibility, record = execute_action(exc, now=NOW)
        self.assertFalse(eligibility.eligible)
        self.assertIsNone(record)


class HighImpactActionRejectionTests(unittest.TestCase):
    def test_fee_mismatch_above_cap_is_not_eligible(self):
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="500.00")
        eligibility, record = execute_action(exc, now=NOW)
        self.assertFalse(eligibility.eligible)
        self.assertIsNone(record)

    def test_duplicate_settlement_with_mismatched_amount_is_not_eligible(self):
        exc = _exception(ExceptionType.DUPLICATE_SETTLEMENT, financial_impact="50.00")
        eligibility, record = execute_action(exc, now=NOW)
        self.assertFalse(eligibility.eligible)
        self.assertIsNone(record)

    def test_human_rejected_exception_is_never_eligible_even_if_type_qualifies(self):
        exc = _exception(
            ExceptionType.FEE_MISMATCH, financial_impact="5.00", review_status=ReviewStatus.REJECTED
        )
        eligibility, record = execute_action(exc, now=NOW)
        self.assertFalse(eligibility.eligible)
        self.assertIsNone(record)
        self.assertEqual(eligibility.rule_id, "action_policy:human_rejected")


class IdempotencyTests(unittest.TestCase):
    def test_same_exception_produces_same_idempotency_key_across_calls(self):
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="10.00")
        _, record1 = execute_action(exc, now=NOW)
        _, record2 = execute_action(exc, now=datetime(2026, 6, 1, tzinfo=timezone.utc))

        self.assertEqual(record1.id, record2.id)
        self.assertEqual(record1.idempotency_key, record2.idempotency_key)
        self.assertEqual(record1.resulting_reference, record2.resulting_reference)

    def test_different_exceptions_produce_different_keys(self):
        exc_a = _exception(ExceptionType.FEE_MISMATCH, financial_impact="10.00", exc_id="exc-a")
        exc_b = _exception(ExceptionType.FEE_MISMATCH, financial_impact="10.00", exc_id="exc-b")
        _, record_a = execute_action(exc_a, now=NOW)
        _, record_b = execute_action(exc_b, now=NOW)
        self.assertNotEqual(record_a.id, record_b.id)

    def test_check_eligibility_has_no_side_effects_and_matches_execute_action(self):
        exc = _exception(ExceptionType.DELAYED_SETTLEMENT, financial_impact="0.00")
        preview = check_eligibility(exc)
        eligibility, _record = execute_action(exc, now=NOW)
        self.assertEqual(preview.eligible, eligibility.eligible)
        self.assertEqual(preview.action_type, eligibility.action_type)
        self.assertEqual(preview.rule_id, eligibility.rule_id)


if __name__ == "__main__":
    unittest.main()
