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

## Bounded Auto-Resolution and Human Review (Phase 3, implemented)
- `backend/app/auto_resolution/` — `auto_resolve(exceptions, config, now)
  -> AutoResolutionReport`. Pure, deterministic, separate from the
  reconciliation engine: reconciliation decides *what happened*, this
  module decides whether an already-classified `ExceptionCase` is safe
  to close without a human. Only three exception types are ever
  auto-resolved, each behind its own bounded check in
  `AutoResolutionConfig`: `fee_mismatch` below a rupee cap,
  `delayed_settlement` (never has a real financial impact),
  `duplicate_settlement` only when its amount exactly matches the
  primary settlement. Everything else — `missing_settlement`,
  `amount_mismatch`, `partial_settlement`, `invalid_reference` — is
  never auto-resolved. Every auto-resolution produces an immutable
  `AutoResolutionRecord` (`backend/app/models/auto_resolution.py`):
  exception id, resolution type, reason, actor, timestamp, financial
  impact, previous/new review status. Re-running the engine over
  already-resolved exceptions is a no-op (checked via
  `review_status != PENDING`), making it safe to call repeatedly.
- `backend/app/review/workflow.py` — human review actions (`approve`,
  `reject`, `mark_resolved`, `add_note`, `start_review`), each
  returning an updated `ExceptionCase` plus a `ReviewAudit` entry
  (`backend/app/models/audit.py`, populated for the first time in this
  phase). Backend/domain logic only — no FastAPI routes, no React UI.
- `backend/app/reconciliation/classifier.py`'s `auto_resolvable`/
  `recommended_action` table is a first-pass candidate signal set at
  ExceptionCase creation time; the auto-resolution engine applies its
  own stricter, independent checks before actually acting (e.g. a
  duplicate settlement is only a candidate in the classifier, but only
  auto-resolved when its amount is an exact match).

## Persistence and API (Phase 4, implemented)
- `backend/app/db/models.py` — SQLAlchemy ORM models: `PaymentORM`,
  `SettlementORM`, `ReconciliationRunORM`, `ReconciliationResultORM`,
  `ExceptionCaseORM`, `AutoResolutionRecordORM`, `ReviewAuditORM`. Kept
  as a separate persistence layer rather than converting the Phase 1-3
  frozen dataclasses into ORM classes: the reconciliation/
  auto-resolution/review engines stay pure Python and DB-agnostic
  (still testable with zero DB dependency, per the 62 Phase 1-3 unit
  tests that still run without a database). `backend/app/services/*`
  converts dataclass <-> ORM row at the boundary.
- `backend/alembic/` — schema migrations; `env.py` builds
  `target_metadata` from `Base.metadata` and reads the connection
  string from `DATABASE_URL` (see docs/api.md), so there's no
  hand-maintained CREATE TABLE path.
- `backend/app/services/` is the orchestration layer requested by this
  phase: `dataset_service`, `reconciliation_service`,
  `review_service`, `dashboard_service`, `exception_service`. Each
  service function loads/persists rows and calls straight into the
  Phase 2/3 engines (`app.reconciliation.engine.reconcile`,
  `app.auto_resolution.engine.auto_resolve`,
  `app.review.workflow.*`) — none of that logic is duplicated or
  reimplemented here.
- `backend/app/api/` — FastAPI routers. A router function's body is
  only ever: parse request -> call one service function -> map
  service errors (`NotFoundError`/`ConflictError`) to HTTP status
  codes -> return a Pydantic response model. No matching, resolution,
  or review logic lives in a route handler.
- Layering: `api/routers` -> `services` -> `reconciliation` /
  `auto_resolution` / `review` (domain) -> `db` (persistence). Each
  layer only calls the one below it.
- Row IDs for reconciliation results/exceptions/auto-resolution
  records are the Phase 2/3 engines' deterministic IDs (derived from
  payment/settlement identifiers), scoped per-run as
  `f"{run_id}:{domain_id}"` at persistence time — this is the only
  place Phase 4 had to adapt Phase 2/3 output, because those IDs were
  designed for in-memory reproducibility within one run, not
  uniqueness across many persisted runs of the same dataset.

## Explicitly Out of Scope for the LLM
- Computing/inventing financial totals or balances
- Matching transactions
- Determining reconciliation outcomes
- Any write path that changes money-affecting state without a
  deterministic rule or human approval
