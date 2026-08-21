# PROJECT_STATE.md

## Current Phase
Phase 4 — Persistent FastAPI + PostgreSQL backend (COMPLETE)

## Completed Work
- Domain models (stdlib dataclasses, validated): Payment, Settlement,
  ReconciliationResult, ExceptionCase, ReviewAudit — `backend/app/models/`
- Shared enums for currency/method/status/match/exception/review — 
  `backend/app/models/enums.py` (Phase 2 added `MatchStrategy.REFERENCE_AMOUNT`
  and `MatchStrategy.TIMESTAMP_TOLERANCE`, additive only)
- Reusable validation helpers — `backend/app/validation.py`
- Deterministic synthetic generator with 8 controlled conditions
  (normal_match + 7 anomalies) — `backend/app/data_generation/`
- Ground truth kept in a separate module/enum/output tree from the
  production models (never written into ReconciliationResult/ExceptionCase)
- Dataset separation: demo (seed 42, n=100/250/500) vs held-out eval
  (seed 1337, n=250) — `scripts/generate_data.py` → `data/`
- **Deterministic reconciliation engine** — `backend/app/reconciliation/`
  - `config.py` — tunable thresholds (fee schedule, amount/fee
    tolerance, partial-settlement fraction, delayed-settlement window)
  - `engine.py` — pure `reconcile(payments, settlements, config, now)`
    function; 4-tier matching hierarchy (exact reference → reference +
    amount → reference + timestamp tolerance → unresolved); produces
    `ReconciliationResult` + `ExceptionCase` lists, never touches
    ground truth, never calls FastAPI or the LLM
  - `classifier.py` — deterministic severity/recommended-action/
    auto_resolvable table per `ExceptionType`, laid out so Phase 3 can
    add bounded auto-resolution without touching matching logic
- **Phase 2.5 correctness fix** — `backend/app/reconciliation/config.py`
  adds `partial_settlement_min_absolute_diff` (default 1.00): a
  shortfall must clear this absolute floor, not just the 90%-fraction
  threshold, to count as `partial_settlement`. Fixes real instability
  at small transaction amounts; the one remaining n=500 boundary case
  is a proven, documented, irreducible ambiguity (DECISIONS.md D009).
  Missing-settlement `reason` text now flags when orphan
  (invalid-reference) settlements exist in the same batch.
- **Bounded auto-resolution** — `backend/app/auto_resolution/`
  - `config.py` — rupee caps gating which exceptions are safe to
    auto-resolve (`AutoResolutionConfig`)
  - `engine.py` — pure `auto_resolve(exceptions, config, now) ->
    AutoResolutionReport`; only auto-resolves `fee_mismatch` (below
    cap), `delayed_settlement` (no financial impact), and
    `duplicate_settlement` (exact-amount match only); idempotent on
    re-runs over already-resolved exceptions
  - `backend/app/models/auto_resolution.py` — `AutoResolutionRecord`
    audit schema (exception id, resolution type, reason, actor,
    timestamp, financial impact, previous/new status)
- **Human review workflow** — `backend/app/review/workflow.py`:
  `approve`/`reject`/`mark_resolved`/`add_note`/`start_review`, each
  producing an updated `ExceptionCase` + a `ReviewAudit` entry
  (`backend/app/models/audit.py`, populated for the first time).
  Domain/backend logic only — no FastAPI routes, no React UI.
- 62 unittest tests across 6 files — `backend/app/tests/` (24 Phase 1
  + 19 reconciliation + 12 auto-resolution + 7 review-workflow)
- **Persistent FastAPI + PostgreSQL backend** (Phase 4)
  - `backend/app/db/models.py` — SQLAlchemy ORM models (`PaymentORM`,
    `SettlementORM`, `ReconciliationRunORM`, `ReconciliationResultORM`,
    `ExceptionCaseORM`, `AutoResolutionRecordORM`, `ReviewAuditORM`) as
    a persistence mirror of the Phase 1-3 dataclasses — the engines
    stay pure-Python/DB-agnostic; only this layer knows about SQL.
  - `backend/alembic/` — one Alembic migration (`9bc6b67a00ed_initial_schema`)
    generated from the ORM models; `env.py` reads `DATABASE_URL` from
    the environment, no hard-coded connection string.
  - `backend/app/services/` — orchestration layer: `dataset_service`
    (generate+persist demo data, idempotent by deterministic
    `dataset_id`), `reconciliation_service` (loads persisted data,
    calls the unmodified `reconcile()`/`auto_resolve()`, persists
    results/exceptions/auto-resolution records in one transaction,
    rolls back and marks the run `failed` on error), `review_service`
    (calls the unmodified `app.review.workflow` functions, persists
    `ReviewAuditORM`), `dashboard_service`, `exception_service`.
  - `backend/app/api/` — FastAPI app; routers only call services, no
    business logic in route handlers. Endpoints: `GET /health`,
    `POST /datasets/demo`, `POST /reconciliation/runs`,
    `GET /reconciliation/runs[/…]`, `GET /dashboard/summary`,
    `GET /exceptions[/…]`, `POST /exceptions/{id}/{start-review,
    approve,reject,mark-resolved,add-note}`.
  - Idempotency: dataset generation is a no-op on repeat
    (seed+num_records name the dataset); reconciliation runs accept an
    optional client `run_id` — repeating a completed run_id replays
    the stored summary instead of recomputing, a `running` run_id
    returns 409. Row IDs are scoped as `f"{run_id}:{domain_id}"` so two
    runs over the same dataset never collide on primary keys (the
    Phase 2/3 engines assign IDs deterministically from payment/
    settlement identifiers, not run-scoped).
  - Transaction safety: results/exceptions/auto-resolution records for
    one run are persisted in a single transaction; on failure it rolls
    back completely (verified by `test_api.py`'s
    `FailureHandlingTests`, which injects a mid-run exception and
    asserts zero partial rows), then the run row is marked `failed`
    with the error message in its own follow-up transaction.
  - 82 unittest tests total (62 unit + 20 in `test_api.py`, run against
    a dedicated `razorrecon_test` PostgreSQL database, never dev data).

## Current Work
- None. Phase 4 closed, awaiting Phase 5 instruction.

## Known Issues
- D006's original constraint (no `pip install` in the Phase 1 sandbox)
  no longer applies now that this repo runs locally with network
  access — Phase 4 installed fastapi/sqlalchemy/alembic/psycopg
  normally (`backend/requirements.txt`). The Phase 1-3 domain
  dataclasses were deliberately *not* rewritten as Pydantic models or
  SQLAlchemy ORM classes even though that's now possible: they're
  proven, tested, DB-agnostic pure Python, and Phase 4 added a
  separate ORM layer (`backend/app/db/models.py`) plus thin
  converters in `app/services/*` instead, per this phase's "do not
  rebuild Phase 1-3 functionality" instruction.
- Engine's `missing_settlement` count is intentionally higher than the
  seeded `invalid_reference` ground-truth count would suggest: a
  payment whose settlement was misdirected (invalid reference on the
  settlement side) is *also* correctly flagged missing on the payment
  side, since the engine has no way to know the two are related
  without reading ground truth. Verified: engine `missing_settlement`
  count == seeded `missing_settlement` + seeded `invalid_reference` at
  n=100/250/500 (see DECISIONS.md D008).
- One n=500 boundary case (1 of 40 `amount_mismatch`) still classifies
  as `partial_settlement`. Phase 2.5 fixed the general small-amount
  instability (see `partial_settlement_min_absolute_diff`), but proved
  this specific record is not separable from a legitimately-labeled
  `partial_settlement` record in the same dataset using any monotonic
  rule over the observable fields — `Settlement.fee`/`.tax` are
  identical in both the generator's `amount_mismatch` and
  `partial_settlement` code paths, so there's no recoverable
  distinguishing signal. Accepted and documented in DECISIONS.md D009.
- React review UI, AI integration, authentication: not started
  (correctly out of scope for Phase 4).
- No Docker/docker-compose for PostgreSQL — this environment has a
  local PostgreSQL 18 Windows service already running, so none was
  added (`# 15` said add Docker only if necessary). A docker-compose
  for Postgres is a reasonable Phase 5 addition for portability.
- `dashboard_service.compute_summary()` defaults to the most recently
  *completed* run when no `run_id` is given; it does not aggregate
  across all historical runs (re-reconciling the same dataset would
  otherwise double-count transactions across runs).
- Alembic's autogenerate was only exercised once (the initial
  schema) — not yet tested through a real schema-change migration.

## Tests
- Unit (no DB): `PYTHONPATH=backend python3 -m unittest discover -s backend/app/tests -p "test_*.py" -v`
- API/integration (`test_api.py`, needs `razorrecon_test` DB migrated —
  see docs/api.md): included in the same discover command
- Result: **82/82 passed**, 0 failures, 0 errors (run locally, this
  session, against real PostgreSQL 18)
- Manual end-to-end verification against the dev `razorrecon` database
  (see docs/api.md for the flow): health check, demo dataset
  generation, reconciliation run, persisted results, dashboard
  summary, exception detail, and a review approval, all confirmed via
  direct HTTP calls through FastAPI's `TestClient`.
- Ground-truth verification from Phase 2.5 (D008/D009) is unchanged —
  no reconciliation logic was modified in this phase.

## Latest Commit
- `c8a6fe1` — feat: add bounded auto resolution and review audit
  (pre-Phase-4 HEAD)

## Next Task
- Phase 5 candidate: React review UI consuming this API (exception
  queue, review actions, dashboard charts), or AI-assisted
  explanation/NL-query endpoints behind the `ai/` provider abstraction
  described in ARCHITECTURE.md — whichever the user prioritizes next.
