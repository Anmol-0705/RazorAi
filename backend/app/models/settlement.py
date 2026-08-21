"""Settlement domain model.

`transaction_reference` is the settlement's claimed link back to a
Payment.transaction_id. It is intentionally NOT enforced to exist in
practice, because the invalid-reference anomaly requires generating
settlements with a broken/unmatched reference. Referential resolution
is the reconciliation engine's job (a later phase), not this model's.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal

from app.models.enums import SettlementStatus
from app.validation import (
    require_non_empty_str,
    require_non_negative_amount,
    require_positive_amount,
    require_valid_enum_member,
    require_valid_timestamp,
)


@dataclass(frozen=True)
class Settlement:
    id: str
    settlement_id: str
    transaction_reference: str
    settled_amount: Decimal
    fee: Decimal
    tax: Decimal
    settlement_status: SettlementStatus
    settled_at: datetime

    def __post_init__(self) -> None:
        require_non_empty_str(self.id, "id")
        require_non_empty_str(self.settlement_id, "settlement_id")
        require_non_empty_str(self.transaction_reference, "transaction_reference")
        require_positive_amount(self.settled_amount, "settled_amount")
        require_non_negative_amount(self.fee, "fee")
        require_non_negative_amount(self.tax, "tax")
        require_valid_enum_member(self.settlement_status, SettlementStatus, "settlement_status")
        require_valid_timestamp(self.settled_at, "settled_at")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["settled_amount"] = str(self.settled_amount)
        data["fee"] = str(self.fee)
        data["tax"] = str(self.tax)
        data["settlement_status"] = self.settlement_status.value
        data["settled_at"] = self.settled_at.isoformat()
        return data
