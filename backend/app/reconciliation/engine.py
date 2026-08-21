"""Deterministic reconciliation engine.

Pure business logic: takes Payment/Settlement records and produces
ReconciliationResult + ExceptionCase records. No FastAPI, no LLM, no
I/O. See ARCHITECTURE.md layer 2 and DECISIONS.md D001/D002.

Matching hierarchy (transparent, applied per payment):
  1. exact transaction/reference match — reference, amount, and
     timestamp all within tolerance -> normal match.
  2. reference + amount — reference matches but the settled amount
     deviates (amount mismatch / partial settlement / fee mismatch).
  3. reference + configurable timestamp tolerance — reference and
     amount are fine but the settlement arrived outside the normal
     window (delayed settlement).
  4. unresolved — no reference match either way (missing settlement /
     invalid reference).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.models.enums import ExceptionType, MatchStatus, MatchStrategy, ReviewStatus
from app.models.exception_case import ExceptionCase
from app.models.payment import Payment
from app.models.reconciliation import ReconciliationResult
from app.models.settlement import Settlement
from app.reconciliation.classifier import policy_for
from app.reconciliation.config import ReconciliationConfig

_ID_NAMESPACE = uuid.UUID("6f6f6f6f-0000-4000-8000-000000000000")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _deterministic_id(*parts: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, ":".join(parts)))


@dataclass
class ReconciliationReport:
    results: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)

    def summary(self) -> dict:
        counts: dict = {}
        for result in self.results:
            key = result.match_status.value
            counts[key] = counts.get(key, 0) + 1
        exception_counts: dict = {}
        for exc in self.exceptions:
            key = exc.exception_type.value
            exception_counts[key] = exception_counts.get(key, 0) + 1
        return {"match_status": counts, "exception_type": exception_counts}


def _expected_net(payment: Payment, config: ReconciliationConfig) -> tuple:
    fee = _q2(payment.amount * config.fee_rate)
    tax = _q2(fee * config.tax_rate)
    net = _q2(payment.amount - fee - tax)
    return fee, tax, net


def _classify_amount(payment: Payment, settlement: Settlement, config: ReconciliationConfig):
    """Returns (category, amount_difference) where category is one of
    'ok', 'fee_mismatch', 'partial_settlement', 'amount_mismatch'."""
    expected_fee, _expected_tax, expected_net = _expected_net(payment, config)
    fee_diff = settlement.fee - expected_fee
    net_diff = expected_net - settlement.settled_amount  # positive => shortfall

    if abs(fee_diff) > config.fee_tolerance:
        return "fee_mismatch", abs(_q2(net_diff))

    if net_diff > config.amount_tolerance:
        fraction_settled = (
            settlement.settled_amount / expected_net if expected_net != 0 else Decimal("0")
        )
        if (
            fraction_settled < config.partial_settlement_threshold
            and net_diff >= config.partial_settlement_min_absolute_diff
        ):
            return "partial_settlement", _q2(net_diff)
        return "amount_mismatch", _q2(net_diff)

    if net_diff < -config.amount_tolerance:
        return "amount_mismatch", abs(_q2(net_diff))

    return "ok", Decimal("0.00")


def _is_delayed(payment: Payment, settlement: Settlement, config: ReconciliationConfig) -> bool:
    return (settlement.settled_at - payment.created_at) > config.delayed_settlement_threshold


def _make_exception(
    reconciliation_result_id: str,
    exception_type: ExceptionType,
    confidence: float,
    financial_impact: Decimal,
    now: datetime,
    seq: int,
) -> ExceptionCase:
    policy = policy_for(exception_type)
    return ExceptionCase(
        id=_deterministic_id("exc", reconciliation_result_id, exception_type.value, str(seq)),
        reconciliation_result_id=reconciliation_result_id,
        exception_type=exception_type,
        severity=policy.severity,
        confidence=confidence,
        financial_impact=financial_impact,
        recommended_action=policy.recommended_action,
        auto_resolvable=policy.auto_resolvable,
        review_status=ReviewStatus.PENDING,
        created_at=now,
    )


def _reconcile_matched_payment(
    payment: Payment,
    matches: list,
    config: ReconciliationConfig,
    now: datetime,
) -> tuple:
    results = []
    exceptions = []

    ordered = sorted(matches, key=lambda s: (s.settled_at, s.settlement_id))
    primary, *duplicates = ordered

    amount_category, amount_diff = _classify_amount(payment, primary, config)
    delayed = _is_delayed(payment, primary, config)

    if amount_category == "ok" and not delayed:
        match_status = MatchStatus.MATCHED
        strategy = MatchStrategy.EXACT_REFERENCE
        confidence = 1.0
        reason = "exact reference, amount, and timestamp match"
    elif amount_category == "partial_settlement":
        match_status = MatchStatus.PARTIAL
        strategy = MatchStrategy.REFERENCE_AMOUNT
        confidence = 0.7
        _, _, expected_net = _expected_net(payment, config)
        fraction_settled = primary.settled_amount / expected_net if expected_net != 0 else Decimal("0")
        reason = (
            f"reference matched but only {(_q2(fraction_settled * 100))}% of the expected "
            f"payout (shortfall of {amount_diff}) was settled — below the "
            f"{config.partial_settlement_threshold * 100:.0f}% partial-settlement threshold"
        )
    elif amount_category in ("amount_mismatch", "fee_mismatch"):
        match_status = MatchStatus.MATCHED
        strategy = MatchStrategy.REFERENCE_AMOUNT
        confidence = 0.8 if amount_category == "fee_mismatch" else 0.75
        reason = (
            f"reference matched but settlement fee does not match the standard fee "
            f"schedule (payout differs by {amount_diff})"
            if amount_category == "fee_mismatch"
            else f"reference matched but settled amount differs from the expected payout by {amount_diff}"
        )
    else:  # amount ok, but delayed
        match_status = MatchStatus.MATCHED
        strategy = MatchStrategy.TIMESTAMP_TOLERANCE
        confidence = 0.9
        reason = "reference and amount matched; settlement arrived outside the normal window"

    result_id = _deterministic_id("result", payment.transaction_id, primary.settlement_id)
    results.append(
        ReconciliationResult(
            id=result_id,
            payment_reference=payment.transaction_id,
            settlement_reference=primary.settlement_id,
            match_status=match_status,
            match_strategy=strategy,
            confidence=confidence,
            amount_difference=amount_diff,
            reason=reason,
            created_at=now,
        )
    )

    seq = 0
    if amount_category != "ok":
        exception_type = {
            "amount_mismatch": ExceptionType.AMOUNT_MISMATCH,
            "partial_settlement": ExceptionType.PARTIAL_SETTLEMENT,
            "fee_mismatch": ExceptionType.FEE_MISMATCH,
        }[amount_category]
        exceptions.append(_make_exception(result_id, exception_type, confidence, amount_diff, now, seq))
        seq += 1
    if delayed:
        exceptions.append(
            _make_exception(result_id, ExceptionType.DELAYED_SETTLEMENT, 0.9, Decimal("0.00"), now, seq)
        )
        seq += 1

    for dup_seq, dup in enumerate(duplicates):
        dup_diff = abs(_q2(dup.settled_amount - primary.settled_amount))
        dup_result_id = _deterministic_id("result", payment.transaction_id, dup.settlement_id)
        results.append(
            ReconciliationResult(
                id=dup_result_id,
                payment_reference=payment.transaction_id,
                settlement_reference=dup.settlement_id,
                match_status=MatchStatus.DUPLICATE,
                match_strategy=MatchStrategy.EXACT_REFERENCE,
                confidence=0.6,
                amount_difference=dup_diff,
                reason="additional settlement found referencing an already-settled payment",
                created_at=now,
            )
        )
        exceptions.append(
            _make_exception(dup_result_id, ExceptionType.DUPLICATE_SETTLEMENT, 0.6, dup_diff, now, dup_seq)
        )

    return results, exceptions


def _reconcile_missing_payment(payment: Payment, orphan_settlement_count: int, now: datetime) -> tuple:
    result_id = _deterministic_id("result", payment.transaction_id, "missing")
    reason = "no settlement found for this payment"
    if orphan_settlement_count:
        # Cannot causally link a specific orphan settlement back to this
        # payment (that's exactly what an invalid reference prevents),
        # but flagging that unresolved settlements exist in the same
        # batch lets a later evaluation/review layer treat this as a
        # possible invalid-reference case rather than an unambiguous
        # true loss, without the engine claiming a link it can't prove.
        reason += (
            f" ({orphan_settlement_count} settlement(s) with references that match no known "
            "payment also exist in this batch — one may be this payment's misdirected settlement)"
        )
    result = ReconciliationResult(
        id=result_id,
        payment_reference=payment.transaction_id,
        settlement_reference=None,
        match_status=MatchStatus.UNMATCHED,
        match_strategy=None,
        confidence=0.0,
        amount_difference=payment.amount,
        reason=reason,
        created_at=now,
    )
    exception = _make_exception(result_id, ExceptionType.MISSING_SETTLEMENT, 0.0, payment.amount, now, 0)
    return [result], [exception]


def _reconcile_orphan_settlement(settlement: Settlement, now: datetime) -> tuple:
    result_id = _deterministic_id("result", "orphan", settlement.settlement_id)
    result = ReconciliationResult(
        id=result_id,
        payment_reference=settlement.transaction_reference,
        settlement_reference=settlement.settlement_id,
        match_status=MatchStatus.UNMATCHED,
        match_strategy=None,
        confidence=0.0,
        amount_difference=settlement.settled_amount,
        reason="settlement reference does not correspond to any known payment",
        created_at=now,
    )
    exception = _make_exception(
        result_id, ExceptionType.INVALID_REFERENCE, 0.0, settlement.settled_amount, now, 0
    )
    return [result], [exception]


def reconcile(
    payments: list,
    settlements: list,
    config: Optional[ReconciliationConfig] = None,
    now: Optional[datetime] = None,
) -> ReconciliationReport:
    """Deterministically reconcile payments against settlements.

    Never reads ground truth. Given the same inputs and config, always
    produces byte-identical results (no randomness, no wall-clock
    dependence unless `now` is left to default, which callers doing
    reproducible runs/tests should pin explicitly).
    """
    config = config or ReconciliationConfig()
    now = now or datetime.now(timezone.utc)

    settlements_by_reference: dict = {}
    for settlement in settlements:
        settlements_by_reference.setdefault(settlement.transaction_reference, []).append(settlement)

    payment_txn_ids = {payment.transaction_id for payment in payments}
    orphan_settlement_count = sum(
        len(matched) for reference, matched in settlements_by_reference.items() if reference not in payment_txn_ids
    )

    report = ReconciliationReport()

    for payment in sorted(payments, key=lambda p: p.transaction_id):
        matches = settlements_by_reference.get(payment.transaction_id, [])
        if matches:
            results, exceptions = _reconcile_matched_payment(payment, matches, config, now)
        else:
            results, exceptions = _reconcile_missing_payment(payment, orphan_settlement_count, now)
        report.results.extend(results)
        report.exceptions.extend(exceptions)

    for reference, matched_settlements in sorted(settlements_by_reference.items()):
        if reference in payment_txn_ids:
            continue
        for settlement in sorted(matched_settlements, key=lambda s: s.settlement_id):
            results, exceptions = _reconcile_orphan_settlement(settlement, now)
            report.results.extend(results)
            report.exceptions.extend(exceptions)

    return report
