# PROJECT_STATE.md

## Current Phase
Phase 2 — Deterministic reconciliation engine (COMPLETE)

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
- 37 unittest tests across 4 files — `backend/app/tests/` (24 Phase 1
  + 13 new reconciliation tests)

## Current Work
- None. Phase 2 closed, awaiting Phase 3 instruction.

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
- At the smallest payment amounts, the fixed-fraction partial-vs-amount-
  mismatch threshold (settled < 90% of expected net ⇒ partial) can
  disagree with the generator's ground truth in rare edge cases
  (observed: 1 of 40 `amount_mismatch` cases reclassified as `partial`
  at n=500). Documented in DECISIONS.md D008; not fixed by reading
  ground truth, since the engine must remain ground-truth-blind.
- Reconciliation API, frontend, AI integration, auto-resolution
  execution: not started (correctly out of scope for Phase 2).

## Tests
- `PYTHONPATH=backend python3 -m unittest discover -s backend/app/tests -p "test_*.py" -v`
- Result: **37/37 passed**, 0 failures, 0 errors (run locally, this session)
- Verified against seeded demo datasets (`data/demo/n100`, `n250`,
  `n500`): engine's `duplicate_settlement`, `amount_mismatch` (n100/
  n250 exact; n500 off by 1, see Known Issues), `partial_settlement`,
  `fee_mismatch`, `delayed_settlement`, and `invalid_reference` exception
  counts match the seeded ground-truth counts exactly at n=100/250 and
  match within 1 at n=500.

## Latest Commit
- `98979a3` — docs: record Phase 1 commit hash (pre-Phase-2 HEAD)

## Next Task
- Phase 3 candidate: bounded auto-resolution built on top of
  `backend/app/reconciliation/classifier.py`'s `auto_resolvable` flag
  (currently data-only, not executed) — deterministic execution of
  low-risk auto-resolutions (fee_mismatch, delayed_settlement),
  ReviewAudit persistence, and routing everything else to human review.
