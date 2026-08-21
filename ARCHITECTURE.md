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

## Explicitly Out of Scope for the LLM
- Computing/inventing financial totals or balances
- Matching transactions
- Determining reconciliation outcomes
- Any write path that changes money-affecting state without a
  deterministic rule or human approval
