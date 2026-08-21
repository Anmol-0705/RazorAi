from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import ReconciliationResultResponse, RunReconciliationRequest, RunSummaryResponse
from app.db.base import get_db
from app.services import reconciliation_service
from app.services.errors import ConflictError, NotFoundError

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.post("/runs", response_model=RunSummaryResponse)
def create_run(request: RunReconciliationRequest, db: Session = Depends(get_db)) -> RunSummaryResponse:
    try:
        summary = reconciliation_service.run_reconciliation(
            db, dataset_id=request.dataset_id, run_id=request.run_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - run failure is persisted, then surfaced as 500
        raise HTTPException(status_code=500, detail=f"reconciliation run failed: {exc}") from exc
    return RunSummaryResponse(**summary)


@router.get("/runs", response_model=list[RunSummaryResponse])
def get_runs(limit: int = Query(default=50, gt=0, le=200), db: Session = Depends(get_db)):
    runs = reconciliation_service.list_runs(db, limit=limit)
    return [
        RunSummaryResponse(
            run_id=r.id,
            dataset_id=r.dataset_id,
            record_count=r.record_count,
            status=r.status,
            started_at=r.started_at,
            completed_at=r.completed_at,
            summary=r.summary,
            error=r.error,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=RunSummaryResponse)
def get_run(run_id: str, db: Session = Depends(get_db)) -> RunSummaryResponse:
    try:
        run = reconciliation_service.get_run(db, run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunSummaryResponse(
        run_id=run.id,
        dataset_id=run.dataset_id,
        record_count=run.record_count,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        summary=run.summary,
        error=run.error,
    )


@router.get("/runs/{run_id}/results", response_model=list[ReconciliationResultResponse])
def get_run_results(
    run_id: str,
    status: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    try:
        results = reconciliation_service.list_results(db, run_id=run_id, match_status=status)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return results
