"""Anthropic (Claude) implementation of the AIProvider interface.

All provider-specific concerns live here: SDK client construction,
prompt text, response parsing, and error-to-AIResult translation. No
other module imports `anthropic` directly.

Safety design: the model is only ever given a small, pre-computed
facts payload (see app/ai/facts.py) and a strict instruction to copy
numbers verbatim rather than compute them — the same rule enforced
structurally elsewhere (the reconciliation/auto-resolution engines
never let the LLM touch matching or money logic; this file is the one
place an LLM call happens at all, and it never sees more than the
facts it's handed).
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

import anthropic

from app.ai.provider import AIProvider, AIResult

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.MULTILINE)

SAFETY_PREAMBLE = (
    "You are a financial reconciliation assistant embedded in RazorRecon AI, "
    "an internal Razorpay finance-operations tool. You only interpret and "
    "explain the structured facts given to you as JSON in the user message — "
    "you never calculate totals, balances, match status, or financial "
    "exposure yourself, and you never invent transaction data absent from "
    "those facts. Every number in your answer must be copied verbatim from "
    "the given facts — never compute, round, or estimate a new one. If the "
    "facts don't support a confident answer, say so explicitly instead of "
    "guessing. Respond with a single JSON object only — no prose before or "
    "after it, no markdown code fences — matching exactly the schema "
    "described in the user message."
)

DEFAULT_MODEL = "claude-opus-5"


def _extract_json(text: str) -> Optional[dict]:
    cleaned = _JSON_FENCE.sub("", text.strip())
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


class AnthropicAIProvider(AIProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 20.0,
    ):
        self._api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("AI_MODEL", DEFAULT_MODEL)
        self._client = (
            anthropic.Anthropic(api_key=self._api_key, timeout=timeout, max_retries=1)
            if self._api_key
            else None
        )

    @property
    def available(self) -> bool:
        return self._client is not None

    def _unavailable(
        self, message: str = "AI provider is not configured (no ANTHROPIC_API_KEY set)"
    ) -> AIResult:
        return AIResult(available=False, error=message)

    def _call(self, user_message: str, max_tokens: int = 700) -> AIResult:
        if self._client is None:
            return self._unavailable()
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=SAFETY_PREAMBLE,
                messages=[{"role": "user", "content": user_message}],
            )
        except anthropic.AuthenticationError:
            return AIResult(available=False, error="AI provider rejected the configured API key")
        except anthropic.RateLimitError:
            return AIResult(available=False, error="AI provider is rate-limited right now")
        except anthropic.APITimeoutError:
            return AIResult(available=False, error="AI provider timed out")
        except anthropic.APIConnectionError:
            return AIResult(available=False, error="could not reach the AI provider")
        except anthropic.APIStatusError as exc:
            return AIResult(
                available=False, error=f"AI provider returned an error (status {exc.status_code})"
            )
        except Exception:  # noqa: BLE001 - an AI failure must never break the request
            return AIResult(available=False, error="AI provider returned an unexpected error")

        text = next((block.text for block in response.content if block.type == "text"), "")
        parsed = _extract_json(text) if text else None
        if parsed is None:
            return AIResult(
                available=False, error="AI provider returned a response that could not be parsed"
            )
        return AIResult(available=True, structured=parsed)

    def explain_exception(self, facts: dict) -> AIResult:
        prompt = (
            "Facts (JSON):\n"
            + json.dumps(facts, indent=2)
            + "\n\nExplain this reconciliation exception for a finance operations "
            "reviewer who has not seen it before. Respond with JSON: "
            '{"explanation": string, "likely_cause": string, '
            '"recommended_next_action": string, "uncertainty_note": string or null}'
        )
        return self._call(prompt)

    def recommend_resolution(self, facts: dict) -> AIResult:
        prompt = (
            "Facts (JSON):\n"
            + json.dumps(facts, indent=2)
            + "\n\nRecommend how a human reviewer should resolve this exception. "
            "The facts already include a system-computed recommended_action and "
            "auto_resolvable flag — explain and expand on those, do not override "
            'them. Respond with JSON: {"recommended_action": string, "rationale": '
            'string, "confidence_note": string or null}'
        )
        return self._call(prompt)

    def answer_query(self, question: str, intent: str, facts: dict) -> AIResult:
        prompt = (
            f"Matched question category: {intent}\n"
            f"User question: {question}\n\n"
            "Facts (JSON) — the only data you may reference or cite numbers from:\n"
            + json.dumps(facts, indent=2)
            + "\n\nAnswer the user's question using only these facts. "
            'Respond with JSON: {"answer": string, "caveats": string or null}'
        )
        return self._call(prompt)

    def summarize_reconciliation(self, facts: dict) -> AIResult:
        prompt = (
            "Facts (JSON):\n"
            + json.dumps(facts, indent=2)
            + "\n\nWrite a concise operational summary of this completed "
            "reconciliation run for a finance manager. "
            'Respond with JSON: {"summary": string, '
            '"largest_exception_categories": string, '
            '"financial_exposure_note": string, "unresolved_cases_note": '
            'string, "suggested_focus": string}'
        )
        return self._call(prompt, max_tokens=900)


def get_ai_provider() -> AIProvider:
    """FastAPI dependency. A fresh instance per request is cheap (just
    an env lookup + a lightweight client object) and lets tests swap in
    a mock via `app.dependency_overrides` without env-var gymnastics."""
    return AnthropicAIProvider()
