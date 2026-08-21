"""Abstract AI provider interface.

Application code (backend/app/ai/service.py, the /ai/* routes) only
ever depends on this interface — never on a specific vendor SDK — so
swapping providers, or the provider being absent/down, never affects
reconciliation, persistence, dashboard, or review functionality. See
ARCHITECTURE.md and DECISIONS.md D001/D002 for the same principle
applied to reconciliation; this module applies it to the AI layer.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIResult:
    """Outcome of one AI call. `structured` is only populated when
    `available` is True and the provider's response parsed cleanly."""

    available: bool
    structured: Optional[dict] = None
    error: Optional[str] = None


class AIProvider(ABC):
    """Every method must return an `AIResult` — never raise — so a
    provider outage degrades to `available=False` instead of a 500."""

    @abstractmethod
    def explain_exception(self, facts: dict) -> AIResult: ...

    @abstractmethod
    def recommend_resolution(self, facts: dict) -> AIResult: ...

    @abstractmethod
    def answer_query(self, question: str, intent: str, facts: dict) -> AIResult: ...

    @abstractmethod
    def summarize_reconciliation(self, facts: dict) -> AIResult: ...
