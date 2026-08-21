"""Ground-truth record: the true underlying condition of a generated
payment, retained for later precision/recall evaluation. Never written
into ReconciliationResult/ExceptionCase output and never read by the
(future) reconciliation engine."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.data_generation.enums import GroundTruthCondition


@dataclass(frozen=True)
class GroundTruthRecord:
    payment_transaction_id: str
    condition: GroundTruthCondition
    settlement_ids: tuple
    expected_amount_difference: Decimal
    notes: str

    def to_dict(self) -> dict:
        return {
            "payment_transaction_id": self.payment_transaction_id,
            "condition": self.condition.value,
            "settlement_ids": list(self.settlement_ids),
            "expected_amount_difference": str(self.expected_amount_difference),
            "notes": self.notes,
        }
