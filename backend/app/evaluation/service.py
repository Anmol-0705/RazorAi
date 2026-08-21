"""Orchestrates a held-out evaluation run.

Loads the committed eval dataset (`app.evaluation.loader`), persists it
(idempotently, same pattern as `app.services.dataset_service`), runs it
through the *unmodified* production reconciliation pipeline
(`app.services.reconciliation_service.run_reconciliation` — the exact
function the `/reconciliation/runs` API route calls, not a copy), then
scores the persisted results against ground truth
(`app.evaluation.scoring`, pure functions, no matching logic of its
own). Nothing here re-implements matching, auto-resolution, or
aggregation beyond the deterministic scoring itself.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvaluationRunORM, ExceptionCaseORM, PaymentORM, SettlementORM
from app.evaluation.loader import EvalDataset, load_eval_dataset
from app.evaluation.scoring import score
from app.services import reconciliation_service
from app.services.errors import NotFoundError

# Fixed per dataset so repeated evaluations replay the same underlying
# reconciliation run (idempotent per DECISIONS.md D013) instead of
# growing a new reconciliation_runs row on every /evaluation/run call.
_RECONCILIATION_RUN_ID_PREFIX = "eval-recon-"


def _dataset_id(name: str) -> str:
    return f"eval-{name}"


def _persist_eval_dataset(db: Session, dataset: EvalDataset) -> str:
    dataset_id = _dataset_id(dataset.name)
    existing = db.scalar(select(PaymentORM.id).where(PaymentORM.dataset_id == dataset_id).limit(1))
    if existing is not None:
        return dataset_id

    for payment in dataset.payments:
        db.add(
            PaymentORM(
                id=payment.id,
                dataset_id=dataset_id,
                transaction_id=payment.transaction_id,
                order_id=payment.order_id,
                customer_reference=payment.customer_reference,
                amount=payment.amount,
                currency=payment.currency.value,
                payment_method=payment.payment_method.value,
                payment_status=payment.payment_status.value,
                created_at=payment.created_at,
            )
        )
    for settlement in dataset.settlements:
        db.add(
            SettlementORM(
                id=settlement.id,
                dataset_id=dataset_id,
                settlement_id=settlement.settlement_id,
                transaction_reference=settlement.transaction_reference,
                settled_amount=settlement.settled_amount,
                fee=settlement.fee,
                tax=settlement.tax,
                settlement_status=settlement.settlement_status.value,
                settled_at=settlement.settled_at,
            )
        )
    db.commit()
    return dataset_id


def _run_summary(run: EvaluationRunORM) -> dict:
    return {
        "evaluation_id": run.id,
        "dataset_name": run.dataset_name,
        "reconciliation_run_id": run.reconciliation_run_id,
        "record_count": run.record_count,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "metrics": run.metrics,
        "error": run.error,
    }


def run_evaluation(db: Session, dataset_name: str = "n250") -> dict:
    dataset = load_eval_dataset(name=dataset_name)
    dataset_id = _persist_eval_dataset(db, dataset)

    reconciliation_run_id = f"{_RECONCILIATION_RUN_ID_PREFIX}{dataset_name}"
    reconciliation_service.run_reconciliation(db, dataset_id=dataset_id, run_id=reconciliation_run_id)

    results = reconciliation_service.list_results(db, run_id=reconciliation_run_id)
    exceptions = list(
        db.execute(
            select(ExceptionCaseORM).where(ExceptionCaseORM.run_id == reconciliation_run_id)
        ).scalars()
    )

    evaluation_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    run = EvaluationRunORM(
        id=evaluation_id,
        dataset_name=dataset_name,
        reconciliation_run_id=reconciliation_run_id,
        record_count=len(dataset.ground_truth),
        status="running",
        started_at=started_at,
    )
    db.add(run)
    db.commit()

    try:
        metrics = score(dataset.payments, results, exceptions, dataset.ground_truth)
    except Exception as exc:  # noqa: BLE001 - persisted as a failed evaluation, then re-raised
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(exc)
        db.commit()
        raise

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.metrics = metrics.to_dict()
    db.commit()
    db.refresh(run)

    return _run_summary(run)


def get_evaluation(db: Session, evaluation_id: str) -> dict:
    run = db.get(EvaluationRunORM, evaluation_id)
    if run is None:
        raise NotFoundError(f"no evaluation run found with id '{evaluation_id}'")
    return _run_summary(run)


def get_latest_evaluation(db: Session) -> dict:
    run = db.execute(
        select(EvaluationRunORM)
        .where(EvaluationRunORM.status == "completed")
        .order_by(EvaluationRunORM.completed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("no completed evaluation run exists yet")
    return _run_summary(run)
