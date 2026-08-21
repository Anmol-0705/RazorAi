"""Held-out ground-truth evaluation endpoints (Phase 7).

Routes only orchestrate `app.evaluation.service`, which runs the exact
production reconciliation pipeline against the committed held-out
dataset and scores it deterministically — see docs/evaluation.md.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.evaluation_schemas import EvaluationRunResponse, RunEvaluationRequest
from app.db.base import get_db
from app.evaluation import service as evaluation_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/run", response_model=EvaluationRunResponse)
def run_evaluation(request: RunEvaluationRequest, db: Session = Depends(get_db)):
    try:
        return evaluation_service.run_evaluation(db, dataset_name=request.dataset_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/latest", response_model=EvaluationRunResponse)
def get_latest_evaluation(db: Session = Depends(get_db)):
    try:
        return evaluation_service.get_latest_evaluation(db)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{evaluation_id}", response_model=EvaluationRunResponse)
def get_evaluation(evaluation_id: str, db: Session = Depends(get_db)):
    try:
        return evaluation_service.get_evaluation(db, evaluation_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
