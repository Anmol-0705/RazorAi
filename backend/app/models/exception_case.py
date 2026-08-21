"""ExceptionCase schema.

Not populated in Phase 1. Produced later by the deterministic exception
classifier; `recommended_action`/`auto_resolvable` are rule-driven, not
LLM-driven (see ARCHITECTURE.md).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal

from app.models.enums import ExceptionType, RecommendedAction, ReviewStatus, Severity
from app.validation import (
    require_non_empty_str,
    require_valid_enum_member,
    require_valid_timestamp,
)


@dataclass(frozen=True)
class ExceptionCase:
    id: str
    reconciliation_result_id: str
    exception_type: ExceptionType
    severity: Severity
    confidence: float
    financial_impact: Decimal
    recommended_action: RecommendedAction
    auto_resolvable: bool
    review_status: ReviewStatus
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty_str(self.id, "id")
        require_non_empty_str(self.reconciliation_result_id, "reconciliation_result_id")
        require_valid_enum_member(self.exception_type, ExceptionType, "exception_type")
        require_valid_enum_member(self.severity, Severity, "severity")
        require_valid_enum_member(self.recommended_action, RecommendedAction, "recommended_action")
        require_valid_enum_member(self.review_status, ReviewStatus, "review_status")
        if not (0.0 <= self.confidence <= 1.0):
            from app.validation import ValidationError

            raise ValidationError("confidence must be between 0.0 and 1.0")
        require_valid_timestamp(self.created_at, "created_at")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["exception_type"] = self.exception_type.value
        data["severity"] = self.severity.value
        data["financial_impact"] = str(self.financial_impact)
        data["recommended_action"] = self.recommended_action.value
        data["review_status"] = self.review_status.value
        data["created_at"] = self.created_at.isoformat()
        return data
