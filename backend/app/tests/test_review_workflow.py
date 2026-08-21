import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.models.enums import ExceptionType, RecommendedAction, ReviewStatus, Severity
from app.models.exception_case import ExceptionCase
from app.review.workflow import add_note, approve, mark_resolved, reject, start_review

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _exception(review_status=ReviewStatus.PENDING):
    return ExceptionCase(
        id="exc-1",
        reconciliation_result_id="result-1",
        exception_type=ExceptionType.AMOUNT_MISMATCH,
        severity=Severity.MEDIUM,
        confidence=0.75,
        financial_impact=Decimal("20.00"),
        recommended_action=RecommendedAction.REQUEST_INFO,
        auto_resolvable=False,
        review_status=review_status,
        created_at=NOW,
    )


class ReviewApprovalTests(unittest.TestCase):
    def test_approve_sets_status_and_creates_audit(self):
        exc = _exception()
        updated, audit = approve(exc, reviewer="anmol@razorpay.com", note="looks correct", now=NOW)

        self.assertEqual(updated.review_status, ReviewStatus.APPROVED)
        self.assertEqual(audit.exception_case_id, "exc-1")
        self.assertEqual(audit.reviewer, "anmol@razorpay.com")
        self.assertEqual(audit.decision, ReviewStatus.APPROVED)
        self.assertEqual(audit.notes, "looks correct")
        self.assertEqual(audit.created_at, NOW)

    def test_original_exception_is_not_mutated(self):
        exc = _exception()
        approve(exc, reviewer="anmol@razorpay.com", now=NOW)
        self.assertEqual(exc.review_status, ReviewStatus.PENDING)


class ReviewRejectionTests(unittest.TestCase):
    def test_reject_sets_status_and_creates_audit(self):
        exc = _exception()
        updated, audit = reject(exc, reviewer="anmol@razorpay.com", note="not a real mismatch", now=NOW)

        self.assertEqual(updated.review_status, ReviewStatus.REJECTED)
        self.assertEqual(audit.decision, ReviewStatus.REJECTED)
        self.assertEqual(audit.notes, "not a real mismatch")


class MarkResolvedTests(unittest.TestCase):
    def test_mark_resolved_sets_approved_status(self):
        exc = _exception()
        updated, audit = mark_resolved(exc, reviewer="anmol@razorpay.com", now=NOW)

        self.assertEqual(updated.review_status, ReviewStatus.APPROVED)
        self.assertEqual(audit.decision, ReviewStatus.APPROVED)
        self.assertTrue(audit.notes)


class AddNoteTests(unittest.TestCase):
    def test_add_note_does_not_change_status(self):
        exc = _exception(review_status=ReviewStatus.IN_REVIEW)
        updated, audit = add_note(exc, reviewer="anmol@razorpay.com", note="checking with finance", now=NOW)

        self.assertEqual(updated.review_status, ReviewStatus.IN_REVIEW)
        self.assertEqual(audit.decision, ReviewStatus.IN_REVIEW)
        self.assertEqual(audit.notes, "checking with finance")


class StartReviewTests(unittest.TestCase):
    def test_start_review_moves_pending_to_in_review(self):
        exc = _exception(review_status=ReviewStatus.PENDING)
        updated, _audit = start_review(exc, reviewer="anmol@razorpay.com", now=NOW)
        self.assertEqual(updated.review_status, ReviewStatus.IN_REVIEW)


class AuditRecordCreationTests(unittest.TestCase):
    def test_each_action_produces_a_distinct_audit_record(self):
        exc = _exception()
        _u1, a1 = approve(exc, reviewer="r1", now=NOW)
        _u2, a2 = reject(exc, reviewer="r2", now=NOW)

        self.assertNotEqual(a1.id, a2.id)
        self.assertEqual(a1.exception_case_id, a2.exception_case_id)


if __name__ == "__main__":
    unittest.main()
