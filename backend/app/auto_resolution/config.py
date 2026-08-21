"""Tunables for bounded auto-resolution.

Kept separate from the reconciliation engine's config
(`backend/app/reconciliation/config.py`): that engine decides *what
happened*; this module decides whether a safe, bounded corrective
action can be taken automatically for what already happened.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ACTOR = "system:auto_resolution_engine"


@dataclass(frozen=True)
class AutoResolutionConfig:
    # Fee mismatches are only auto-resolved below this rupee cap;
    # anything larger goes to human review regardless of the
    # classifier's severity rating.
    max_auto_fee_adjustment: Decimal = Decimal("100.00")

    # Delayed settlements never carry a direct financial impact by
    # construction (the money still arrived in full), but the cap is
    # enforced anyway as a defensive bound.
    max_auto_delay_financial_impact: Decimal = Decimal("0.01")

    # A duplicate settlement is only auto-suppressed when its amount
    # exactly matches the primary settlement — i.e. unambiguously the
    # same event recorded twice, not a second, possibly legitimate,
    # transaction that merely shares a reference.
    max_auto_duplicate_financial_impact: Decimal = Decimal("0.00")
