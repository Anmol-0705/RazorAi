"""Pydantic request/response schemas for the API layer."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, Field

# ORM Numeric columns load as Decimal; coerce to str at the API
# boundary so JSON responses carry exact monetary values, not floats.
MoneyStr = Annotated[str, BeforeValidator(str)]


class HealthResponse(BaseModel):
    status: str
    database: str


class GenerateDatasetRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    num_records: int = Field(default=100, gt=0, le=5000)


class GenerateDatasetResponse(BaseModel):
    dataset_id: str
    seed: int
    num_records: int
    payment_count: int
    settlement_count: int
    created: bool


class RunReconciliationRequest(BaseModel):
    dataset_id: str
    run_id: Optional[str] = Field(
        default=None,
        description="Optional idempotency key. Re-posting the same run_id after it "
        "completed returns the existing result instead of recomputing.",
    )


class RunSummaryResponse(BaseModel):
    run_id: str
    dataset_id: str
    record_count: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    summary: Optional[dict]
    error: Optional[str]


class ReconciliationResultResponse(BaseModel):
    id: str
    run_id: str
    payment_reference: str
    settlement_reference: Optional[str]
    match_status: str
    match_strategy: Optional[str]
    confidence: float
    amount_difference: MoneyStr
    reason: str
    created_at: datetime

    # Denormalized payment/settlement/exception fields, joined in
    # app.services.reconciliation_service for the transaction-list and
    # exception-detail views. Optional because a row's payment or
    # settlement side (or associated exception) may not exist — e.g. an
    # orphaned settlement has no payment.
    order_id: Optional[str] = None
    payment_amount: Optional[MoneyStr] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    settlement_status: Optional[str] = None
    settled_amount: Optional[MoneyStr] = None
    fee: Optional[MoneyStr] = None
    tax: Optional[MoneyStr] = None
    exception_type: Optional[str] = None
    exception_review_status: Optional[str] = None
    exception_id: Optional[str] = None

    model_config = {"from_attributes": True}


class ExceptionCaseResponse(BaseModel):
    id: str
    run_id: str
    reconciliation_result_id: str
    payment_reference: str
    exception_type: str
    severity: str
    confidence: float
    financial_impact: MoneyStr
    recommended_action: str
    auto_resolvable: bool
    review_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AutoResolutionRecordResponse(BaseModel):
    id: str
    exception_case_id: str
    resolution_type: str
    reason: str
    actor: str
    financial_impact: MoneyStr
    previous_status: str
    new_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewAuditResponse(BaseModel):
    id: str
    exception_case_id: str
    actor: str
    action: str
    note: str
    previous_status: str
    new_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ActionExecutionResponse(BaseModel):
    id: str
    exception_case_id: str
    action_type: str
    actor: str
    reason: str
    rule_id: str
    status: str
    idempotency_key: str
    resulting_reference: str
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ControllerActionEligibilityResponse(BaseModel):
    eligible: bool
    action_type: Optional[str] = None
    reason: str
    rule_id: str

    model_config = {"from_attributes": True}


class ExecuteActionResponse(BaseModel):
    eligible: bool
    reason: str
    rule_id: str
    already_executed: bool = False
    action: Optional[ActionExecutionResponse] = None
    audit: Optional[ReviewAuditResponse] = None
    exception: Optional[ExceptionCaseResponse] = None


class ExceptionDetailResponse(BaseModel):
    exception: ExceptionCaseResponse
    result: Optional[ReconciliationResultResponse] = None
    auto_resolutions: list[AutoResolutionRecordResponse]
    review_audits: list[ReviewAuditResponse]
    action_executions: list[ActionExecutionResponse] = []
    controller_action: Optional[ControllerActionEligibilityResponse] = None


class ReviewActionRequest(BaseModel):
    reviewer: str = Field(min_length=1)
    note: str = ""


class ReviewActionResponse(BaseModel):
    exception: ExceptionCaseResponse
    audit: ReviewAuditResponse


class DashboardSummaryResponse(BaseModel):
    run_id: Optional[str]
    total_transactions: int
    matched: int
    unmatched: int
    partial: int
    duplicate: int
    exceptions: int
    match_rate: float
    amount_reconciled: MoneyStr
    amount_at_risk: MoneyStr
    auto_resolution_rate: float


class ErrorResponse(BaseModel):
    detail: str
