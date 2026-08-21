# PROJECT_STATE.md

## Current Phase
Phase 1 — Data model + synthetic data generator (COMPLETE)

## Completed Work
- Domain models (stdlib dataclasses, validated): Payment, Settlement,
  ReconciliationResult, ExceptionCase, ReviewAudit — `backend/app/models/`
- Shared enums for currency/method/status/match/exception/review — 
  `backend/app/models/enums.py`
- Reusable validation helpers — `backend/app/validation.py`
- Deterministic synthetic generator with 8 controlled conditions
  (normal_match + 7 anomalies) — `backend/app/data_generation/`
- Ground truth kept in a separate module/enum/output tree from the
  production models (never written into ReconciliationResult/ExceptionCase)
- Dataset separation: demo (seed 42, n=100/250/500) vs held-out eval
  (seed 1337, n=250) — `scripts/generate_data.py` → `data/`
- 24 unittest tests across 3 files — `backend/app/tests/`

## Current Work
- None. Phase 1 closed, awaiting Phase 2 instruction.

## Known Issues
- Sandbox has no network access: cannot `pip install`, so Phase 1 is
  implemented with stdlib dataclasses + `unittest` instead of the
  planned Pydantic/SQLAlchemy (see DECISIONS.md D006). Migrating
  validation to Pydantic and adding real SQLAlchemy ORM mappings is
  deferred to the Docker/DB phase, where `pip install` will work.
- No remote GitHub push capability in this sandbox (no GitHub
  connector, no bash network egress) — this repo (`RazorAi`) is
  local-only in this session. User must sync to GitHub manually
  (download the working tree, or continue via Claude Code locally,
  which has network access) until a GitHub connector is available here.
- Reconciliation matching logic, API, frontend, AI integration: not
  started (correctly out of scope for Phase 1).

## Tests
- `PYTHONPATH=backend python3 -m unittest discover -s backend/app/tests -p "test_*.py" -v`
- Result: **24/24 passed**, 0 failures, 0 errors (run locally, this session)
- Manual verification also run: generator executed for n=100/250/500 (demo)
  and n=250 (eval); confirmed all 8 ground-truth conditions appear;
  confirmed byte-identical output across two runs with the same seed;
  confirmed demo/eval transaction IDs are disjoint (seed is embedded in
  the ID, so they can't collide by construction).

## Latest Commit
- `66f9a59` (Phase 0 memory files) — Phase 1 commit hash recorded below
  once committed this turn.

## Next Task
- Phase 2 candidate: deterministic reconciliation engine (pure Python,
  no LLM) that consumes `data/demo/*` and `data/eval/*`, producing
  ReconciliationResult + ExceptionCase records, matched against
  `data/ground_truth/*` for precision/recall — without the engine ever
  reading the ground truth directory at runtime.
