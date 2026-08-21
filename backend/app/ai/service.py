"""Orchestrates AI-assisted operations.

Every function here follows the same shape: retrieve deterministic
facts (via `app.ai.facts` / `app.ai.query_router`, never raw SQL, never
an LLM-chosen operation), then ask the configured `AIProvider` to
interpret/word them. The provider is never responsible for computing a
number, deciding match status, or picking which backend function ran —
this module always decides that first, and the facts it computed are
returned alongside the AI's answer so the UI can show both.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.ai import facts as f
from app.ai.provider import AIProvider, AIResult
from app.ai.query_router import route
from app.services import dashboard_service
from app.services.errors import NotFoundError

# Hallucination guardrail: any number the AI writes in its free-text
# fields must already appear somewhere in the facts it was given.
# Only numbers with 3+ digits are checked — smaller numbers (counts,
# rankings like "2nd") are too common in normal prose to reliably
# signal a fabricated figure, but a fabricated financial amount is
# almost always 3+ digits.
_NUMBER_PATTERN = re.compile(r"\d[\d,]*\.?\d*")


def _numbers_in(text: str) -> set[str]:
    return {m.replace(",", "") for m in _NUMBER_PATTERN.findall(text)}


def _check_for_fabricated_numbers(structured: dict, facts: dict) -> Optional[str]:
    known_numbers = _numbers_in(json.dumps(facts, default=str))
    for value in structured.values():
        if not isinstance(value, str):
            continue
        for number in _numbers_in(value):
            digits = number.replace(".", "")
            if len(digits) >= 3 and number not in known_numbers:
                return (
                    f"AI response referenced a number ({number}) that does not appear in the "
                    "backend-supplied facts — discarded rather than shown as a trustworthy answer"
                )
    return None

UNSUPPORTED_MESSAGE = (
    "I can only answer questions grounded in this run's reconciliation data: "
    "exception causes/counts by type, exception counts by severity, amount "
    "at risk, exception rate by payment method, auto-resolved counts, "
    "unresolved high-severity exceptions, and why a specific transaction "
    "(e.g. TXN-42-000007) wasn't reconciled. Try rephrasing your question in "
    "those terms."
)


def _resolve_run_id(db: Session, run_id: Optional[str]) -> str:
    if run_id:
        return run_id
    summary = dashboard_service.compute_summary(db)
    if not summary.get("run_id"):
        raise NotFoundError("no completed reconciliation run exists yet")
    return summary["run_id"]


def _serialize_exception_facts(detail: dict) -> dict:
    exc = detail["exception"]
    result = detail.get("result")
    return f.to_jsonable(
        {
            "transaction_id": exc.payment_reference,
            "exception_type": exc.exception_type,
            "severity": exc.severity,
            "confidence": exc.confidence,
            "financial_impact": exc.financial_impact,
            "recommended_action": exc.recommended_action,
            "auto_resolvable": exc.auto_resolvable,
            "review_status": exc.review_status,
            "match_status": result.get("match_status") if result else None,
            "match_strategy": result.get("match_strategy") if result else None,
            "reason": result.get("reason") if result else None,
            "payment_amount": result.get("payment_amount") if result else None,
            "settled_amount": result.get("settled_amount") if result else None,
            "amount_difference": result.get("amount_difference") if result else None,
            "payment_method": result.get("payment_method") if result else None,
            "settlement_status": result.get("settlement_status") if result else None,
        }
    )


def _respond(facts: dict, result: AIResult) -> dict:
    if not result.available:
        return {"facts": facts, "ai_available": False, "ai_generated": False, "error": result.error}

    structured = result.structured or {}
    warning = _check_for_fabricated_numbers(structured, facts)
    if warning:
        return {"facts": facts, "ai_available": False, "ai_generated": False, "error": warning}

    return {"facts": facts, "ai_available": True, "ai_generated": True, **structured}


def explain_exception(db: Session, provider: AIProvider, exception_id: str) -> dict:
    detail = f.exception_detail_facts(db, exception_id)
    facts = _serialize_exception_facts(detail)
    return _respond(facts, provider.explain_exception(facts))


def recommend_resolution(db: Session, provider: AIProvider, exception_id: str) -> dict:
    detail = f.exception_detail_facts(db, exception_id)
    facts = _serialize_exception_facts(detail)
    return _respond(facts, provider.recommend_resolution(facts))


def answer_controller_query(
    db: Session, provider: AIProvider, question: str, run_id: Optional[str] = None
) -> dict:
    resolved_run_id = _resolve_run_id(db, run_id)
    routed = route(db, resolved_run_id, question)

    if routed.intent == "unsupported":
        return {
            "question": question,
            "intent": routed.intent,
            "facts": routed.facts,
            "ai_available": True,
            "ai_generated": False,
            "answer": UNSUPPORTED_MESSAGE,
        }

    response = _respond(routed.facts, provider.answer_query(question, routed.intent, routed.facts))
    response["question"] = question
    response["intent"] = routed.intent
    return response


def summarize_reconciliation(db: Session, provider: AIProvider, run_id: str) -> dict:
    summary = dashboard_service.compute_summary(db, run_id=run_id)
    if not summary.get("run_id"):
        raise NotFoundError(f"no completed reconciliation run found with id '{run_id}'")
    facts = {
        "summary": summary,
        "exceptions_by_type": f.exception_counts_by_type(db, run_id),
        "unresolved_high_severity": f.unresolved_high_severity(db, run_id),
    }
    return _respond(facts, provider.summarize_reconciliation(facts))
