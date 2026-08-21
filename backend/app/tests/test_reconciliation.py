import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.data_generation.config import GeneratorConfig
from app.data_generation.enums import GroundTruthCondition
from app.data_generation.generator import generate_dataset
from app.models.enums import (
    Currency,
    ExceptionType,
    MatchStatus,
    MatchStrategy,
    PaymentMethod,
    PaymentStatus,
    SettlementStatus,
)
from app.models.payment import Payment
from app.models.settlement import Settlement
from app.reconciliation.config import ReconciliationConfig
from app.reconciliation.engine import reconcile

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
CREATED_AT = datetime(2026, 1, 1, 0, 0, 0)


def _payment(txn_id="TXN-1", amount="1000.00", order_id="ORD-1", created_at=CREATED_AT):
    return Payment(
        id=f"pay-{txn_id}",
        transaction_id=txn_id,
        order_id=order_id,
        customer_reference="CUST-1",
        amount=Decimal(amount),
        currency=Currency.INR,
        payment_method=PaymentMethod.UPI,
        payment_status=PaymentStatus.CAPTURED,
        created_at=created_at,
    )


def _settlement(settlement_id, reference, settled_amount, fee="20.00", tax="3.60", settled_at=None, status=SettlementStatus.SETTLED):
    return Settlement(
        id=f"stl-{settlement_id}",
        settlement_id=settlement_id,
        transaction_reference=reference,
        settled_amount=Decimal(settled_amount),
        fee=Decimal(fee),
        tax=Decimal(tax),
        settlement_status=status,
        settled_at=settled_at or (CREATED_AT + timedelta(hours=2)),
    )


class ExactMatchTests(unittest.TestCase):
    def test_exact_match(self):
        payment = _payment(amount="1000.00")
        settlement = _settlement("STL-1", "TXN-1", "976.40")  # 1000 - 20 fee - 3.60 tax
        report = reconcile([payment], [settlement], now=NOW)

        self.assertEqual(len(report.results), 1)
        result = report.results[0]
        self.assertEqual(result.match_status, MatchStatus.MATCHED)
        self.assertEqual(result.match_strategy, MatchStrategy.EXACT_REFERENCE)
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.amount_difference, Decimal("0.00"))
        self.assertEqual(len(report.exceptions), 0)


class ReferenceOrderAmountTests(unittest.TestCase):
    def test_reference_amount_mismatch(self):
        payment = _payment(amount="1000.00")
        # expected net 976.40, off by 20.00
        settlement = _settlement("STL-1", "TXN-1", "996.40")
        report = reconcile([payment], [settlement], now=NOW)

        result = report.results[0]
        self.assertEqual(result.match_status, MatchStatus.MATCHED)
        self.assertEqual(result.match_strategy, MatchStrategy.REFERENCE_AMOUNT)
        self.assertEqual(result.amount_difference, Decimal("20.00"))
        self.assertEqual(len(report.exceptions), 1)
        self.assertEqual(report.exceptions[0].exception_type, ExceptionType.AMOUNT_MISMATCH)


class TimestampToleranceTests(unittest.TestCase):
    def test_delayed_settlement_within_reference_match(self):
        payment = _payment(amount="1000.00")
        settlement = _settlement("STL-1", "TXN-1", "976.40", settled_at=CREATED_AT + timedelta(days=15))
        report = reconcile([payment], [settlement], now=NOW)

        result = report.results[0]
        self.assertEqual(result.match_status, MatchStatus.MATCHED)
        self.assertEqual(result.match_strategy, MatchStrategy.TIMESTAMP_TOLERANCE)
        self.assertEqual(len(report.exceptions), 1)
        self.assertEqual(report.exceptions[0].exception_type, ExceptionType.DELAYED_SETTLEMENT)

    def test_configurable_tolerance_changes_outcome(self):
        payment = _payment(amount="1000.00")
        settlement = _settlement("STL-1", "TXN-1", "976.40", settled_at=CREATED_AT + timedelta(hours=100))
        strict_config = ReconciliationConfig(delayed_settlement_threshold=timedelta(hours=48))
        lenient_config = ReconciliationConfig(delayed_settlement_threshold=timedelta(hours=200))

        strict_report = reconcile([payment], [settlement], config=strict_config, now=NOW)
        lenient_report = reconcile([payment], [settlement], config=lenient_config, now=NOW)

        self.assertEqual(len(strict_report.exceptions), 1)
        self.assertEqual(len(lenient_report.exceptions), 0)


class AmountMismatchTests(unittest.TestCase):
    def test_fee_mismatch_detected_over_amount_mismatch(self):
        payment = _payment(amount="1000.00")
        # fee doubled to 40.00, tax recomputed on wrong fee -> settled = 1000 - 40 - 7.20 = 952.80
        settlement = _settlement("STL-1", "TXN-1", "952.80", fee="40.00", tax="7.20")
        report = reconcile([payment], [settlement], now=NOW)

        self.assertEqual(len(report.exceptions), 1)
        self.assertEqual(report.exceptions[0].exception_type, ExceptionType.FEE_MISMATCH)


class MissingSettlementTests(unittest.TestCase):
    def test_missing_settlement(self):
        payment = _payment()
        report = reconcile([payment], [], now=NOW)

        result = report.results[0]
        self.assertEqual(result.match_status, MatchStatus.UNMATCHED)
        self.assertIsNone(result.settlement_reference)
        self.assertEqual(len(report.exceptions), 1)
        self.assertEqual(report.exceptions[0].exception_type, ExceptionType.MISSING_SETTLEMENT)


class DuplicateSettlementTests(unittest.TestCase):
    def test_duplicate_settlement(self):
        payment = _payment(amount="1000.00")
        s1 = _settlement("STL-1", "TXN-1", "976.40", settled_at=CREATED_AT + timedelta(hours=2))
        s2 = _settlement("STL-2", "TXN-1", "976.40", settled_at=CREATED_AT + timedelta(hours=5))
        report = reconcile([payment], [s1, s2], now=NOW)

        self.assertEqual(len(report.results), 2)
        statuses = {r.settlement_reference: r.match_status for r in report.results}
        self.assertEqual(statuses["STL-1"], MatchStatus.MATCHED)
        self.assertEqual(statuses["STL-2"], MatchStatus.DUPLICATE)
        dup_exceptions = [e for e in report.exceptions if e.exception_type == ExceptionType.DUPLICATE_SETTLEMENT]
        self.assertEqual(len(dup_exceptions), 1)


class PartialSettlementTests(unittest.TestCase):
    def test_partial_settlement(self):
        payment = _payment(amount="1000.00")
        # expected net 976.40; settle only 50% of it
        settlement = _settlement("STL-1", "TXN-1", "488.20")
        report = reconcile([payment], [settlement], now=NOW)

        result = report.results[0]
        self.assertEqual(result.match_status, MatchStatus.PARTIAL)
        self.assertEqual(report.exceptions[0].exception_type, ExceptionType.PARTIAL_SETTLEMENT)


class InvalidReferenceTests(unittest.TestCase):
    def test_invalid_reference_orphan_settlement(self):
        payment = _payment(txn_id="TXN-1")
        orphan = _settlement("STL-9", "TXN-DOES-NOT-EXIST", "500.00")
        report = reconcile([payment], [orphan], now=NOW)

        # payment itself is unmatched (missing settlement) + orphan settlement is unresolved
        statuses = [r.match_status for r in report.results]
        self.assertIn(MatchStatus.UNMATCHED, statuses)
        exception_types = {e.exception_type for e in report.exceptions}
        self.assertIn(ExceptionType.INVALID_REFERENCE, exception_types)
        self.assertIn(ExceptionType.MISSING_SETTLEMENT, exception_types)


class UnresolvedTests(unittest.TestCase):
    def test_unresolved_transaction_has_no_strategy(self):
        payment = _payment()
        report = reconcile([payment], [], now=NOW)
        self.assertIsNone(report.results[0].match_strategy)


class DeterminismTests(unittest.TestCase):
    def test_deterministic_output(self):
        payment = _payment(amount="1000.00")
        settlement = _settlement("STL-1", "TXN-1", "976.40")

        first = reconcile([payment], [settlement], now=NOW)
        second = reconcile([payment], [settlement], now=NOW)

        self.assertEqual(
            [r.to_dict() for r in first.results],
            [r.to_dict() for r in second.results],
        )
        self.assertEqual(
            [e.to_dict() for e in first.exceptions],
            [e.to_dict() for e in second.exceptions],
        )

    def test_deterministic_against_seeded_demo_dataset(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        first = reconcile(bundle.payments, bundle.settlements, now=NOW)
        second = reconcile(bundle.payments, bundle.settlements, now=NOW)
        self.assertEqual(
            [r.to_dict() for r in first.results],
            [r.to_dict() for r in second.results],
        )


class SeededDatasetCoverageTests(unittest.TestCase):
    """Sanity-check the engine against Phase 1's seeded demo dataset:
    every ground-truth anomaly condition should surface as at least one
    corresponding exception (the engine never reads ground truth
    itself, this test just uses it to check coverage)."""

    def test_all_conditions_produce_expected_exception_types(self):
        bundle = generate_dataset(GeneratorConfig(seed=42, num_records=250))
        report = reconcile(bundle.payments, bundle.settlements, now=NOW)
        found_exception_types = {e.exception_type for e in report.exceptions}

        expected = {
            GroundTruthCondition.MISSING_SETTLEMENT: ExceptionType.MISSING_SETTLEMENT,
            GroundTruthCondition.DUPLICATE_SETTLEMENT: ExceptionType.DUPLICATE_SETTLEMENT,
            GroundTruthCondition.AMOUNT_MISMATCH: ExceptionType.AMOUNT_MISMATCH,
            GroundTruthCondition.FEE_MISMATCH: ExceptionType.FEE_MISMATCH,
            GroundTruthCondition.DELAYED_SETTLEMENT: ExceptionType.DELAYED_SETTLEMENT,
            GroundTruthCondition.INVALID_REFERENCE: ExceptionType.INVALID_REFERENCE,
        }
        for condition, exception_type in expected.items():
            present = any(g.condition == condition for g in bundle.ground_truth)
            self.assertTrue(present, f"seeded dataset missing condition {condition}")
            self.assertIn(
                exception_type, found_exception_types,
                f"engine never raised {exception_type} despite seeded {condition} cases",
            )

        normal_matches = [
            r for r in report.results
            if r.match_status == MatchStatus.MATCHED and r.match_strategy == MatchStrategy.EXACT_REFERENCE
        ]
        self.assertGreater(len(normal_matches), 0)


if __name__ == "__main__":
    unittest.main()
