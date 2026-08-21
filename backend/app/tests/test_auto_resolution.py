import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.auto_resolution.config import AutoResolutionConfig
from app.auto_resolution.engine import auto_resolve
from app.models.enums import ExceptionType, RecommendedAction, ResolutionType, ReviewStatus, Severity
from app.models.exception_case import ExceptionCase

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _exception(
    exception_type,
    financial_impact="0.00",
    auto_resolvable=True,
    review_status=ReviewStatus.PENDING,
    exc_id="exc-1",
    severity=Severity.LOW,
):
    return ExceptionCase(
        id=exc_id,
        reconciliation_result_id="result-1",
        exception_type=exception_type,
        severity=severity,
        confidence=0.8,
        financial_impact=Decimal(financial_impact),
        recommended_action=RecommendedAction.AUTO_RESOLVE if auto_resolvable else RecommendedAction.ESCALATE,
        auto_resolvable=auto_resolvable,
        review_status=review_status,
        created_at=NOW,
    )


class AutoResolvableExceptionTests(unittest.TestCase):
    def test_fee_mismatch_within_cap_is_auto_resolved(self):
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="10.00")
        report = auto_resolve([exc], now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 1)
        self.assertEqual(report.resolved_exceptions[0].review_status, ReviewStatus.AUTO_RESOLVED)
        self.assertEqual(len(report.records), 1)
        self.assertEqual(report.records[0].resolution_type, ResolutionType.FEE_ADJUSTMENT_ACCEPTED)

    def test_delayed_settlement_is_auto_resolved(self):
        exc = _exception(ExceptionType.DELAYED_SETTLEMENT, financial_impact="0.00")
        report = auto_resolve([exc], now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 1)
        self.assertEqual(report.records[0].resolution_type, ResolutionType.DELAY_ACCEPTED)

    def test_exact_duplicate_settlement_is_auto_resolved(self):
        exc = _exception(ExceptionType.DUPLICATE_SETTLEMENT, financial_impact="0.00")
        report = auto_resolve([exc], now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 1)
        self.assertEqual(report.records[0].resolution_type, ResolutionType.DUPLICATE_SUPPRESSED)


class NonAutoResolvableExceptionTests(unittest.TestCase):
    def test_missing_settlement_is_never_auto_resolved(self):
        exc = _exception(ExceptionType.MISSING_SETTLEMENT, financial_impact="500.00", auto_resolvable=False)
        report = auto_resolve([exc], now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 0)
        self.assertEqual(len(report.unresolved_exceptions), 1)
        self.assertEqual(len(report.records), 0)

    def test_partial_settlement_is_never_auto_resolved(self):
        exc = _exception(ExceptionType.PARTIAL_SETTLEMENT, financial_impact="300.00", auto_resolvable=False)
        report = auto_resolve([exc], now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 0)

    def test_amount_mismatch_is_never_auto_resolved(self):
        exc = _exception(ExceptionType.AMOUNT_MISMATCH, financial_impact="20.00", auto_resolvable=False)
        report = auto_resolve([exc], now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 0)

    def test_invalid_reference_is_never_auto_resolved(self):
        exc = _exception(ExceptionType.INVALID_REFERENCE, financial_impact="500.00", auto_resolvable=False)
        report = auto_resolve([exc], now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 0)


class HighImpactExceptionTests(unittest.TestCase):
    def test_fee_mismatch_above_cap_is_escalated_not_resolved(self):
        config = AutoResolutionConfig(max_auto_fee_adjustment=Decimal("100.00"))
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="250.00")
        report = auto_resolve([exc], config=config, now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 0)
        self.assertEqual(len(report.unresolved_exceptions), 1)
        self.assertEqual(report.unresolved_exceptions[0].review_status, ReviewStatus.PENDING)

    def test_duplicate_settlement_with_mismatched_amount_is_not_auto_resolved(self):
        # Different amount between the "duplicate" and the original ->
        # possibly a real second transaction, not a safe auto-suppress.
        exc = _exception(ExceptionType.DUPLICATE_SETTLEMENT, financial_impact="150.00")
        report = auto_resolve([exc], now=NOW)

        self.assertEqual(len(report.resolved_exceptions), 0)


class AuditRecordCreationTests(unittest.TestCase):
    def test_record_captures_required_fields(self):
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="10.00", exc_id="exc-42")
        report = auto_resolve([exc], now=NOW)
        record = report.records[0]

        self.assertEqual(record.exception_case_id, "exc-42")
        self.assertEqual(record.resolution_type, ResolutionType.FEE_ADJUSTMENT_ACCEPTED)
        self.assertTrue(record.reason)
        self.assertEqual(record.actor, "system:auto_resolution_engine")
        self.assertEqual(record.created_at, NOW)
        self.assertEqual(record.financial_impact, Decimal("10.00"))
        self.assertEqual(record.previous_status, ReviewStatus.PENDING)
        self.assertEqual(record.new_status, ReviewStatus.AUTO_RESOLVED)


class IdempotentResolutionTests(unittest.TestCase):
    def test_rerunning_over_already_resolved_exceptions_is_a_no_op(self):
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="10.00")
        first = auto_resolve([exc], now=NOW)
        self.assertEqual(len(first.records), 1)

        second = auto_resolve(first.resolved_exceptions, now=NOW)

        self.assertEqual(len(second.records), 0)
        self.assertEqual(len(second.resolved_exceptions), 0)
        self.assertEqual(len(second.unresolved_exceptions), 1)
        self.assertEqual(second.unresolved_exceptions[0].review_status, ReviewStatus.AUTO_RESOLVED)

    def test_deterministic_record_ids_across_runs(self):
        exc = _exception(ExceptionType.FEE_MISMATCH, financial_impact="10.00")
        first = auto_resolve([exc], now=NOW)
        second = auto_resolve([exc], now=NOW)

        self.assertEqual(first.records[0].id, second.records[0].id)


if __name__ == "__main__":
    unittest.main()
