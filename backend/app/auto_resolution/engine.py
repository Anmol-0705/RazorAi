"""Bounded auto-resolution engine.

Consumes ExceptionCase records produced by the reconciliation engine
(`backend/app/reconciliation/`) and decides, per a fixed set of safe,
deterministic rules, whether to execute a corrective action
automatically. This module never determines *what happened* (that's
the reconciliation engine's job) and never calls the LLM — it only
decides whether an already-classified exception is safe to close
without a human.

Only low-risk, unambiguous cases are auto-resolved:
  - fee_mismatch, below a configured rupee cap
  - delayed_settlement, which never carries a real financial impact
  - duplicate_settlement, only when the duplicate's amount exactly
    matches the primary settlement (an unambiguous double-record, not
    a second, possibly legitimate, transaction)

Everything else (missing_settlement, amount_mismatch,
partial_settlement, invalid_reference, "other", and any case the
reconciliation classifier didn't mark `auto_resolvable`) is left
untouched for human review. An exception already acted on (review
status other than PENDING) is left as-is, making repeated runs over
the same exceptions idempotent.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional

from app.auto_resolution.config import ACTOR, AutoResolutionConfig
from app.models.auto_resolution import AutoResolutionRecord
from app.models.enums import ExceptionType, ResolutionType, ReviewStatus
from app.models.exception_case import ExceptionCase

_ID_NAMESPACE = uuid.UUID("7a7a7a7a-0000-4000-8000-000000000000")


def _deterministic_id(*parts: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, ":".join(parts)))


@dataclass
class AutoResolutionReport:
    resolved_exceptions: list = field(default_factory=list)
    unresolved_exceptions: list = field(default_factory=list)
    records: list = field(default_factory=list)


def policy_decision(exception: ExceptionCase, config: AutoResolutionConfig):
    """Pure bounded-safety check: returns (ResolutionType, reason) if
    this exception's *type and financial impact* fall within the
    auto-resolution policy, else None. Deliberately excludes the
    `review_status`/idempotency gating in `_decide` below — this is
    the reusable safety rule itself (exposed for
    `app.actions.engine`, Phase 8, to reuse verbatim for downstream
    finance-operation action eligibility, rather than re-deriving or
    duplicating these caps), independent of where a given exception
    currently sits in the review workflow.
    """
    if not exception.auto_resolvable:
        return None

    if exception.exception_type == ExceptionType.FEE_MISMATCH:
        if exception.financial_impact <= config.max_auto_fee_adjustment:
            return (
                ResolutionType.FEE_ADJUSTMENT_ACCEPTED,
                f"fee deviation of {exception.financial_impact} is within the "
                f"auto-approved cap of {config.max_auto_fee_adjustment}",
            )
        return None

    if exception.exception_type == ExceptionType.DELAYED_SETTLEMENT:
        if exception.financial_impact <= config.max_auto_delay_financial_impact:
            return (
                ResolutionType.DELAY_ACCEPTED,
                "settlement arrived outside the normal window but carries no "
                "financial impact; delay accepted",
            )
        return None

    if exception.exception_type == ExceptionType.DUPLICATE_SETTLEMENT:
        if exception.financial_impact <= config.max_auto_duplicate_financial_impact:
            return (
                ResolutionType.DUPLICATE_SUPPRESSED,
                "duplicate settlement amount exactly matches the original settlement; "
                "suppressed as a duplicate record rather than a second transaction",
            )
        return None

    return None


def _decide(exception: ExceptionCase, config: AutoResolutionConfig):
    """Pure decision logic: returns (ResolutionType, reason) if this
    exception should be auto-resolved *right now*, else None. Adds the
    idempotency/workflow-state gate on top of `policy_decision`'s bounded
    safety check. No side effects."""
    if exception.review_status != ReviewStatus.PENDING:
        return None  # already acted on elsewhere -> idempotent no-op
    return policy_decision(exception, config)


def auto_resolve(
    exceptions: list,
    config: Optional[AutoResolutionConfig] = None,
    now: Optional[datetime] = None,
) -> AutoResolutionReport:
    """Deterministically decide which exceptions can be safely closed
    without a human. Never mutates the input list or its ExceptionCase
    instances (they're frozen); resolved exceptions are returned as new
    copies with `review_status=AUTO_RESOLVED`.
    """
    config = config or AutoResolutionConfig()
    now = now or datetime.now(timezone.utc)

    report = AutoResolutionReport()

    for exception in exceptions:
        decision = _decide(exception, config)
        if decision is None:
            report.unresolved_exceptions.append(exception)
            continue

        resolution_type, reason = decision
        previous_status = exception.review_status
        resolved = replace(exception, review_status=ReviewStatus.AUTO_RESOLVED)
        record = AutoResolutionRecord(
            id=_deterministic_id("autoresolve", exception.id),
            exception_case_id=exception.id,
            resolution_type=resolution_type,
            reason=reason,
            actor=ACTOR,
            financial_impact=exception.financial_impact,
            previous_status=previous_status,
            new_status=ReviewStatus.AUTO_RESOLVED,
            created_at=now,
        )
        report.resolved_exceptions.append(resolved)
        report.records.append(record)

    return report
