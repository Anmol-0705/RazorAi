"""Payment domain model.

Mirrors the future `payments` SQLAlchemy/Postgres table. Implemented
as a validated, immutable dataclass for Phase 1 (see DECISIONS.md
D006 for why this is stdlib-only rather than Pydantic for now).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal

from app.models.enums import Currency, PaymentMethod, PaymentStatus
from app.validation import (
    require_non_empty_str,
    require_positive_amount,
    require_valid_currency,
    require_valid_enum_member,
    require_valid_timestamp,
)


@dataclass(frozen=True)
class Payment:
    id: str
    transaction_id: str
    order_id: str
    customer_reference: str
    amount: Decimal
    currency: Currency
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    created_at: datetime

    def __post_init__(self) -> None:
        require_non_empty_str(self.id, "id")
        require_non_empty_str(self.transaction_id, "transaction_id")
        require_non_empty_str(self.order_id, "order_id")
        require_non_empty_str(self.customer_reference, "customer_reference")
        require_positive_amount(self.amount, "amount")
        require_valid_enum_member(self.currency, Currency, "currency")
        require_valid_currency(self.currency)
        require_valid_enum_member(self.payment_method, PaymentMethod, "payment_method")
        require_valid_enum_member(self.payment_status, PaymentStatus, "payment_status")
        require_valid_timestamp(self.created_at, "created_at")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["amount"] = str(self.amount)
        data["currency"] = self.currency.value
        data["payment_method"] = self.payment_method.value
        data["payment_status"] = self.payment_status.value
        data["created_at"] = self.created_at.isoformat()
        return data
