# PROJECT_STATE.md

## Current Phase
Phase 7 — Held-out ground-truth evaluation (COMPLETE)

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
  - 84 unittest tests total (62 unit + 22 in `test_api.py`, run against
    a dedicated `razorrecon_test` PostgreSQL database, never dev data).
  - Phase 5 additive backend enrichments (discovered while wiring the
    UI — no matching/persistence logic touched): `ReconciliationResultResponse`
    now also carries denormalized payment/settlement fields (order_id,
    payment_amount, currency, payment_method, payment_status,
    settlement_status, settled_amount, fee, tax) and the linked
    exception's type/status, joined in
    `reconciliation_service._enrich_results`; `ExceptionDetailResponse`
    gained a `result` field (the same enriched result) so the exception
    detail view has payment/settlement context without a second
    endpoint; `GET /exceptions` gained an optional `run_id` filter (the
    column already existed) so exception views can be scoped to one
    run. `CORSMiddleware` added to the FastAPI app, restricted to the
    Vite dev origins (`http://localhost:5173` / `127.0.0.1:5173`) —
    there is still no authentication (intentional, per project scope).
- **React finance operations frontend** (Phase 5) — `frontend/`
  (Vite + React + Tailwind v4 + Recharts + Axios + React Router)
  - `src/api/client.js` — single Axios instance + one function per
    endpoint; all requests go through it, no raw Axios calls in
    components; base URL from `VITE_API_BASE_URL` (`.env`/`.env.example`).
  - `src/context/RunContext.jsx` — the only shared state: current
    `datasetId`/`runId` (persisted to localStorage) plus a
    `refreshKey`/`bumpRefresh()` used to re-trigger data fetches after a
    write. Bootstraps from `GET /dashboard/summary` on first load so a
    page refresh doesn't lose context. No Redux/other store — plain
    `useState`/`useContext` plus a tiny `useAsync` hook was enough.
  - Pages: Dashboard (run control + real summary metrics + 3 charts
    derived from `/dashboard/summary` and `/exceptions`), Transactions
    (enriched `/reconciliation/runs/{id}/results`, status filter),
    Exceptions (list + type/severity/status filters), Exception Detail
    (financial discrepancy panel, payment/settlement/reconciliation
    detail, the full review workflow, audit history), Review Queue
    (pending/in-review exceptions sorted by severity then financial
    impact), Evaluation (explicit placeholder — no ground-truth
    scoring endpoint exists yet, so it says so instead of showing
    invented numbers).
  - UX: loading/empty/error states with retry on every data view,
    disabled buttons + a confirm dialog on approve/reject/mark-resolved
    (start-review and add-note are non-destructive, no confirm),
    reviewer note field, success/error feedback banners.
  - Dashboard explicitly labels which run its numbers describe and
    states the backend doesn't aggregate across runs; a note next to
    the charts states the settlement-trend chart is omitted because no
    multi-run time series endpoint exists yet, and that a documented
    exception-classification boundary case exists (D009) — no accuracy
    claim is made anywhere in the UI.
  - Verified with a headless Chrome (Playwright, driving the system
    Chrome install — `frontend/scripts/verify*.mjs`, local dev aids,
    not part of the test suite): generate dataset → run reconciliation
    → dashboard/transactions/exceptions/review-queue all show real
    persisted data → start-review → approve → change persists across a
    reload → audit history shows both actions. Zero browser console/
    page errors across all six views. `npm run build` passes.
- **AI-assisted layer** (Phase 6A) — `backend/app/ai/`, safety-boundary
  details in `docs/ai-architecture.md`. The rule: the LLM only phrases
  facts the backend already computed — it never calculates a total,
  balance, match status, or exposure number, never invents transaction
  data, never mutates a financial record, and never executes a review
  action or picks which backend function runs.
  - `provider.py` — abstract `AIProvider`/`AIResult`; `anthropic_provider.py`
    — the only concrete provider and the only file importing the
    `anthropic` SDK. Reads `ANTHROPIC_API_KEY`/`AI_MODEL` from the
    environment (default model `claude-opus-5`); every method catches
    every SDK exception (auth, rate limit, timeout, connection, status,
    unexpected) and returns `AIResult(available=False, error=...)` —
    an AI failure is always a return value, never a raised exception.
  - `facts.py` — the fixed allowlist of deterministic data-retrieval
    functions (thin wrappers over the existing `app.services.*` layer)
    the AI is ever allowed to see; `query_router.py` — plain Python
    regex matching (no LLM tool-use, no agent framework) that maps a
    controller question to one of those functions; an unmatched,
    off-topic question gets a canned "unsupported" response without
    ever calling the provider.
  - `service.py` — orchestrates facts → provider → response, and runs
    a hallucination guardrail (`_check_for_fabricated_numbers`): any
    3+ digit number in the AI's free-text output that doesn't appear
    in the facts payload it was given causes the whole response to be
    discarded in favor of a structured error, rather than shown as a
    trustworthy number.
  - Endpoints: `POST /ai/exceptions/{id}/explain`,
    `POST /ai/exceptions/{id}/recommend`, `POST /ai/query`,
    `POST /ai/runs/{run_id}/summary` — routes only call `app.ai.service`,
    no business logic in the router.
  - Frontend: `AIResultCard` component renders every response with
    **SYSTEM FACTS** (raw facts JSON) visually separated from **AI
    EXPLANATION**/**AI ANSWER** (labeled "AI-generated interpretation").
    New `AIControllerPage` (prompt box + the task's example questions
    as one-click buttons + running history); Exception Detail page
    gained an "Explain with AI" button using the same component.
  - 19 new tests (`backend/app/tests/test_ai.py`, all mocked — no live
    LLM call anywhere in the suite): provider-unavailable/missing-key,
    exception explanation using backend-derived facts, a numerical
    controller query asserted to echo the backend's own computed
    value, an unsupported question proven to never call the provider
    (`NeverCalledProvider`), recommend-resolution, reconciliation
    summary, direct unit tests on the `facts.py` allowlist, and two
    hallucination-guardrail tests (a fabricated number is discarded; a
    real one is not falsely flagged).
  - Manually verified end-to-end with headless Chrome: AI Controller
    page asks a question and renders facts+answer via a temporary
    mocked-provider backend instance (not committed, local-only); the
    same flow re-verified against the real, keyless backend to confirm
    the "AI unavailable" banner renders correctly instead. No live
    ANTHROPIC_API_KEY exists in this environment — no live provider
    call was made or claimed anywhere in this phase.

- **Held-out ground-truth evaluation** (Phase 7) —
  `backend/app/evaluation/`, methodology in `docs/evaluation.md`.
  - `loader.py` — reads `data/eval/n250` + `data/ground_truth/eval/n250`
    from disk (never regenerates), so scoring is always against the
    exact fixed 250-record held-out set (seed 1337, disjoint from the
    seed-42 demo data).
  - `service.py` — persists the eval dataset idempotently, then calls
    `reconciliation_service.run_reconciliation` **unmodified** against
    a fixed `run_id` (`eval-recon-n250`) — the same production
    pipeline, not a second matching algorithm (DECISIONS.md D019).
    Repeated `POST /evaluation/run` calls replay the same underlying
    reconciliation run and produce byte-identical metrics.
  - `scoring.py` — pure functions: reconciliation match
    rate/precision/recall/F1, exception detection
    precision/recall/F1 + per-class type accuracy, auto-resolution
    eligible/resolved/correct/unsafe + precision/recall, and financial
    totals (processed/reconciled/at-risk/unresolved). The D009
    amount_mismatch/partial_settlement boundary is scored as one
    equivalence class (exact boundary-case count and agreement rate
    always reported, never hidden) — DECISIONS.md D020.
  - Endpoints: `POST /evaluation/run`, `GET /evaluation/latest`,
    `GET /evaluation/{id}`; new `EvaluationRunORM` table + Alembic
    migration `25181f4e201c`.
  - Frontend: the Evaluation placeholder is now a real page — Summary,
    Exception Detection (with a prominent D009 callout), Auto
    Resolution, Financial Impact, and a methodology/limitations
    section — always labeled **"Held-out synthetic evaluation,"** never
    presented as production/customer performance.
  - 19 new tests (`test_evaluation.py`): a hand-computed 4-record
    dataset independently verifying every formula (match rate,
    precision/recall/F1, the D009 equivalence-class handling,
    unsafe-auto-resolution detection, financial totals, determinism),
    loader tests against the real 250-record set, and API tests
    (real run, repeated-run identical metrics, latest/get-by-id/404s).
  - Verified against the real held-out dataset: 250 records, match
    rate 80.8%, match precision/recall/F1 all 1.0 (the reconciliation
    engine's own matching decisions agree perfectly with ground truth
    on this set), exception detection precision/recall/F1 all 1.0,
    45 auto-resolution-eligible exceptions with 44 correctly
    auto-resolved and 0 unsafe, 40 D009 boundary cases with 100%
    agreement rate in this run. Re-run twice via the API and confirmed
    byte-identical `metrics`. Manually verified via headless Chrome:
    Evaluation page runs an evaluation and renders all four sections
    plus the D009 callout with zero console errors.

## Current Work
- None. Phase 7 closed, awaiting the next phase.

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
- AI integration, authentication: not started (correctly out of scope
  for Phase 5).
- No Docker/docker-compose for PostgreSQL — this environment has a
  local PostgreSQL 18 Windows service already running, so none was
  added. Still pending, deferred to a later phase per this phase's
  instructions.
- `dashboard_service.compute_summary()` defaults to the most recently
  *completed* run when no `run_id` is given; it does not aggregate
  across all historical runs (re-reconciling the same dataset would
  otherwise double-count transactions across runs). The frontend
  mirrors this: Dashboard/Transactions/Exceptions/Review Queue are all
  scoped to one run at a time, never an aggregate.
- Alembic's autogenerate was only exercised once (the initial
  schema) — not yet tested through a real schema-change migration
  (Phase 5's response-shape changes didn't touch the DB schema, only
  Pydantic response models, so no new migration was needed).
- Evaluation page is an intentional placeholder: no backend endpoint
  scores reconciliation output against `data/ground_truth/eval` yet.
- The Recharts/Recharts+Vite production bundle is ~700KB (single
  chunk, no code-splitting) — fine for a demo, worth revisiting with
  route-based `lazy()` splitting if the app grows.
- `frontend/scripts/verify*.mjs` are local, environment-specific
  verification aids (hardcode a Chrome path found on this machine via
  `playwright-core`) — not part of `npm test`/CI, and not meant to be
  portable as-is.
- No live `ANTHROPIC_API_KEY` exists in this environment. Every AI
  code path is exercised via a mocked `AIProvider` (unit tests) or a
  temporary local mock-provider process (manual UI verification, not
  committed) — the real Anthropic API has never actually been called
  from this project. The provider/prompt/JSON-parsing code is written
  against the documented API shape but is unverified against a live
  response.
- `query_router.py`'s regex categories are necessarily approximate —
  a question using unexpected phrasing may route to `dashboard_overview`
  (a generic but real, non-fabricated fact set) rather than the most
  specific category, or occasionally to "unsupported" when it
  shouldn't. This is a deliberate simplicity/safety tradeoff (see
  DECISIONS.md D017), not a bug, but it means the controller's
  question coverage is narrower than a true NLU system's.
- The hallucination guardrail (`_check_for_fabricated_numbers`) is a
  heuristic (3+ digit numbers only, exact-substring match against the
  facts JSON) — it can't catch a fabricated 1-2 digit figure, and a
  correct number formatted differently than in the facts (e.g. `1,234`
  vs `1234.00`) could in principle be falsely flagged, though the
  provider is explicitly instructed to copy values verbatim.
- The evaluation's per-payment aggregation counts a payment as
  "clean-matched" using only `match_status`/attached-exception
  presence, not settlement amount tolerance directly — this mirrors
  the reconciliation engine's own definitions exactly (by design,
  since the evaluator scores the engine's real decisions), but means
  the metrics can't diverge from whatever `dashboard_service`/
  `reconciliation_service` already consider "matched".
- `EvaluationRunORM.reconciliation_run_id` is a fixed value per
  dataset name (`eval-recon-{name}`), not per evaluation call — this
  is intentional (D019) but means the eval history table accumulates
  one row per `POST /evaluation/run` call while all of them reference
  the same underlying reconciliation run after the first.

## Tests
- Unit (no DB): `PYTHONPATH=backend python3 -m unittest discover -s backend/app/tests -p "test_*.py" -v`
- API/integration (`test_api.py`, `test_ai.py`, `test_evaluation.py`;
  needs `razorrecon_test` DB migrated — see docs/api.md): included in
  the same discover command
- Result: **122/122 passed**, 0 failures, 0 errors (run locally, this
  session, against real PostgreSQL 18; 103 from Phase 4/5/6A + 19 new
  `test_evaluation.py` tests)
- Frontend: `cd frontend && npm run build` passes cleanly
- Frontend manual/E2E verification (headless Chrome via Playwright,
  real backend + real held-out dataset, no mocking needed since
  evaluation has no AI dependency): Evaluation page runs an evaluation
  and renders Evaluation Summary, Exception Detection (with the D009
  callout), Auto Resolution, and Financial Impact sections with real
  numbers, plus the methodology section. Zero browser console/page
  errors.
- Manual verification against a small, hand-computed 4-record dataset
  (`ScoringUnitTests`) independently confirms the match/exception/
  auto-resolution/financial formulas, separately from the real
  250-record run.
- Re-ran `POST /evaluation/run` twice via both the test suite and a
  live curl/API call — `metrics` byte-identical both times.
- Ground-truth verification from Phase 2.5 (D008/D009) is unchanged —
  no reconciliation logic was modified in this phase.

## Latest Commit
- `52ef09f` — feat: add AI finance controller (pre-Phase-7 HEAD)

## Next Task
- Docker/docker-compose for the full stack (Postgres + backend +
  frontend) remains the main pending item, deferred from Phase 5 and
  explicitly out of scope for Phase 7 too.
