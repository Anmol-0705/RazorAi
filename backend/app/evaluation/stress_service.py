"""Orchestrates the Stress / Dirty Data evaluation benchmark.

Runs `app.reconciliation.engine.reconcile` and
`app.auto_resolution.engine.auto_resolve` — the exact same, unmodified,
pure functions the baseline evaluation and every reconciliation API
route call — directly in memory against a noised copy of the held-out
dataset (`app.evaluation.stress.apply_noise`), then scores it with the
same `app.evaluation.scoring.score` used for the clean baseline.

Deliberately *not* persisted through `app.services.reconciliation_service`
like the baseline evaluation (DECISIONS.md D019) is: that service
requires the dataset's Payment/Settlement rows to be inserted under a
fresh `dataset_id`, but `PaymentORM.transaction_id` and
`SettlementORM.settlement_id` are globally unique columns — and the
stress dataset intentionally reuses the baseline's exact payment
identities (see stress.py) so ground-truth scoring stays valid. Trying
to persist it under those same identifiers would collide with the
already-persisted baseline eval rows. Calling the reconciliation/
auto-resolution engines directly is still "run the actual production
reconciliation engine" — it is the identical function, just invoked
without a database round-trip that would fail for an unrelated reason.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auto_resolution.engine import auto_resolve
from app.db.models import StressEvaluationRunORM
from app.evaluation.loader import load_eval_dataset
from app.evaluation.scoring import score
from app.evaluation.stress import NoiseConfig, apply_noise, summarize_noise
from app.reconciliation.engine import reconcile
from app.services.errors import NotFoundError


def _enriched_result_dicts(results, settlements_by_id: dict) -> list[dict]:
    enriched = []
    for r in results:
        settlement = settlements_by_id.get(r.settlement_reference)
        enriched.append(
            {
                "payment_reference": r.payment_reference,
                "match_status": r.match_status.value,
                "settled_amount": settlement.settled_amount if settlement else None,
            }
        )
    return enriched


def _scoring_exceptions(final_exceptions, result_payment_ref: dict) -> list:
    return [
        SimpleNamespace(
            payment_reference=result_payment_ref.get(exc.reconciliation_result_id, ""),
            exception_type=exc.exception_type,
            review_status=exc.review_status,
            financial_impact=exc.financial_impact,
            auto_resolvable=exc.auto_resolvable,
        )
        for exc in final_exceptions
    ]


def _run_summary(run: StressEvaluationRunORM) -> dict:
    return {
        "stress_evaluation_id": run.id,
        "dataset_name": run.dataset_name,
        "seed": run.seed,
        "record_count": run.record_count,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "noise_summary": run.noise_summary,
        "metrics": run.metrics,
        "error": run.error,
    }


def run_stress_evaluation(
    db: Session, dataset_name: str = "n250", noise_config: NoiseConfig | None = None
) -> dict:
    config = noise_config or NoiseConfig()
    baseline = load_eval_dataset(name=dataset_name)
    noisy_dataset, noise_log = apply_noise(baseline, config)

    stress_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    run = StressEvaluationRunORM(
        id=stress_id,
        dataset_name=noisy_dataset.name,
        seed=config.seed,
        record_count=len(noisy_dataset.ground_truth),
        status="running",
        started_at=started_at,
    )
    db.add(run)
    db.commit()

    try:
        now = datetime.now(timezone.utc)
        report = reconcile(noisy_dataset.payments, noisy_dataset.settlements, now=now)
        auto_report = auto_resolve(report.exceptions, now=now)

        resolved_by_id = {exc.id: exc for exc in auto_report.resolved_exceptions}
        final_exceptions = [resolved_by_id.get(exc.id, exc) for exc in report.exceptions]

        settlements_by_id = {s.settlement_id: s for s in noisy_dataset.settlements}
        result_payment_ref = {r.id: r.payment_reference for r in report.results}

        enriched_results = _enriched_result_dicts(report.results, settlements_by_id)
        scoring_exceptions = _scoring_exceptions(final_exceptions, result_payment_ref)

        metrics = score(noisy_dataset.payments, enriched_results, scoring_exceptions, noisy_dataset.ground_truth)
        noise_summary = summarize_noise(noise_log)
    except Exception as exc:  # noqa: BLE001 - persisted as a failed run, then re-raised
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(exc)
        db.commit()
        raise

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.metrics = metrics.to_dict()
    run.noise_summary = noise_summary
    db.commit()
    db.refresh(run)

    return _run_summary(run)


def get_stress_evaluation(db: Session, stress_evaluation_id: str) -> dict:
    run = db.get(StressEvaluationRunORM, stress_evaluation_id)
    if run is None:
        raise NotFoundError(f"no stress evaluation run found with id '{stress_evaluation_id}'")
    return _run_summary(run)


def get_latest_stress_evaluation(db: Session) -> dict:
    run = db.execute(
        select(StressEvaluationRunORM)
        .where(StressEvaluationRunORM.status == "completed")
        .order_by(StressEvaluationRunORM.completed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("no completed stress evaluation run exists yet")
    return _run_summary(run)
