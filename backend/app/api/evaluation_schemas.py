"""Pydantic schemas for the /evaluation/* endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RunEvaluationRequest(BaseModel):
    dataset_name: str = Field(default="n250")


class EvaluationRunResponse(BaseModel):
    evaluation_id: str
    dataset_name: str
    reconciliation_run_id: str
    record_count: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    metrics: Optional[dict] = None
    error: Optional[str] = None


class RunStressEvaluationRequest(BaseModel):
    dataset_name: str = Field(default="n250")


class StressEvaluationRunResponse(BaseModel):
    stress_evaluation_id: str
    dataset_name: str
    seed: int
    record_count: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    noise_summary: Optional[dict] = None
    metrics: Optional[dict] = None
    error: Optional[str] = None
