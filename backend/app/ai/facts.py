"""Allowlisted, deterministic backend data-retrieval functions for the
AI layer.

Every fact the AI is ever allowed to reason over comes from one of the
functions in this module — all of them thin wrappers around the
existing `app.services.*` layer (no new matching/aggregation logic;
`exception_rate_by_payment_method` is the one genuinely new
aggregation, and it's plain Python over already-enriched rows, not a
new SQL query). There is no path from a user question to raw SQL or to
an arbitrary backend function: `app.ai.query_router` only ever calls
functions from this fixed list.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services import dashboard_service, exception_service, reconciliation_service
from app.services.errors import NotFoundError


def to_jsonable(value):
    """Recursively convert Decimal/datetime to JSON-safe primitives so
    every fact function's output is safe both to `json.dumps` for the
    AI provider and to return directly as an API response field."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def dashboard_summary(db: Session, run_id: str | None = None) -> dict:
    return to_jsonable(dashboard_service.compute_summary(db, run_id=run_id))


def exception_counts_by_type(db: Session, run_id: str) -> dict:
    exceptions = exception_service.list_exceptions(db, run_id=run_id, limit=10000)
    counts: dict[str, int] = {}
    impact: dict[str, Decimal] = {}
    for e in exceptions:
        counts[e.exception_type] = counts.get(e.exception_type, 0) + 1
        impact[e.exception_type] = impact.get(e.exception_type, Decimal("0")) + Decimal(e.financial_impact)
    return to_jsonable(
        {
            "run_id": run_id,
            "counts_by_type": counts,
            "financial_impact_by_type": impact,
        }
    )


def exception_counts_by_severity(db: Session, run_id: str) -> dict:
    exceptions = exception_service.list_exceptions(db, run_id=run_id, limit=10000)
    counts: dict[str, int] = {}
    for e in exceptions:
        counts[e.severity] = counts.get(e.severity, 0) + 1
    return to_jsonable({"run_id": run_id, "counts_by_severity": counts})


def exception_rate_by_payment_method(db: Session, run_id: str) -> dict:
    results = reconciliation_service.list_results(db, run_id=run_id)
    totals: dict[str, int] = {}
    exceptions: dict[str, int] = {}
    for r in results:
        method = r.get("payment_method")
        if not method:
            continue
        totals[method] = totals.get(method, 0) + 1
        if r.get("exception_type"):
            exceptions[method] = exceptions.get(method, 0) + 1
    rate = {
        method: round(exceptions.get(method, 0) / total, 4) if total else 0.0
        for method, total in totals.items()
    }
    return to_jsonable(
        {
            "run_id": run_id,
            "transactions_by_method": totals,
            "exceptions_by_method": exceptions,
            "exception_rate_by_method": rate,
        }
    )


def auto_resolved_count(db: Session, run_id: str) -> dict:
    exceptions = exception_service.list_exceptions(db, run_id=run_id, status="auto_resolved", limit=10000)
    total = exception_service.list_exceptions(db, run_id=run_id, limit=10000)
    return to_jsonable(
        {"run_id": run_id, "auto_resolved_count": len(exceptions), "total_exception_count": len(total)}
    )


def unresolved_high_severity(db: Session, run_id: str, limit: int = 20) -> dict:
    exceptions = exception_service.list_exceptions(db, run_id=run_id, limit=10000)
    open_statuses = {"pending", "in_review"}
    high = [
        e for e in exceptions if e.severity in ("high", "critical") and e.review_status in open_statuses
    ]
    high.sort(key=lambda e: (0 if e.severity == "critical" else 1, -float(e.financial_impact)))
    return to_jsonable(
        {
            "run_id": run_id,
            "count": len(high),
            "items": [
                {
                    "exception_id": e.id,
                    "payment_reference": e.payment_reference,
                    "exception_type": e.exception_type,
                    "severity": e.severity,
                    "financial_impact": e.financial_impact,
                    "review_status": e.review_status,
                }
                for e in high[:limit]
            ],
        }
    )


def explain_transaction(db: Session, run_id: str, transaction_id: str) -> dict:
    results = reconciliation_service.list_results(db, run_id=run_id)
    matches = [r for r in results if r["payment_reference"] == transaction_id]
    if not matches:
        raise NotFoundError(
            f"no reconciliation result found for transaction '{transaction_id}' in run '{run_id}'"
        )
    return to_jsonable({"run_id": run_id, "transaction_id": transaction_id, "results": matches})


def exception_detail_facts(db: Session, exception_id: str) -> dict:
    """Returns the raw service-layer detail dict (ORM rows, not yet
    JSON-sanitized) — callers that build a facts payload for the AI
    provider should extract only the fields they need and sanitize
    with `to_jsonable`, since the raw dict includes ORM objects and
    lists of audit rows that aren't directly JSON-serializable."""
    return exception_service.get_exception_detail(db, exception_id)
