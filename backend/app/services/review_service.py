"""Orchestrates human review actions against persisted ExceptionCase
rows.

Reuses `app.review.workflow` as-is for the actual status-transition
logic; this module's only job is loading the row, converting it to the
domain `ExceptionCase` dataclass, calling the workflow function, and
persisting the result plus a `ReviewAuditORM` entry.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import ExceptionCaseORM, ReviewAuditORM
from app.models.enums import ExceptionType, RecommendedAction, ReviewStatus, Severity
from app.models.exception_case import ExceptionCase
from app.review import workflow
from app.services.errors import NotFoundError

_ACTIONS = {
    "start_review": workflow.start_review,
    "approve": workflow.approve,
    "reject": workflow.reject,
    "mark_resolved": workflow.mark_resolved,
    "add_note": workflow.add_note,
}


def _exception_from_row(row: ExceptionCaseORM) -> ExceptionCase:
    return ExceptionCase(
        id=row.id,
        reconciliation_result_id=row.reconciliation_result_id,
        exception_type=ExceptionType(row.exception_type),
        severity=Severity(row.severity),
        confidence=row.confidence,
        financial_impact=Decimal(row.financial_impact),
        recommended_action=RecommendedAction(row.recommended_action),
        auto_resolvable=row.auto_resolvable,
        review_status=ReviewStatus(row.review_status),
        created_at=row.created_at,
    )


def get_exception(db: Session, exception_id: str) -> ExceptionCaseORM:
    row = db.get(ExceptionCaseORM, exception_id)
    if row is None:
        raise NotFoundError(f"no exception found with id '{exception_id}'")
    return row


def apply_review_action(
    db: Session,
    exception_id: str,
    action: str,
    reviewer: str,
    note: str = "",
) -> tuple[ExceptionCaseORM, ReviewAuditORM]:
    if action not in _ACTIONS:
        raise ValueError(f"unknown review action '{action}'")

    row = get_exception(db, exception_id)
    domain_exception = _exception_from_row(row)
    previous_status = domain_exception.review_status

    updated, audit = _ACTIONS[action](domain_exception, reviewer, note=note)

    row.review_status = updated.review_status.value
    audit_row = ReviewAuditORM(
        id=audit.id,
        exception_case_id=exception_id,
        actor=audit.reviewer,
        action=action,
        note=audit.notes,
        previous_status=previous_status.value,
        new_status=updated.review_status.value,
        created_at=audit.created_at,
    )
    db.add(audit_row)
    db.commit()
    db.refresh(row)

    return row, audit_row
