"""Deterministic natural-language question routing.

Maps a controller question to one of a small, fixed set of allowlisted
fact-retrieval functions (`app.ai.facts`) using plain Python pattern
matching — no LLM call is involved in deciding which backend function
runs, and the LLM is never given the ability to pick or invoke a
backend operation itself. This is the "constrained query/data-
retrieval approach" the AI safety boundary requires: the model only
ever sees the small facts payload this router already decided to
fetch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai import facts as f
from app.services.errors import NotFoundError

_TXN_PATTERN = re.compile(r"\bTXN-[A-Za-z0-9-]+\b", re.IGNORECASE)

# Finance-relevant keywords used only to decide whether an unmatched
# question is "in-domain but not one of our specific categories" vs.
# "outside supported capabilities entirely" — never used to fetch data.
_FINANCE_KEYWORDS = re.compile(
    r"reconcil|transaction|exception|payment|settlement|risk|amount|match|"
    r"auto.?resolv|severity|resolve|review|dataset|\brun\b|txn|dashboard",
    re.IGNORECASE,
)

_RULES: list[tuple[str, re.Pattern]] = [
    (
        "unresolved_high_severity",
        re.compile(r"high[- ]severity|critical|unresolved", re.IGNORECASE),
    ),
    (
        "auto_resolved_count",
        re.compile(r"auto[- ]?resolved|automatically resolved", re.IGNORECASE),
    ),
    (
        "exception_rate_by_payment_method",
        re.compile(r"payment method|\bupi\b|\bcard\b|netbanking|\bwallet\b|\bemi\b", re.IGNORECASE),
    ),
    (
        "amount_at_risk",
        re.compile(r"at risk|exposure|money.*(risk|exposed)|how much", re.IGNORECASE),
    ),
    (
        "exception_causes",
        re.compile(r"cause|reason|biggest|most.*(failur|unreconcil)", re.IGNORECASE),
    ),
    (
        "exception_severity_breakdown",
        re.compile(r"severity breakdown|by severity", re.IGNORECASE),
    ),
]


@dataclass
class RoutedQuery:
    intent: str
    facts: dict


def route(db: Session, run_id: str, question: str) -> RoutedQuery:
    txn_match = _TXN_PATTERN.search(question)
    if txn_match:
        txn_id = txn_match.group(0).upper()
        try:
            return RoutedQuery("explain_transaction", f.explain_transaction(db, run_id, txn_id))
        except NotFoundError:
            return RoutedQuery(
                "unsupported",
                {"reason": f"no transaction '{txn_id}' found in run '{run_id}'"},
            )

    for intent, pattern in _RULES:
        if not pattern.search(question):
            continue
        if intent == "unresolved_high_severity":
            return RoutedQuery(intent, f.unresolved_high_severity(db, run_id))
        if intent == "auto_resolved_count":
            return RoutedQuery(intent, f.auto_resolved_count(db, run_id))
        if intent == "exception_rate_by_payment_method":
            return RoutedQuery(intent, f.exception_rate_by_payment_method(db, run_id))
        if intent == "amount_at_risk":
            return RoutedQuery(intent, f.dashboard_summary(db, run_id))
        if intent == "exception_causes":
            return RoutedQuery(intent, f.exception_counts_by_type(db, run_id))
        if intent == "exception_severity_breakdown":
            return RoutedQuery(intent, f.exception_counts_by_severity(db, run_id))

    if _FINANCE_KEYWORDS.search(question):
        return RoutedQuery("dashboard_overview", f.dashboard_summary(db, run_id))

    return RoutedQuery(
        "unsupported",
        {
            "reason": "question does not match a supported finance-data category",
            "supported_categories": [
                "exception causes/counts by type",
                "exception counts by severity",
                "amount at risk / dashboard totals",
                "exception rate by payment method",
                "auto-resolved exception count",
                "unresolved high-severity exceptions",
                "why a specific transaction (TXN-...) wasn't reconciled",
            ],
        },
    )
