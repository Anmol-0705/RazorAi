"""Computes dashboard metrics straight from persisted data — no
hard-coded numbers. Defaults to the most recently completed
reconciliation run; pass `run_id` to scope to a specific run.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExceptionCaseORM, ReconciliationResultORM, ReconciliationRunORM, SettlementORM
from app.services.errors import NotFoundError

_RECONCILED_STATUSES = ("matched", "partial")


def _latest_completed_run(db: Session) -> ReconciliationRunORM | None:
    return db.execute(
        select(ReconciliationRunORM)
        .where(ReconciliationRunORM.status == "completed")
        .order_by(ReconciliationRunORM.completed_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def compute_summary(db: Session, run_id: str | None = None) -> dict:
    if run_id:
        run = db.get(ReconciliationRunORM, run_id)
        if run is None or run.status != "completed":
            raise NotFoundError(f"no completed reconciliation run found with id '{run_id}'")
    else:
        run = _latest_completed_run(db)

    if run is None:
        return {
            "run_id": None,
            "total_transactions": 0,
            "matched": 0,
            "unmatched": 0,
            "partial": 0,
            "duplicate": 0,
            "exceptions": 0,
            "match_rate": 0.0,
            "amount_reconciled": "0.00",
            "amount_at_risk": "0.00",
            "auto_resolution_rate": 0.0,
        }

    results = db.execute(
        select(ReconciliationResultORM).where(ReconciliationResultORM.run_id == run.id)
    ).scalars().all()
    exceptions = db.execute(
        select(ExceptionCaseORM).where(ExceptionCaseORM.run_id == run.id)
    ).scalars().all()

    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.match_status] = status_counts.get(result.match_status, 0) + 1

    matched = status_counts.get("matched", 0)
    unmatched = status_counts.get("unmatched", 0)
    partial = status_counts.get("partial", 0)
    duplicate = status_counts.get("duplicate", 0)

    total_transactions = run.record_count
    match_rate = (matched / total_transactions) if total_transactions else 0.0

    settlement_ids = {r.settlement_reference for r in results if r.settlement_reference}
    settled_amounts: dict[str, Decimal] = {}
    if settlement_ids:
        rows = db.execute(
            select(SettlementORM.settlement_id, SettlementORM.settled_amount).where(
                SettlementORM.settlement_id.in_(settlement_ids)
            )
        ).all()
        settled_amounts = {row[0]: Decimal(row[1]) for row in rows}

    amount_reconciled = sum(
        (settled_amounts.get(r.settlement_reference, Decimal("0.00")) for r in results if r.match_status in _RECONCILED_STATUSES),
        Decimal("0.00"),
    )

    open_statuses = {"pending", "in_review"}
    amount_at_risk = sum(
        (Decimal(exc.financial_impact) for exc in exceptions if exc.review_status in open_statuses),
        Decimal("0.00"),
    )

    auto_resolved = sum(1 for exc in exceptions if exc.review_status == "auto_resolved")
    auto_resolution_rate = (auto_resolved / len(exceptions)) if exceptions else 0.0

    return {
        "run_id": run.id,
        "total_transactions": total_transactions,
        "matched": matched,
        "unmatched": unmatched,
        "partial": partial,
        "duplicate": duplicate,
        "exceptions": len(exceptions),
        "match_rate": round(match_rate, 4),
        "amount_reconciled": str(amount_reconciled.quantize(Decimal("0.01"))),
        "amount_at_risk": str(amount_at_risk.quantize(Decimal("0.01"))),
        "auto_resolution_rate": round(auto_resolution_rate, 4),
    }
