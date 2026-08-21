"""AI-assisted endpoints: exception explanation, natural-language
controller queries, and reconciliation summaries.

Routes only orchestrate `app.ai.service`, which retrieves deterministic
facts (`app.ai.facts` / `app.ai.query_router`) and asks the configured
`AIProvider` to phrase them. The AI never computes a number, never
picks which backend function runs, and every failure mode (no key,
timeout, bad response) degrades to a structured `ai_available: false`
response rather than a 500 — see docs/ai-architecture.md.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai import service as ai_service
from app.ai.anthropic_provider import get_ai_provider
from app.ai.provider import AIProvider
from app.api.ai_schemas import (
    AIQueryRequest,
    AIQueryResponse,
    ExceptionAIResponse,
    ReconciliationSummaryResponse,
)
from app.db.base import get_db
from app.services.errors import NotFoundError

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/exceptions/{exception_id}/explain", response_model=ExceptionAIResponse)
def explain_exception(
    exception_id: str,
    db: Session = Depends(get_db),
    provider: AIProvider = Depends(get_ai_provider),
):
    try:
        return ai_service.explain_exception(db, provider, exception_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/exceptions/{exception_id}/recommend", response_model=ExceptionAIResponse)
def recommend_resolution(
    exception_id: str,
    db: Session = Depends(get_db),
    provider: AIProvider = Depends(get_ai_provider),
):
    try:
        return ai_service.recommend_resolution(db, provider, exception_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/query", response_model=AIQueryResponse)
def query(
    request: AIQueryRequest,
    db: Session = Depends(get_db),
    provider: AIProvider = Depends(get_ai_provider),
):
    try:
        return ai_service.answer_controller_query(db, provider, request.question, run_id=request.run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/summary", response_model=ReconciliationSummaryResponse)
def summarize(
    run_id: str,
    db: Session = Depends(get_db),
    provider: AIProvider = Depends(get_ai_provider),
):
    try:
        return ai_service.summarize_reconciliation(db, provider, run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
