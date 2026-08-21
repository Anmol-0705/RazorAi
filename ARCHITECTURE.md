# ARCHITECTURE.md

## Overview
RazorRecon AI reconciles synthetic payment records against settlement
records, flags exceptions, auto-resolves low-risk exceptions
deterministically, routes ambiguous cases to human review, and exposes
AI-assisted explanation/classification and natural-language querying
on top of real backend data.

## Stack
- **Frontend:** React + Vite + Tailwind CSS + Recharts + Axios
- **Backend:** Python + FastAPI + SQLAlchemy + PostgreSQL + Pydantic
- **Infra:** Docker + Docker Compose
- **AI:** LLM provider behind a modular service abstraction (swappable,
  optional at runtime)

## Layers

1. **Data layer (Postgres via SQLAlchemy)**
   Stores raw payment records, settlement records, reconciliation
   results, exception records, and review decisions.

2. **Reconciliation engine (deterministic, pure Python)**
   Matches payments to settlements using rule-based logic (amount,
   reference IDs, timestamps, fees). Produces: matched / exception
   states. This layer never calls the LLM and never depends on it.
   All financial totals, matches, and classifications that affect
   money are computed here only.

3. **Exception handling / auto-resolution**
   Deterministic rules classify exceptions by risk. Low-risk exceptions
   (e.g. rounding within tolerance, known fee patterns) are
   auto-resolved by rule, not by the LLM. Ambiguous/high-risk
   exceptions are queued for human review.

4. **AI service abstraction (`ai/` module)**
   A provider-agnostic interface (e.g. `LLMProvider.explain()`,
   `.classify_hint()`, `.answer_query()`) sitting behind the backend.
   Used only for: (a) natural-language explanations of reconciliation
   results, (b) advisory classification signals that a human/rule
   still gates, (c) natural-language Q&A over already-computed backend
   data. The LLM never invents or calculates financial values. If the
   LLM provider is unavailable, all deterministic features (matching,
   auto-resolution, dashboards, exports) continue to function; only
   AI-explanation/NL-query features degrade gracefully.

5. **API layer (FastAPI)**
   REST endpoints for ingestion, reconciliation runs, exception review,
   metrics/evaluation against held-out data, and AI-assisted endpoints.

6. **Frontend (React)**
   Dashboards (Recharts) for reconciliation health, exception queues,
   review workflow UI, and a natural-language query panel.

## Data Flow (high level)
Synthetic payment + settlement data → ingestion → deterministic
reconciliation engine → exception classification (rule-based) →
[auto-resolve] or [human review queue] → results persisted →
evaluation against held-out labeled set → dashboards / AI explanation
layer reads final computed results (read-only, no write-back of
financial values from AI).

## Data Model & Generator (Phase 1, implemented)
- `backend/app/models/` — Payment, Settlement, ReconciliationResult,
  ExceptionCase, ReviewAudit. Currently stdlib `dataclasses` with
  explicit validation (not yet SQLAlchemy ORM — see DECISIONS.md D006).
  Only Payment/Settlement are populated by the generator; the other
  three are schema-only contracts for later phases.
- `backend/app/data_generation/` — deterministic generator. Config
  (seed, record count, anomaly weights) lives in `config.py`; anomaly
  labels live in their own `GroundTruthCondition` enum, intentionally
  separate from `models.enums.ExceptionType` so the reconciliation
  engine can never accidentally import the answer key.
- `data/demo/` and `data/eval/` hold generator output (payments +
  settlements only). `data/ground_truth/` is a physically separate
  tree holding the true condition per transaction, for evaluation
  scripts only — never a valid input to the reconciliation engine.

## Reconciliation Engine (Phase 2, implemented)
- `backend/app/reconciliation/engine.py` — pure function
  `reconcile(payments, settlements, config=None, now=None) ->
  ReconciliationReport`. No FastAPI imports, no LLM imports, no I/O;
  callable from a route, a script, or a test identically.
- Matching hierarchy, applied per payment against settlements sharing
  its `transaction_id` via `Settlement.transaction_reference`:
  1. **Exact reference match** — reference, amount (within tolerance),
     and timestamp (within the delayed-settlement window) all agree →
     `MatchStatus.MATCHED` / `MatchStrategy.EXACT_REFERENCE`.
  2. **Reference + amount** — reference agrees, amount does not →
     `MatchStrategy.REFERENCE_AMOUNT`, further split into
     `amount_mismatch` / `partial_settlement` / `fee_mismatch` exceptions
     by comparing the settlement's reported fee/settled amount against
     the standard fee schedule in `reconciliation/config.py`.
  3. **Reference + configurable timestamp tolerance** — reference and
     amount agree, but `settled_at` falls outside
     `ReconciliationConfig.delayed_settlement_threshold` →
     `MatchStrategy.TIMESTAMP_TOLERANCE` + `delayed_settlement` exception.
  4. **Unresolved** — no reference match on either side: a payment with
     no settlement → `missing_settlement`; a settlement whose reference
     matches no payment → `invalid_reference`. Both are
     `MatchStatus.UNMATCHED` with `match_strategy=None`.
  Extra settlements sharing a reference beyond the earliest one are
  reported separately as `MatchStatus.DUPLICATE` / `duplicate_settlement`.
- `backend/app/reconciliation/classifier.py` — a fixed table mapping
  each `ExceptionType` to `Severity` / `RecommendedAction` /
  `auto_resolvable`. Phase 2 only classifies; nothing reads
  `auto_resolvable` to actually act — that execution is Phase 3's job.
- The engine never imports `app.data_generation.ground_truth` or
  `GroundTruthCondition`; it only ever sees `Payment`/`Settlement`
  records, keeping it usable on real production data later.

## Explicitly Out of Scope for the LLM
- Computing/inventing financial totals or balances
- Matching transactions
- Determining reconciliation outcomes
- Any write path that changes money-affecting state without a
  deterministic rule or human approval
