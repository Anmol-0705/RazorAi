"""Orchestrates a reconciliation run: loads persisted payments/
settlements, calls the existing (unmodified) reconciliation and
auto-resolution engines, and persists the results.

This module never re-implements matching or auto-resolution logic —
it only converts rows <-> domain dataclasses around calls to
`app.reconciliation.engine.reconcile` and
`app.auto_resolution.engine.auto_resolve`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auto_resolution.engine import auto_resolve
from app.db.models import (
    AutoResolutionRecordORM,
    ExceptionCaseORM,
    PaymentORM,
    ReconciliationResultORM,
    ReconciliationRunORM,
    SettlementORM,
)
from app.models.enums import Currency, PaymentMethod, PaymentStatus, SettlementStatus
from app.models.exception_case import ExceptionCase
from app.models.payment import Payment
from app.models.settlement import Settlement
from app.reconciliation.engine import reconcile
from app.services.errors import ConflictError, NotFoundError


def _payment_from_row(row: PaymentORM) -> Payment:
    return Payment(
        id=row.id,
        transaction_id=row.transaction_id,
        order_id=row.order_id,
        customer_reference=row.customer_reference,
        amount=Decimal(row.amount),
        currency=Currency(row.currency),
        payment_method=PaymentMethod(row.payment_method),
        payment_status=PaymentStatus(row.payment_status),
        created_at=row.created_at,
    )


def _settlement_from_row(row: SettlementORM) -> Settlement:
    return Settlement(
        id=row.id,
        settlement_id=row.settlement_id,
        transaction_reference=row.transaction_reference,
        settled_amount=Decimal(row.settled_amount),
        fee=Decimal(row.fee),
        tax=Decimal(row.tax),
        settlement_status=SettlementStatus(row.settlement_status),
        settled_at=row.settled_at,
    )


def _run_summary(run: ReconciliationRunORM) -> dict:
    return {
        "run_id": run.id,
        "dataset_id": run.dataset_id,
        "record_count": run.record_count,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "summary": run.summary,
        "error": run.error,
    }


def run_reconciliation(db: Session, dataset_id: str, run_id: str | None = None) -> dict:
    payment_rows = db.execute(
        select(PaymentORM).where(PaymentORM.dataset_id == dataset_id)
    ).scalars().all()
    if not payment_rows:
        raise NotFoundError(f"no dataset found with id '{dataset_id}'")
    settlement_rows = db.execute(
        select(SettlementORM).where(SettlementORM.dataset_id == dataset_id)
    ).scalars().all()

    run_id = run_id or str(uuid.uuid4())
    existing_run = db.get(ReconciliationRunORM, run_id)
    if existing_run is not None:
        if existing_run.status == "completed":
            return _run_summary(existing_run)  # idempotent replay, no recomputation
        if existing_run.status == "running":
            raise ConflictError(f"run '{run_id}' is already in progress")
        # status == "failed": fall through and retry with the same id.
        run = existing_run
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = None
        run.error = None
    else:
        run = ReconciliationRunORM(
            id=run_id,
            dataset_id=dataset_id,
            record_count=len(payment_rows),
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
    db.commit()

    try:
        payments = [_payment_from_row(row) for row in payment_rows]
        settlements = [_settlement_from_row(row) for row in settlement_rows]
        now = datetime.now(timezone.utc)

        report = reconcile(payments, settlements, now=now)
        auto_report = auto_resolve(report.exceptions, now=now)

        resolved_by_id = {exc.id: exc for exc in auto_report.resolved_exceptions}
        final_exceptions: list[ExceptionCase] = [
            resolved_by_id.get(exc.id, exc) for exc in report.exceptions
        ]

        # The reconciliation/auto-resolution engines assign IDs deterministically
        # from payment/settlement identifiers, so the *same* dataset reconciled in
        # two different runs would otherwise produce colliding primary keys. Scope
        # every persisted row's id to its run_id to keep runs independent.
        def scoped(domain_id: str) -> str:
            return f"{run_id}:{domain_id}"

        for result in report.results:
            db.add(
                ReconciliationResultORM(
                    id=scoped(result.id),
                    run_id=run_id,
                    payment_reference=result.payment_reference,
                    settlement_reference=result.settlement_reference,
                    match_status=result.match_status.value,
                    match_strategy=result.match_strategy.value if result.match_strategy else None,
                    confidence=result.confidence,
                    amount_difference=result.amount_difference,
                    reason=result.reason,
                    created_at=result.created_at,
                )
            )

        db.flush()  # ensure reconciliation_results rows exist before exception_cases FKs reference them

        result_payment_ref = {r.id: r.payment_reference for r in report.results}
        for exc in final_exceptions:
            db.add(
                ExceptionCaseORM(
                    id=scoped(exc.id),
                    run_id=run_id,
                    reconciliation_result_id=scoped(exc.reconciliation_result_id),
                    payment_reference=result_payment_ref.get(exc.reconciliation_result_id, ""),
                    exception_type=exc.exception_type.value,
                    severity=exc.severity.value,
                    confidence=exc.confidence,
                    financial_impact=exc.financial_impact,
                    recommended_action=exc.recommended_action.value,
                    auto_resolvable=exc.auto_resolvable,
                    review_status=exc.review_status.value,
                    created_at=exc.created_at,
                    updated_at=exc.created_at,
                )
            )

        db.flush()  # ensure exception_cases rows exist before auto_resolution_records FKs reference them

        for record in auto_report.records:
            db.add(
                AutoResolutionRecordORM(
                    id=scoped(record.id),
                    exception_case_id=scoped(record.exception_case_id),
                    resolution_type=record.resolution_type.value,
                    reason=record.reason,
                    actor=record.actor,
                    financial_impact=record.financial_impact,
                    previous_status=record.previous_status.value,
                    new_status=record.new_status.value,
                    created_at=record.created_at,
                )
            )

        summary = report.summary()
        summary["auto_resolved_count"] = len(auto_report.records)
        summary["exception_count"] = len(final_exceptions)

        db.commit()
    except Exception as exc:  # noqa: BLE001 - persisted as a run failure, then re-raised
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(exc)
        db.commit()
        raise

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.summary = summary
    db.commit()
    db.refresh(run)

    return _run_summary(run)


def get_run(db: Session, run_id: str) -> ReconciliationRunORM:
    run = db.get(ReconciliationRunORM, run_id)
    if run is None:
        raise NotFoundError(f"no reconciliation run found with id '{run_id}'")
    return run


def list_runs(db: Session, limit: int = 50) -> list[ReconciliationRunORM]:
    return list(
        db.execute(
            select(ReconciliationRunORM).order_by(ReconciliationRunORM.started_at.desc()).limit(limit)
        ).scalars().all()
    )


def _enrich_result(
    result: ReconciliationResultORM,
    payment_by_txn: dict[str, PaymentORM],
    settlement_by_id: dict[str, SettlementORM],
    exception_by_result_id: dict[str, ExceptionCaseORM],
) -> dict:
    payment = payment_by_txn.get(result.payment_reference)
    settlement = settlement_by_id.get(result.settlement_reference) if result.settlement_reference else None
    exc = exception_by_result_id.get(result.id)
    return {
        "id": result.id,
        "run_id": result.run_id,
        "payment_reference": result.payment_reference,
        "settlement_reference": result.settlement_reference,
        "match_status": result.match_status,
        "match_strategy": result.match_strategy,
        "confidence": result.confidence,
        "amount_difference": result.amount_difference,
        "reason": result.reason,
        "created_at": result.created_at,
        "order_id": payment.order_id if payment else None,
        "payment_amount": payment.amount if payment else None,
        "currency": payment.currency if payment else None,
        "payment_method": payment.payment_method if payment else None,
        "payment_status": payment.payment_status if payment else None,
        "settlement_status": settlement.settlement_status if settlement else None,
        "settled_amount": settlement.settled_amount if settlement else None,
        "fee": settlement.fee if settlement else None,
        "tax": settlement.tax if settlement else None,
        "exception_type": exc.exception_type if exc else None,
        "exception_review_status": exc.review_status if exc else None,
        "exception_id": exc.id if exc else None,
    }


def list_results(
    db: Session,
    run_id: str,
    match_status: str | None = None,
) -> list[dict]:
    get_run(db, run_id)  # 404 if the run doesn't exist
    stmt = select(ReconciliationResultORM).where(ReconciliationResultORM.run_id == run_id)
    if match_status:
        stmt = stmt.where(ReconciliationResultORM.match_status == match_status)
    results = list(db.execute(stmt.order_by(ReconciliationResultORM.payment_reference)).scalars().all())
    return _enrich_results(db, run_id, results)


def _enrich_results(db: Session, run_id: str, results: list[ReconciliationResultORM]) -> list[dict]:
    if not results:
        return []
    payment_refs = {r.payment_reference for r in results}
    settlement_refs = {r.settlement_reference for r in results if r.settlement_reference}

    payment_by_txn = {
        p.transaction_id: p
        for p in db.execute(
            select(PaymentORM).where(PaymentORM.transaction_id.in_(payment_refs))
        ).scalars()
    }
    settlement_by_id = {
        s.settlement_id: s
        for s in db.execute(
            select(SettlementORM).where(SettlementORM.settlement_id.in_(settlement_refs))
        ).scalars()
    } if settlement_refs else {}
    exception_by_result_id = {
        e.reconciliation_result_id: e
        for e in db.execute(
            select(ExceptionCaseORM).where(ExceptionCaseORM.run_id == run_id)
        ).scalars()
    }

    return [
        _enrich_result(result, payment_by_txn, settlement_by_id, exception_by_result_id)
        for result in results
    ]


def get_result_by_id(db: Session, run_id: str, result_id: str) -> dict:
    result = db.get(ReconciliationResultORM, result_id)
    if result is None or result.run_id != run_id:
        raise NotFoundError(f"no reconciliation result found with id '{result_id}' in run '{run_id}'")
    return _enrich_results(db, run_id, [result])[0]
