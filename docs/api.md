# RazorRecon AI — Backend API (Phase 4)

FastAPI + SQLAlchemy + PostgreSQL backend over the Phase 1-3 domain
logic. Route handlers only orchestrate `app.services.*`, which call
the unmodified `app.reconciliation` / `app.auto_resolution` /
`app.review` engines and persist their output.

## Running locally

1. Install dependencies:
   ```
   pip install -r backend/requirements.txt
   ```
2. Have a PostgreSQL server reachable locally (any install works — no
   Docker Compose is included since none was needed in this
   environment). Create a database:
   ```
   createdb razorrecon
   ```
3. Copy `.env.example` to `.env` at the repo root and fill in your
   real connection string:
   ```
   DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/razorrecon
   ```
4. Apply migrations:
   ```
   cd backend
   PYTHONPATH=. python -m alembic upgrade head
   ```
5. Start the API:
   ```
   cd backend
   PYTHONPATH=. uvicorn app.api.main:app --reload
   ```
   Interactive docs at `http://localhost:8000/docs`.

## Migrations

- Create a new migration after changing `app/db/models.py`:
  ```
  cd backend
  PYTHONPATH=. python -m alembic revision --autogenerate -m "message"
  ```
- Apply migrations: `PYTHONPATH=. python -m alembic upgrade head`
- Roll back one step: `PYTHONPATH=. python -m alembic downgrade -1`

`alembic/env.py` reads `DATABASE_URL` from the environment/`.env` the
same way the app does — there's no separate hard-coded connection
string to keep in sync.

## Running tests

Unit tests (Phase 1-3, no database): 
```
PYTHONPATH=backend python -m unittest discover -s backend/app/tests -p "test_*.py"
```

API/integration tests (`test_api.py`) run against a **separate**
database, `razorrecon_test`, so they never touch dev data:
```
createdb razorrecon_test
cd backend
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/razorrecon_test PYTHONPATH=. python -m alembic upgrade head
cd ..
PYTHONPATH=backend python -m unittest discover -s backend/app/tests -p "test_*.py"
```
(`test_api.py` hard-codes the `razorrecon_test` connection string and
truncates its tables before/after every test — it never reads dev
data or the dev `.env`.)

## Main endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + DB connectivity check |
| POST | `/datasets/demo` | Generate + persist a deterministic demo dataset |
| POST | `/reconciliation/runs` | Run reconciliation + auto-resolution against a dataset |
| GET | `/reconciliation/runs` | List runs |
| GET | `/reconciliation/runs/{run_id}` | Run detail/status |
| GET | `/reconciliation/runs/{run_id}/results` | Persisted results (filter: `?status=matched`) |
| GET | `/dashboard/summary` | Real, DB-computed metrics (optional `?run_id=`) |
| GET | `/exceptions` | List exceptions (filters: `status`, `severity`, `exception_type`) |
| GET | `/exceptions/{id}` | Exception detail + auto-resolution + review audit trail |
| POST | `/exceptions/{id}/start-review` | Move PENDING → IN_REVIEW |
| POST | `/exceptions/{id}/approve` | Approve a proposed resolution |
| POST | `/exceptions/{id}/reject` | Reject a proposed resolution |
| POST | `/exceptions/{id}/mark-resolved` | Human resolves outright |
| POST | `/exceptions/{id}/add-note` | Note only, no status change |

### Example: generate a dataset and run reconciliation

```
POST /datasets/demo
{"seed": 42, "num_records": 100}

-> 201
{
  "dataset_id": "demo-seed42-n100",
  "seed": 42,
  "num_records": 100,
  "payment_count": 100,
  "settlement_count": 99,
  "created": true
}
```

```
POST /reconciliation/runs
{"dataset_id": "demo-seed42-n100"}

-> 200
{
  "run_id": "ea330bbc-8206-43c1-bfc1-030275cb4840",
  "dataset_id": "demo-seed42-n100",
  "record_count": 100,
  "status": "completed",
  "started_at": "2026-08-22T00:41:54Z",
  "completed_at": "2026-08-22T00:41:54Z",
  "summary": {
    "match_status": {"matched": 81, "duplicate": 6, "partial": 8, "unmatched": 15},
    "exception_type": {"delayed_settlement": 6, "duplicate_settlement": 6, "amount_mismatch": 8,
                        "partial_settlement": 8, "missing_settlement": 11, "fee_mismatch": 6,
                        "invalid_reference": 4},
    "auto_resolved_count": 18,
    "exception_count": 49
  },
  "error": null
}
```

Re-posting the same body (no `run_id`) starts a **new**, independent
run over the same dataset. Passing an explicit `run_id` makes the
request idempotent: re-posting the same `run_id` after it completed
returns the existing summary without recomputing (see "Idempotency"
below).

### Example: dashboard summary

```
GET /dashboard/summary

-> 200
{
  "run_id": "ea330bbc-...",
  "total_transactions": 100,
  "matched": 81, "unmatched": 15, "partial": 8, "duplicate": 6,
  "exceptions": 49,
  "match_rate": 0.81,
  "amount_reconciled": "219024.75",
  "amount_at_risk": "61090.17",
  "auto_resolution_rate": 0.3673
}
```

Defaults to the most recently *completed* run; pass `?run_id=` to
scope to a specific one. Every number is computed from persisted rows
at request time — nothing is hard-coded.

### Example: review action

```
POST /exceptions/{id}/approve
{"reviewer": "anmol@razorpay.com", "note": "looks correct"}

-> 200
{
  "exception": {"...": "...", "review_status": "approved"},
  "audit": {
    "id": "...", "exception_case_id": "...", "actor": "anmol@razorpay.com",
    "action": "approve", "note": "looks correct",
    "previous_status": "auto_resolved", "new_status": "approved",
    "created_at": "2026-08-22T00:41:54Z"
  }
}
```

## Idempotency and transaction safety

- **Datasets** are named deterministically as `demo-seed{seed}-n{num_records}`.
  Re-requesting the same (seed, num_records) is a no-op (`created: false`,
  same row counts) — it never re-inserts or duplicates payments/settlements.
- **Reconciliation runs** accept an optional client-supplied `run_id`.
  Omitting it always starts a new, independent run (each run's results
  are isolated by `run_id`, so this never corrupts prior data). Passing
  the same `run_id` twice after it completed returns the existing
  summary instead of recomputing; a `run_id` currently `running`
  returns `409 Conflict` instead of racing.
- Every reconciliation run persists results, exceptions, and
  auto-resolution records in one transaction. If anything fails
  partway, that transaction is rolled back in full (no partial rows),
  the run is marked `failed` with the error message in its own small
  transaction, and the API returns `500`. See `test_api.py`'s
  `FailureHandlingTests` for a test that injects a mid-run failure and
  asserts zero partial rows.
- Reconciliation/exception/auto-resolution row IDs are derived
  deterministically from payment/settlement identifiers (by the
  Phase 2/3 engines) and then scoped to their `run_id` at persistence
  time (`f"{run_id}:{domain_id}"`), so re-running the same dataset in a
  second run never collides with the first run's rows.
