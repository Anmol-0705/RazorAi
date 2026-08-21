"""Read-side queries over persisted ExceptionCase rows (listing/detail
with filters). Mutating actions live in `app.services.review_service`.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AutoResolutionRecordORM, ExceptionCaseORM, ReconciliationResultORM, ReviewAuditORM
from app.services import reconciliation_service
from app.services.errors import NotFoundError


def list_exceptions(
    db: Session,
    status: str | None = None,
    severity: str | None = None,
    exception_type: str | None = None,
    run_id: str | None = None,
    limit: int = 100,
) -> list[ExceptionCaseORM]:
    stmt = select(ExceptionCaseORM)
    if status:
        stmt = stmt.where(ExceptionCaseORM.review_status == status)
    if severity:
        stmt = stmt.where(ExceptionCaseORM.severity == severity)
    if exception_type:
        stmt = stmt.where(ExceptionCaseORM.exception_type == exception_type)
    if run_id:
        stmt = stmt.where(ExceptionCaseORM.run_id == run_id)
    stmt = stmt.order_by(ExceptionCaseORM.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_exception_detail(db: Session, exception_id: str) -> dict:
    exc = db.get(ExceptionCaseORM, exception_id)
    if exc is None:
        raise NotFoundError(f"no exception found with id '{exception_id}'")

    auto_resolutions = db.execute(
        select(AutoResolutionRecordORM).where(AutoResolutionRecordORM.exception_case_id == exception_id)
    ).scalars().all()
    review_audits = db.execute(
        select(ReviewAuditORM)
        .where(ReviewAuditORM.exception_case_id == exception_id)
        .order_by(ReviewAuditORM.created_at)
    ).scalars().all()

    result_row = db.get(ReconciliationResultORM, exc.reconciliation_result_id)
    enriched_result = (
        reconciliation_service._enrich_results(db, exc.run_id, [result_row])[0] if result_row else None
    )

    return {
        "exception": exc,
        "result": enriched_result,
        "auto_resolutions": list(auto_resolutions),
        "review_audits": list(review_audits),
    }
