"""Human review workflow over ExceptionCase records.

Backend/domain layer only — no API routes, no UI yet (see
PROJECT_STATE.md). A reviewer (or a system acting on a human's behalf)
can approve a proposed resolution, reject it, mark an exception
resolved outright, or leave a note; each action returns an updated
ExceptionCase alongside an immutable ReviewAudit entry. Never touches
the reconciliation or auto-resolution engines.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from app.models.audit import ReviewAudit
from app.models.enums import ReviewStatus
from app.models.exception_case import ExceptionCase


def _apply(
    exception: ExceptionCase,
    reviewer: str,
    decision: ReviewStatus,
    note: str,
    now: Optional[datetime],
):
    now = now or datetime.now(timezone.utc)
    updated = replace(exception, review_status=decision)
    audit = ReviewAudit(
        id=str(uuid.uuid4()),
        exception_case_id=exception.id,
        reviewer=reviewer,
        decision=decision,
        notes=note,
        created_at=now,
    )
    return updated, audit


def approve(exception: ExceptionCase, reviewer: str, note: str = "", now: Optional[datetime] = None):
    """Approve a proposed resolution (e.g. confirm an auto-resolution)."""
    return _apply(exception, reviewer, ReviewStatus.APPROVED, note, now)


def reject(exception: ExceptionCase, reviewer: str, note: str = "", now: Optional[datetime] = None):
    """Reject a proposed resolution, sending the case back for further work."""
    return _apply(exception, reviewer, ReviewStatus.REJECTED, note, now)


def mark_resolved(exception: ExceptionCase, reviewer: str, note: str = "", now: Optional[datetime] = None):
    """A human manually resolves the exception outright, independent of
    any proposed/automated resolution."""
    return _apply(exception, reviewer, ReviewStatus.APPROVED, note or "manually resolved by reviewer", now)


def add_note(exception: ExceptionCase, reviewer: str, note: str, now: Optional[datetime] = None):
    """Record a note without changing the exception's review status."""
    return _apply(exception, reviewer, exception.review_status, note, now)


def start_review(exception: ExceptionCase, reviewer: str, note: str = "", now: Optional[datetime] = None):
    """Move a pending exception into active human review."""
    return _apply(exception, reviewer, ReviewStatus.IN_REVIEW, note, now)
