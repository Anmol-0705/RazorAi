"""Configuration for the synthetic data generator. No magic constants
in generator.py — all tunables live here."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.data_generation.enums import GroundTruthCondition
from app.models.enums import Currency, PaymentMethod

DEFAULT_ANOMALY_WEIGHTS: dict[GroundTruthCondition, float] = {
    GroundTruthCondition.NORMAL_MATCH: 0.55,
    GroundTruthCondition.MISSING_SETTLEMENT: 0.07,
    GroundTruthCondition.DUPLICATE_SETTLEMENT: 0.06,
    GroundTruthCondition.AMOUNT_MISMATCH: 0.08,
    GroundTruthCondition.PARTIAL_SETTLEMENT: 0.08,
    GroundTruthCondition.FEE_MISMATCH: 0.06,
    GroundTruthCondition.DELAYED_SETTLEMENT: 0.06,
    GroundTruthCondition.INVALID_REFERENCE: 0.04,
}


@dataclass
class GeneratorConfig:
    seed: int
    num_records: int
    base_date: datetime = datetime(2026, 1, 1)
    currencies: tuple = (Currency.INR, Currency.USD)
    payment_methods: tuple = tuple(PaymentMethod)
    anomaly_weights: dict = field(default_factory=lambda: dict(DEFAULT_ANOMALY_WEIGHTS))

    def __post_init__(self) -> None:
        if self.num_records <= 0:
            raise ValueError("num_records must be positive")
        total_weight = sum(self.anomaly_weights.values())
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(f"anomaly_weights must sum to 1.0, got {total_weight}")
