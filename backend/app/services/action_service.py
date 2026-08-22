"""Orchestrates the Bounded Finance Controller Action Engine
(`app.actions.engine`) against a persisted ExceptionCase row.

Mirrors `app.services.review_service`'s shape: load the row, convert
to the domain `ExceptionCase` dataclass, call the pure engine,
persist. The only extra piece is idempotency — `ActionExecutionORM.id`
is the engine's deterministic idempotency key, so a retried call for
the same exception is detected by primary-key lookup before any
insert, never by a duplicate/unique-constraint error.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.actions import engine
from app.actions.config import ACTOR
from app.db.models import ActionExecutionORM, ExceptionCaseORM, ReviewAuditORM
from app.models.enums import ExceptionType, RecommendedAction, ReviewStatus, Severity
from app.models.exception_case import ExceptionCase
from app.services.errors import NotFoundError

# ReviewAuditORM.action is a String(20) column; existing values
# ("start_review", "mark_resolved", ...) are all short workflow verbs,
# so this one is kept to the same style/length rather than widening
# the column for a single new value.
_AUDIT_ACTION = "controller_action"


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


def check_eligibility(db: Session, exception_id: str) -> engine.ActionEligibility:
    """Read-only eligibility preview — used by the Exception Detail
    view so the UI can show "eligible"/"requires human review" *before*
    the user attempts to execute anything, without that preview itself
    being able to bypass the same check the execute endpoint re-runs."""
    row = get_exception(db, exception_id)
    return engine.check_eligibility(_exception_from_row(row))


def execute_action(db: Session, exception_id: str) -> dict:
    row = get_exception(db, exception_id)
    domain_exception = _exception_from_row(row)

    eligibility, record = engine.execute_action(domain_exception)

    if record is None:
        return {
            "eligible": False,
            "reason": eligibility.reason,
            "rule_id": eligibility.rule_id,
            "already_executed": False,
            "action": None,
            "audit": None,
            "exception": row,
        }

    existing = db.get(ActionExecutionORM, record.id)
    if existing is not None:
        # Idempotent replay: the same exception + action type always
        # derives the same primary key, so this is the *same* action
        # being asked for again, not a duplicate to create.
        return {
            "eligible": True,
            "reason": eligibility.reason,
            "rule_id": eligibility.rule_id,
            "already_executed": True,
            "action": existing,
            "audit": None,
            "exception": row,
        }

    before_status = row.review_status
    # Executing a bounded action implies the case is being closed out;
    # an exception still sitting PENDING moves to APPROVED so it drops
    # out of the open review queue. An exception already AUTO_RESOLVED
    # or APPROVED (the common path — auto-resolution already ran)
    # keeps its status; REJECTED is already blocked by eligibility.
    new_status = row.review_status
    if row.review_status == ReviewStatus.PENDING.value:
        new_status = ReviewStatus.APPROVED.value
        row.review_status = new_status

    action_row = ActionExecutionORM(
        id=record.id,
        exception_case_id=exception_id,
        action_type=record.action_type.value,
        actor=record.actor,
        reason=record.reason,
        rule_id=record.rule_id,
        status=record.status.value,
        idempotency_key=record.idempotency_key,
        resulting_reference=record.resulting_reference,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )
    db.add(action_row)

    audit_row = ReviewAuditORM(
        id=str(uuid.uuid4()),
        exception_case_id=exception_id,
        actor=ACTOR,
        action=_AUDIT_ACTION,
        note=(
            f"{record.action_type.value}: {record.reason} (rule {record.rule_id}); "
            f"resulting_reference={record.resulting_reference}"
        ),
        previous_status=before_status,
        new_status=new_status,
        created_at=record.created_at,
    )
    db.add(audit_row)

    db.commit()
    db.refresh(action_row)
    db.refresh(row)

    return {
        "eligible": True,
        "reason": eligibility.reason,
        "rule_id": eligibility.rule_id,
        "already_executed": False,
        "action": action_row,
        "audit": audit_row,
        "exception": row,
    }
