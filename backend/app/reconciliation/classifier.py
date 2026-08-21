"""Deterministic severity/action classification for exception types.

Kept separate from engine.py's matching logic so Phase 3's bounded
auto-resolution can extend or override this table without touching how
payments and settlements are matched. `auto_resolvable` here is a
classification flag only — this phase never acts on it (no
auto-resolution is executed).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import ExceptionType, RecommendedAction, Severity


@dataclass(frozen=True)
class ExceptionPolicy:
    severity: Severity
    recommended_action: RecommendedAction
    auto_resolvable: bool


_POLICY: dict[ExceptionType, ExceptionPolicy] = {
    ExceptionType.MISSING_SETTLEMENT: ExceptionPolicy(Severity.HIGH, RecommendedAction.ESCALATE, False),
    ExceptionType.DUPLICATE_SETTLEMENT: ExceptionPolicy(Severity.MEDIUM, RecommendedAction.REQUEST_INFO, False),
    ExceptionType.AMOUNT_MISMATCH: ExceptionPolicy(Severity.MEDIUM, RecommendedAction.REQUEST_INFO, False),
    ExceptionType.PARTIAL_SETTLEMENT: ExceptionPolicy(Severity.HIGH, RecommendedAction.ESCALATE, False),
    ExceptionType.FEE_MISMATCH: ExceptionPolicy(Severity.LOW, RecommendedAction.AUTO_RESOLVE, True),
    ExceptionType.DELAYED_SETTLEMENT: ExceptionPolicy(Severity.LOW, RecommendedAction.AUTO_RESOLVE, True),
    ExceptionType.INVALID_REFERENCE: ExceptionPolicy(Severity.HIGH, RecommendedAction.ESCALATE, False),
    ExceptionType.OTHER: ExceptionPolicy(Severity.MEDIUM, RecommendedAction.ESCALATE, False),
}


def policy_for(exception_type: ExceptionType) -> ExceptionPolicy:
    return _POLICY[exception_type]
