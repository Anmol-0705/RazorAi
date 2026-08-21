"""Deterministic scoring of reconciliation output against ground truth.

Pure functions only — no DB, no I/O, no randomness. Given the same
ground truth, results, and exceptions, `score()` always returns the
same metrics. This module never re-implements matching: it only reads
the `match_status`/`exception_type` the production reconciliation
engine already produced (via `app.reconciliation.engine.reconcile`,
called unmodified by `app.evaluation.service`).

## The D009 boundary

`amount_mismatch` and `partial_settlement` are observationally
indistinguishable for a documented subset of small-amount transactions
(DECISIONS.md D009): both conditions manifest only as "settled_amount
differs from expected", and `Settlement.fee`/`.tax` are identical in
both of the generator's code paths for them, so no feature available
to the reconciliation engine can separate them with certainty in every
case. Rather than score them as strictly separate classes (which would
report a "classification error" for a case that is not actually
distinguishable, overstating a real defect) or silently merge them in
the ground truth (which would hide the ambiguity), this scorer treats
{amount_mismatch, partial_settlement} as one equivalence class for
per-class correctness: a prediction of either type counts as correct
when the ground truth condition is either of the two. The exact count
of "boundary disagreements" (predicted the other label within the
pair) is still reported separately, never hidden.

## D008: invalid_reference's expected prediction

A ground-truth `invalid_reference` condition is applied to the
*payment* whose real settlement was misdirected to an orphan reference
generated independently at random (see the generator: the corrupted
reference does not correspond to any real payment index). From that
payment's own perspective there is no settlement at all — the engine
correctly reports it as `missing_settlement`, not `invalid_reference`
(the orphan settlement itself produces a *separate*, unlabeled
reconciliation result that isn't scored here, since it doesn't
correspond to any ground-truth payment record). This is the same,
already-documented system behavior as DECISIONS.md D008 — the expected
per-class label below encodes it explicitly rather than scoring it as
a mysterious "wrong" prediction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

NORMAL_MATCH = "normal_match"
OPEN_REVIEW_STATUSES = {"pending", "in_review"}
RECONCILED_MATCH_STATUSES = {"matched", "partial"}

# Exception types the auto-resolution engine ever considers safe to
# resolve automatically (see backend/app/auto_resolution/engine.py) —
# reused here only as a *reference set* for scoring, never as new
# matching/resolution logic.
AUTO_RESOLVABLE_CONDITIONS = {"fee_mismatch", "delayed_settlement", "duplicate_settlement"}

# The one documented, genuinely ambiguous pair (DECISIONS.md D009).
D009_BOUNDARY_TYPES = frozenset({"amount_mismatch", "partial_settlement"})

# What the production engine is expected to output for each ground
# truth condition, per its own documented, deterministic rules
# (DECISIONS.md D008/D009). `None` means "no exception expected".
EXPECTED_EXCEPTION_TYPES: dict[str, Optional[frozenset]] = {
    "normal_match": None,
    "missing_settlement": frozenset({"missing_settlement"}),
    "duplicate_settlement": frozenset({"duplicate_settlement"}),
    "amount_mismatch": D009_BOUNDARY_TYPES,
    "partial_settlement": D009_BOUNDARY_TYPES,
    "fee_mismatch": frozenset({"fee_mismatch"}),
    "delayed_settlement": frozenset({"delayed_settlement"}),
    "invalid_reference": frozenset({"missing_settlement"}),
}


def _safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def _f1(precision: Optional[float], recall: Optional[float]) -> Optional[float]:
    if precision is None or recall is None or (precision + recall) == 0:
        return None
    return 2 * precision * recall / (precision + recall)


@dataclass
class ConfusionCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def precision(self) -> Optional[float]:
        return _safe_div(self.tp, self.tp + self.fp)

    def recall(self) -> Optional[float]:
        return _safe_div(self.tp, self.tp + self.fn)

    def f1(self) -> Optional[float]:
        return _f1(self.precision(), self.recall())

    def to_dict(self) -> dict:
        return {
            "true_positive": self.tp,
            "false_positive": self.fp,
            "false_negative": self.fn,
            "true_negative": self.tn,
            "precision": self.precision(),
            "recall": self.recall(),
            "f1": self.f1(),
        }


@dataclass
class EvaluationMetrics:
    total_records: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    match_rate: Optional[float] = None
    match_confusion: ConfusionCounts = field(default_factory=ConfusionCounts)

    exception_confusion: ConfusionCounts = field(default_factory=ConfusionCounts)
    unresolved_exception_count: int = 0

    classified_cases: int = 0
    classified_correct: int = 0
    boundary_cases: int = 0
    boundary_correct: int = 0

    eligible_count: int = 0
    auto_resolved_count: int = 0
    correctly_auto_resolved_count: int = 0
    unsafe_auto_resolved_count: int = 0
    auto_resolution_eligible_ground_truth: int = 0
    unresolved_after_automation: int = 0

    total_amount_processed: Decimal = Decimal("0.00")
    total_amount_reconciled: Decimal = Decimal("0.00")
    amount_at_risk: Decimal = Decimal("0.00")
    amount_unresolved: Decimal = Decimal("0.00")

    def exception_type_accuracy(self) -> Optional[float]:
        return _safe_div(self.classified_correct, self.classified_cases)

    def boundary_agreement_rate(self) -> Optional[float]:
        return _safe_div(self.boundary_correct, self.boundary_cases)

    def auto_resolution_precision(self) -> Optional[float]:
        return _safe_div(self.correctly_auto_resolved_count, self.auto_resolved_count)

    def auto_resolution_recall(self) -> Optional[float]:
        return _safe_div(self.correctly_auto_resolved_count, self.auto_resolution_eligible_ground_truth)

    def to_dict(self) -> dict:
        return {
            "reconciliation": {
                "total_records": self.total_records,
                "matched_count": self.matched_count,
                "unmatched_count": self.unmatched_count,
                "match_rate": self.match_rate,
                "precision": self.match_confusion.precision(),
                "recall": self.match_confusion.recall(),
                "f1": self.match_confusion.f1(),
                "confusion": self.match_confusion.to_dict(),
            },
            "exceptions": {
                "detection_precision": self.exception_confusion.precision(),
                "detection_recall": self.exception_confusion.recall(),
                "detection_f1": self.exception_confusion.f1(),
                "confusion": self.exception_confusion.to_dict(),
                "unresolved_exception_count": self.unresolved_exception_count,
                "exception_type_accuracy": self.exception_type_accuracy(),
                "exception_type_classified_cases": self.classified_cases,
                "exception_type_correct_cases": self.classified_correct,
                "d009_boundary_cases": self.boundary_cases,
                "d009_boundary_agreement_rate": self.boundary_agreement_rate(),
                "d009_note": (
                    "amount_mismatch and partial_settlement are observationally "
                    "indistinguishable for a subset of small-amount transactions "
                    "(DECISIONS.md D009); these two conditions are scored as one "
                    "equivalence class rather than reporting a false classification "
                    "error, and the exact disagreement count above is never hidden."
                ),
            },
            "auto_resolution": {
                "eligible_count": self.eligible_count,
                "auto_resolved_count": self.auto_resolved_count,
                "correctly_auto_resolved_count": self.correctly_auto_resolved_count,
                "unsafe_auto_resolved_count": self.unsafe_auto_resolved_count,
                "precision": self.auto_resolution_precision(),
                "recall": self.auto_resolution_recall(),
                "unresolved_after_automation": self.unresolved_after_automation,
            },
            "financial": {
                "total_amount_processed": str(self.total_amount_processed),
                "total_amount_reconciled": str(self.total_amount_reconciled),
                "amount_at_risk": str(self.amount_at_risk),
                "amount_unresolved": str(self.amount_unresolved),
            },
        }


def score(payments: list, results: list[dict], exceptions: list[dict], ground_truth: list[dict]) -> EvaluationMetrics:
    """
    `payments`: list of Payment dataclasses (the evaluated dataset).
    `results`: enriched reconciliation result dicts (as returned by
        `reconciliation_service.list_results` / `_enrich_results`) for
        the run under evaluation.
    `exceptions`: ExceptionCaseORM rows (or equivalent objects with the
        same attributes) for the same run.
    `ground_truth`: the loaded `ground_truth.json` records.
    """
    metrics = EvaluationMetrics()
    metrics.total_records = len(ground_truth)

    by_payment: dict[str, dict] = {}
    for r in results:
        entry = by_payment.setdefault(r["payment_reference"], {"match_statuses": set(), "exception_types": set()})
        entry["match_statuses"].add(r["match_status"])
    for e in exceptions:
        entry = by_payment.setdefault(e.payment_reference, {"match_statuses": set(), "exception_types": set()})
        entry["exception_types"].add(e.exception_type)

    metrics.total_amount_processed = sum((p.amount for p in payments), Decimal("0.00"))
    metrics.total_amount_reconciled = sum(
        (Decimal(r["settled_amount"]) for r in results if r["match_status"] in RECONCILED_MATCH_STATUSES and r["settled_amount"] is not None),
        Decimal("0.00"),
    )
    metrics.amount_at_risk = sum(
        (Decimal(e.financial_impact) for e in exceptions if e.review_status in OPEN_REVIEW_STATUSES),
        Decimal("0.00"),
    )
    metrics.amount_unresolved = metrics.amount_at_risk
    metrics.unresolved_exception_count = sum(1 for e in exceptions if e.review_status in OPEN_REVIEW_STATUSES)

    payment_condition: dict[str, str] = {}

    for gt in ground_truth:
        payment_id = gt["payment_transaction_id"]
        condition = gt["condition"]
        payment_condition[payment_id] = condition

        entry = by_payment.get(payment_id, {"match_statuses": set(), "exception_types": set()})
        is_anomaly_gt = condition != NORMAL_MATCH
        has_exception_pred = bool(entry["exception_types"])
        is_clean_match_pred = ("matched" in entry["match_statuses"]) and not has_exception_pred
        is_clean_match_gt = condition == NORMAL_MATCH

        if "matched" in entry["match_statuses"]:
            metrics.matched_count += 1
        if "unmatched" in entry["match_statuses"]:
            metrics.unmatched_count += 1

        if is_clean_match_gt and is_clean_match_pred:
            metrics.match_confusion.tp += 1
        elif (not is_clean_match_gt) and is_clean_match_pred:
            metrics.match_confusion.fp += 1
        elif is_clean_match_gt and (not is_clean_match_pred):
            metrics.match_confusion.fn += 1
        else:
            metrics.match_confusion.tn += 1

        if is_anomaly_gt and has_exception_pred:
            metrics.exception_confusion.tp += 1
        elif (not is_anomaly_gt) and has_exception_pred:
            metrics.exception_confusion.fp += 1
        elif is_anomaly_gt and (not has_exception_pred):
            metrics.exception_confusion.fn += 1
        else:
            metrics.exception_confusion.tn += 1

        if is_anomaly_gt:
            expected_types = EXPECTED_EXCEPTION_TYPES.get(condition)
            type_correct = bool(expected_types and (entry["exception_types"] & expected_types))
            if condition in D009_BOUNDARY_TYPES:
                metrics.boundary_cases += 1
                if type_correct:
                    metrics.boundary_correct += 1
            else:
                metrics.classified_cases += 1
                if type_correct:
                    metrics.classified_correct += 1

        if condition in AUTO_RESOLVABLE_CONDITIONS:
            metrics.auto_resolution_eligible_ground_truth += 1

    metrics.match_rate = _safe_div(metrics.matched_count, metrics.total_records)

    for e in exceptions:
        if e.auto_resolvable:
            metrics.eligible_count += 1
        if e.review_status == "auto_resolved":
            metrics.auto_resolved_count += 1
            gt_condition = payment_condition.get(e.payment_reference)
            if gt_condition in AUTO_RESOLVABLE_CONDITIONS:
                metrics.correctly_auto_resolved_count += 1
            else:
                metrics.unsafe_auto_resolved_count += 1

    metrics.unresolved_after_automation = metrics.eligible_count - metrics.auto_resolved_count

    return metrics
