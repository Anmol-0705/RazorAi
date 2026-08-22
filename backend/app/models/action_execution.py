"""ActionExecution schema.

One immutable row per bounded finance-operations action the Action
Engine (`backend/app/actions/`) executed against an ExceptionCase.
Synthetic/test-mode only — `resulting_reference` is a system-generated
reference, never a real banking/settlement system identifier. See
ARCHITECTURE.md's Bounded Finance Controller Action section.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from app.models.enums import ActionStatus, ActionType
from app.validation import (
    require_non_empty_str,
    require_valid_enum_member,
    require_valid_timestamp,
)


@dataclass(frozen=True)
class ActionExecution:
    id: str
    exception_case_id: str
    action_type: ActionType
    actor: str
    reason: str
    rule_id: str
    status: ActionStatus
    idempotency_key: str
    created_at: datetime
    completed_at: Optional[datetime]
    resulting_reference: str

    def __post_init__(self) -> None:
        require_non_empty_str(self.id, "id")
        require_non_empty_str(self.exception_case_id, "exception_case_id")
        require_valid_enum_member(self.action_type, ActionType, "action_type")
        require_non_empty_str(self.actor, "actor")
        require_non_empty_str(self.reason, "reason")
        require_non_empty_str(self.rule_id, "rule_id")
        require_valid_enum_member(self.status, ActionStatus, "status")
        require_non_empty_str(self.idempotency_key, "idempotency_key")
        require_valid_timestamp(self.created_at, "created_at")
        require_non_empty_str(self.resulting_reference, "resulting_reference")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["action_type"] = self.action_type.value
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        data["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        return data
