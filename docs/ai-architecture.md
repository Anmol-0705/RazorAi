# AI Architecture (Phase 6A)

RazorRecon AI adds an AI-assisted layer for exception explanation,
resolution recommendations, natural-language querying, and
reconciliation summaries — without letting the LLM become a source of
financial truth. This document is the safety boundary reference;
implementation lives under `backend/app/ai/`.

## The one rule everything else follows

**The LLM only ever phrases facts the backend already computed.** It
never calculates a total, a balance, a match status, or a financial
exposure number; it never invents transaction data; it never mutates a
financial record or a review decision; it never picks which backend
function runs. Every number in an AI response is required to have come
from the facts payload it was given — enforced by an automatic check,
not just by prompt instruction (see "Hallucination prevention" below).

## Provider abstraction

`backend/app/ai/provider.py` defines `AIProvider` (abstract) and
`AIResult` (`available: bool`, `structured: dict | None`,
`error: str | None`). `backend/app/ai/anthropic_provider.py` is the
only concrete implementation and the only file that imports the
`anthropic` SDK — application code (`app/ai/service.py`, the `/ai/*`
routes) depends solely on the interface, so swapping providers or the
provider being absent/down never touches reconciliation, persistence,
dashboard, or review code.

`AnthropicAIProvider`:
- Reads `ANTHROPIC_API_KEY` and `AI_MODEL` (default `claude-opus-5`)
  from the environment (`.env.example`). No key is hard-coded anywhere;
  none is committed.
- Constructs its SDK client only if a key is present; `.available` is
  `False` otherwise, with no network call attempted.
- Every method catches `AuthenticationError`, `RateLimitError`,
  `APITimeoutError`, `APIConnectionError`, `APIStatusError`, and any
  other exception, translating each into `AIResult(available=False,
  error=...)` — an AI failure is always a return value, never a raised
  exception, so a route can never 500 because the AI is down.
- Prompts a fixed safety preamble (`SAFETY_PREAMBLE`) before every
  call, instructing the model to copy numbers verbatim from the given
  facts, never compute new ones, and respond with a single JSON object
  matching a schema described in the user message.
- Parses the response as JSON (stripping markdown fences if present);
  an unparseable response is itself an `AIResult(available=False, ...)`
  — never surfaced to the user as if it were a valid answer.

## Backend data retrieval (the allowlist)

`backend/app/ai/facts.py` is the **only** place the AI layer is allowed
to read data from. Every function in it is a thin wrapper around the
existing `app.services.*` layer (dashboard, exception, reconciliation
services) — no new SQL, no new aggregation beyond simple counting over
already-fetched rows. The functions:

- `dashboard_summary` — real dashboard metrics for a run
- `exception_counts_by_type` / `exception_counts_by_severity`
- `exception_rate_by_payment_method`
- `auto_resolved_count`
- `unresolved_high_severity`
- `explain_transaction` — a single transaction's reconciliation result(s)
- `exception_detail_facts` — one exception's full detail (reused from
  the existing `/exceptions/{id}` endpoint's service call)

There is no path from a user's question to raw SQL, and no path for
the LLM to invoke an arbitrary backend function. `backend/app/ai/query_router.py`
decides which of the functions above to call using **plain Python
regex pattern matching against the question text** — not an LLM tool-use
loop, not an agent framework. This was a deliberate simplicity choice:
the task's example questions map cleanly onto a small fixed set of
categories, and a deterministic router has zero risk of the model
picking an unintended operation. A question that matches no pattern
and contains none of a broad set of finance keywords gets a canned
"I don't have data for that" response — the router itself decides this,
never the model.

## Hallucination prevention

Beyond prompt instructions, `backend/app/ai/service.py._check_for_fabricated_numbers`
scans every free-text field the AI returns for 3+ digit numbers and
verifies each one appears somewhere in the JSON-serialized facts
payload the model was given. If the model writes a number that isn't
in the facts (a stand-in for a hallucinated figure), the entire
response is discarded and replaced with an `ai_available: false`
error — the UI never shows a plausible-looking but unverifiable
number. See `backend/app/tests/test_ai.py`'s `HallucinationPreventionTests`
for the test that injects exactly this failure mode via a mocked
provider.

## Graceful degradation

Every `/ai/*` endpoint returns HTTP 200 with a structured body whether
or not the AI succeeded:

```json
// ai_available: false (no key / timeout / bad response / rate limit)
{ "facts": { ... }, "ai_available": false, "ai_generated": false, "error": "..." }

// ai_available: true
{ "facts": { ... }, "ai_available": true, "ai_generated": true, "explanation": "...", ... }
```

Reconciliation, persistence, the dashboard, transactions, exceptions,
and the full human review workflow (`/exceptions/{id}/{start-review,
approve,reject,mark-resolved,add-note}`) have zero dependency on the
AI layer and are unaffected by its absence — verified in
`backend/app/tests/test_ai.py`'s `ProviderUnavailableTests` and by
running the whole app with no `ANTHROPIC_API_KEY` set (this
environment's default state; no live LLM call was made anywhere in
this phase's verification).

## Allowed vs. prohibited capabilities

| Allowed | Prohibited |
|---|---|
| Explain an exception using backend-supplied facts | Calculate a transaction total, balance, or match status |
| Recommend how to resolve an exception (advisory text only) | Determine financial exposure |
| Answer a natural-language question using pre-fetched facts | Invent transaction/payment/settlement data |
| Summarize a completed reconciliation run | Execute a review action (approve/reject/mark-resolved) |
| Word a number the backend already computed | Compute a new number not present in the given facts |
| — | Pick which backend function/query runs |
| — | See raw SQL or the whole database |

## Frontend

- `frontend/src/components/AIResultCard.jsx` renders every AI response
  with **SYSTEM FACTS** (the raw facts JSON, backend-derived) visually
  separated from **AI EXPLANATION**/**AI ANSWER** (labeled
  "AI-generated interpretation") — the AI's text never replaces or is
  styled the same as the real transaction facts. Handles loading and
  "AI unavailable" states itself so every call site gets them for free.
- `frontend/src/pages/AIControllerPage.jsx` — prompt box with the
  task's example questions as one-click buttons, a running history of
  question/facts/answer.
- Exception Detail page gained an "Explain with AI" button that shows
  the same facts/explanation split inline.

## Security

- User questions are never interpolated into SQL — they only ever flow
  through the regex-based `query_router`, which selects from the fixed
  `facts.py` function list.
- The LLM cannot execute arbitrary backend functions or generate SQL;
  it receives a pre-built facts dict and a question, and returns text.
- No secrets are ever included in a prompt or a response; the API key
  lives only in `AnthropicAIProvider`'s client construction.
- CORS remains scoped to the Vite dev origins (Phase 5, DECISIONS.md
  D016) — the `/ai/*` routes add no new origin exposure.

## The AI cannot execute — the Action Engine boundary (Phase 8)

Phase 8 (see ARCHITECTURE.md's "Bounded Finance Controller Action"
section) adds `backend/app/actions/`, a deterministic engine that
executes one small, allowlisted, synthetic downstream finance-ops
instruction for an eligible exception. This does **not** change the
one rule above — it makes the existing boundary explicit end to end:

```
Verified facts  →  AI interpretation  →  deterministic safety policy  →  bounded finance action  →  audit trail
(app.services.*)   (app.ai, optional,      (app.actions.engine,           (ActionExecutionORM +
                     never in the             reuses the exact same         ReviewAuditORM)
                     execution path)          caps as auto_resolution)
```

- `app.actions` never imports `app.ai`, and `app.ai` never imports
  `app.actions` — there is no code path connecting them. The AI can
  explain *why* an exception looks the way it does; it has no API, no
  tool-use loop, and no function call that reaches the Action Engine.
- `POST /exceptions/{id}/execute-action` takes no request body — the
  action type is derived entirely from server-side policy
  (`app.actions.engine.check_eligibility`), never from client input,
  and certainly never from an LLM's output. There is nothing for a
  request (or a prompt-injected AI response, if one were ever wired
  in) to select.
- The eligibility policy itself is the same bounded, rupee-capped rule
  table Phase 3's auto-resolution engine already proved out
  (`app.auto_resolution.engine.policy_decision`, reused verbatim) —
  Phase 8 does not introduce a second, possibly-looser safety surface.
