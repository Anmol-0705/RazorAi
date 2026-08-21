"""Tunables for the deterministic reconciliation engine. No magic
constants in engine.py — all thresholds live here so Phase 3's
auto-resolution rules can reuse/override them without touching the
matching logic itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal


@dataclass(frozen=True)
class ReconciliationConfig:
    # Standard fee schedule used to compute the expected net settlement
    # amount for a payment. A business rule, not a peek at ground truth.
    fee_rate: Decimal = Decimal("0.02")
    tax_rate: Decimal = Decimal("0.18")

    # Rounding/float-noise tolerance before an amount difference counts
    # as a real discrepancy.
    amount_tolerance: Decimal = Decimal("0.01")

    # How far the settlement's reported fee may deviate from the
    # standard fee schedule before it's a fee mismatch rather than noise.
    fee_tolerance: Decimal = Decimal("0.01")

    # If settled_amount falls below this fraction of the expected net
    # amount, classify as a partial settlement rather than a plain
    # amount mismatch.
    partial_settlement_threshold: Decimal = Decimal("0.90")

    # Settlements arriving later than this after payment.created_at are
    # flagged as delayed (still matched via reference + timestamp
    # tolerance, tier 3 of the matching hierarchy).
    delayed_settlement_threshold: timedelta = timedelta(hours=72)
