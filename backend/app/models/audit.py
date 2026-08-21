"""Minimal review/audit trail schema.

Deliberately minimal per Phase 1 scope ("do not over-engineer yet").
One row per human decision made against an ExceptionCase.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from app.models.enums import ReviewStatus
from app.validation import (
    require_non_empty_str,
    require_valid_enum_member,
    require_valid_timestamp,
)


@dataclass(frozen=True)
class ReviewAudit:
    id: str
    exception_case_id: str
    reviewer: str
    decision: ReviewStatus
    notes: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty_str(self.id, "id")
        require_non_empty_str(self.exception_case_id, "exception_case_id")
        require_non_empty_str(self.reviewer, "reviewer")
        require_valid_enum_member(self.decision, ReviewStatus, "decision")
        require_valid_timestamp(self.created_at, "created_at")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["decision"] = self.decision.value
        data["created_at"] = self.created_at.isoformat()
        return data
