# PROJECT_STATE.md

## Current Phase
Phase 3 — Bounded auto-resolution + human review (COMPLETE)

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

## Current Work
- None. Phase 3 closed, awaiting Phase 4 instruction.

## Known Issues
- Sandbox has no network access: cannot `pip install`, so Phase 1/2 are
  implemented with stdlib dataclasses + `unittest` instead of the
  planned Pydantic/SQLAlchemy (see DECISIONS.md D006). Migrating
  validation to Pydantic and adding real SQLAlchemy ORM mappings is
  deferred to the Docker/DB phase, where `pip install` will work.
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
- FastAPI routes, React review UI, AI integration: not started
  (correctly out of scope for Phase 3).
- No persistence layer yet (no DB/ORM) — reconciliation results,
  exceptions, auto-resolution records, and review audits are all
  produced in-memory by pure functions; nothing is written to disk or
  a database in this phase.

## Tests
- `PYTHONPATH=backend python3 -m unittest discover -s backend/app/tests -p "test_*.py" -v`
- Result: **62/62 passed**, 0 failures, 0 errors (run locally, this session)
- Re-verified against seeded demo datasets (`data/demo/n100`, `n250`,
  `n500`) after the Phase 2.5 fix: `duplicate_settlement`,
  `fee_mismatch`, `delayed_settlement`, and `invalid_reference`
  exception counts match ground truth exactly at n=100/250/500;
  `amount_mismatch`/`partial_settlement` exact at n=100/250, off by the
  same single documented case at n=500 (see Known Issues, D009).

## Latest Commit
- `61ca40f` — fix: improve reconciliation exception classification
  (pre-Phase-3 HEAD)

## Next Task
- Phase 4 candidate: FastAPI routes exposing the reconciliation run,
  exception list, auto-resolution report, and review actions
  (approve/reject/mark_resolved/add_note) as HTTP endpoints, plus a
  real persistence layer (SQLAlchemy/PostgreSQL per DECISIONS.md D004)
  so results, exceptions, and audit trails survive past a single
  process. React review UI and AI-assisted endpoints stay out of scope
  until their own phases.
