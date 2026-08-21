"""AutoResolutionRecord schema.

One immutable row per automated corrective action the auto-resolution
engine (`backend/app/auto_resolution/`) took against an ExceptionCase.
Never mutated after creation — it is the audit trail proving what an
automated system did, why, and what changed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal

from app.models.enums import ResolutionType, ReviewStatus
from app.validation import (
    require_non_empty_str,
    require_valid_enum_member,
    require_valid_timestamp,
)


@dataclass(frozen=True)
class AutoResolutionRecord:
    id: str
    exception_case_id: str
    resolution_type: ResolutionType
    reason: str
    actor: str
    financial_impact: Decimal
    previous_status: ReviewStatus
    new_status: ReviewStatus
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty_str(self.id, "id")
        require_non_empty_str(self.exception_case_id, "exception_case_id")
        require_valid_enum_member(self.resolution_type, ResolutionType, "resolution_type")
        require_non_empty_str(self.reason, "reason")
        require_non_empty_str(self.actor, "actor")
        require_valid_enum_member(self.previous_status, ReviewStatus, "previous_status")
        require_valid_enum_member(self.new_status, ReviewStatus, "new_status")
        require_valid_timestamp(self.created_at, "created_at")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["resolution_type"] = self.resolution_type.value
        data["financial_impact"] = str(self.financial_impact)
        data["previous_status"] = self.previous_status.value
        data["new_status"] = self.new_status.value
        data["created_at"] = self.created_at.isoformat()
        return data
