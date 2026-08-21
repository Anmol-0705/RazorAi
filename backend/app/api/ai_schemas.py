"""Pydantic schemas for the /ai/* endpoints.

Response fields are optional across the board because a single
response model covers both the "ai_available: true" shape (fields the
provider filled in) and the "ai_available: false" shape (just
`facts` + `error`) — the AI being down is a normal, not exceptional,
response shape (see backend/app/ai/service.py).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AIQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    run_id: Optional[str] = None


class ExceptionAIResponse(BaseModel):
    facts: dict
    ai_available: bool
    ai_generated: bool
    error: Optional[str] = None
    # explain_exception fields
    explanation: Optional[str] = None
    likely_cause: Optional[str] = None
    recommended_next_action: Optional[str] = None
    uncertainty_note: Optional[str] = None
    # recommend_resolution fields
    recommended_action: Optional[str] = None
    rationale: Optional[str] = None
    confidence_note: Optional[str] = None


class AIQueryResponse(BaseModel):
    question: str
    intent: str
    facts: dict
    ai_available: bool
    ai_generated: bool
    answer: Optional[str] = None
    caveats: Optional[str] = None
    error: Optional[str] = None


class ReconciliationSummaryResponse(BaseModel):
    facts: dict
    ai_available: bool
    ai_generated: bool
    summary: Optional[str] = None
    largest_exception_categories: Optional[str] = None
    financial_exposure_note: Optional[str] = None
    unresolved_cases_note: Optional[str] = None
    suggested_focus: Optional[str] = None
    error: Optional[str] = None
