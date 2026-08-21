"""ReconciliationResult schema.

Not populated in Phase 1 — the deterministic reconciliation engine
that produces these lives in a later phase. Defined now so the shape
is fixed and later phases build against a stable contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.models.enums import MatchStatus, MatchStrategy
from app.validation import (
    require_non_empty_str,
    require_valid_enum_member,
    require_valid_timestamp,
)


@dataclass(frozen=True)
class ReconciliationResult:
    id: str
    payment_reference: str
    settlement_reference: Optional[str]
    match_status: MatchStatus
    match_strategy: Optional[MatchStrategy]
    confidence: float
    amount_difference: Decimal
    reason: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty_str(self.id, "id")
        require_non_empty_str(self.payment_reference, "payment_reference")
        require_valid_enum_member(self.match_status, MatchStatus, "match_status")
        if not (0.0 <= self.confidence <= 1.0):
            from app.validation import ValidationError

            raise ValidationError("confidence must be between 0.0 and 1.0")
        require_valid_timestamp(self.created_at, "created_at")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["match_status"] = self.match_status.value
        data["match_strategy"] = self.match_strategy.value if self.match_strategy else None
        data["amount_difference"] = str(self.amount_difference)
        data["created_at"] = self.created_at.isoformat()
        return data
