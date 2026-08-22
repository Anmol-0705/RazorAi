# RazorRecon AI

**AI Finance Controller**

**Verify → Decide → Act → Audit**

Razorpay AI Builder Buildathon — Track 04: AI Finance Controller

---

## Overview

Finance-ops teams reconcile payments against settlements by hand: cross-checking
amounts, chasing missing settlements, spotting fee mismatches, and deciding which
discrepancies are safe to close versus which need a human. It's repetitive,
error-prone, and the "safe to auto-close" judgment call is exactly where naive
automation gets dangerous — you don't want a probabilistic model deciding that
money moved correctly.

RazorRecon AI is a finance operations console that automates the deterministic
parts of this loop and uses AI only where it can't cause financial harm. Every
number that affects money — a match, a total, a classification — is computed by
plain, testable Python. The AI layer sits on top, phrasing explanations and
answering questions about facts the backend already computed. It never
calculates a total, decides a match, or executes an action.

## Track 04 Alignment

| Requirement | Implementation |
|---|---|
| Finance-ops loop (detect → decide → act → audit) | Reconciliation engine detects exceptions → bounded policy decides eligibility → Controller Action executes a synthetic instruction → the result is written to a shared audit trail |
| 50+ synthetic records | Deterministic generator produces demo datasets of 100/250/500 records and a disjoint 250-record held-out evaluation set |
| Match rate | Reported per run on the Dashboard and in the Evaluation page (baseline held-out match rate: 80.8%) |
| Unresolved exceptions | Every exception the deterministic engine can't safely auto-resolve is routed to the Review Queue and stays visible until a human acts |
| Verification | A held-out, disjoint 250-record ground-truth set the engine was never tuned against, scored automatically after every run |
| Bounded automation | Auto-resolution and Controller Actions are restricted to three exception types, capped by rupee thresholds, and never touch a case a human has rejected |

No functionality beyond what's implemented below is claimed.

## Core Workflow

1. **Generate/ingest** synthetic payment and settlement data (deterministic, seeded generator; demo and held-out sets are disjoint)
2. **Reconcile** — a pure, deterministic engine matches payments to settlements through a 4-tier hierarchy
3. **Detect exceptions** — unmatched/mismatched cases are classified by type and severity
4. **Apply safety policy** — a bounded, rupee-capped rule decides whether an exception is safe to act on automatically
5. **Execute a bounded action** when eligible (a synthetic, allowlisted finance-ops instruction) — **or** route to human review when not
6. **Persist an audit trail** — every automated and human action is recorded, queryable per exception
7. **Evaluate** against held-out ground truth (baseline) and a seeded dirty-data variant (stress)

## Architecture

```
React/Vite  →  FastAPI  →  Services  →  Domain engines  →  PostgreSQL
 (frontend)     (routers)   (orchestration)  (reconciliation,          (persistence)
                                              auto-resolution,
                                              actions, evaluation)
```

A separate, parallel path for the AI layer:

```
Verified backend facts  →  deterministic/allowlisted retrieval  →  AI provider  →  explanation/query response
   (app.services.*)          (app.ai.facts + query_router,             (Anthropic,
                               regex-routed, no LLM tool-use)            optional)
```

**Safety boundary — the AI cannot:**
- calculate financial totals
- determine match status
- execute Controller Actions
- directly mutate financial state

`app.actions` (the Controller Action engine) never imports `app.ai`, and `app.ai`
never imports `app.actions` — there is no code path connecting them. The AI can
explain why an exception looks the way it does; it has no way to reach the code
that acts on it.

## Major Features

- Deterministic reconciliation (4-tier matching hierarchy, pure Python)
- Exception detection and classification (severity, recommended action)
- Bounded auto-resolution (3 exception types, rupee-capped, idempotent)
- Human review workflow (start-review / approve / reject / mark-resolved / add-note)
- Controller Actions — bounded, synthetic finance-ops instructions for eligible exceptions
- Action idempotency (deterministic `uuid5` idempotency key; a retried execution is a no-op)
- Unified audit history (human review + auto-resolution + controller actions, one trail)
- PostgreSQL persistence via SQLAlchemy + Alembic
- Held-out evaluation against a disjoint, ground-truth-labeled 250-record set
- Stress / dirty-data evaluation (seeded settlement-side noise, same engines)
- AI provider abstraction (swappable; Anthropic is the only implemented provider)
- AI graceful degradation (every core flow works with zero AI dependency)

## Evaluation

### Baseline Held-Out Synthetic Evaluation

250 records (seed 1337, disjoint from demo data, never used to tune the engine):

| Metric | Value |
|---|---|
| Match rate | 80.8% |
| Reconciliation F1 | 1.00 |
| Exception Detection F1 | 1.00 |
| Auto-Resolution Classification Agreement | 1.00 |

### Stress / Dirty Data Evaluation

Same 250 records with seeded, settlement-side-only noise injected (seed 9001):

| Metric | Value |
|---|---|
| Match rate | 71.2% |
| Reconciliation F1 | 0.83 |
| Exception Detection F1 | 0.84 |
| Auto-Resolution Classification Agreement | 0.85 |

**On terminology:** the 0.85 figure above is the **Auto-Resolution Classification
Agreement** — how often the deterministic classifier's decision (`fee_mismatch` /
`delayed_settlement` / `duplicate_settlement`, each capped) agrees with hidden
ground truth under noisy input. It is **not** a financial-action success rate.
The stress benchmark never calls `POST /exceptions/{id}/execute-action` and never
executes a Controller Action — it exercises only the reconciliation and
auto-resolution engines, in memory, against a noised copy of the dataset. See
`docs/evaluation.md` for the full three-layer distinction (classification →
eligibility → execution) and why only the first layer is scored here.

**D009**: a documented, investigated boundary case where `amount_mismatch` and
`partial_settlement` are observationally indistinguishable for a subset of
small-amount transactions — both code paths in the synthetic generator produce
settlements with identical fee/tax fields, so no available field can separate
them with certainty. The evaluator scores this pair as one equivalence class
rather than hiding or force-fitting it. See `DECISIONS.md` D009/D020.

Neither benchmark is a production or customer-performance claim — both are
synthetic, reproducible, and always labeled as such in the UI.

## Safety & Reliability

- **Deterministic financial logic** — all matching, totals, and classification that affect money are plain, tested Python; the reconciliation and auto-resolution engines have no AI import
- **Allowlisted actions** — the Controller Action engine maps exactly three safe resolution types to exactly three allowlisted action types; everything else stays human-review-only
- **Bounded action eligibility** — the same rupee-capped policy Phase 3's auto-resolution engine already proved out is reused directly, not duplicated
- **Idempotent action execution** — a deterministic `uuid5(exception_id, action_type)` key catches a retried execute-action call by primary-key lookup before any insert
- **Human rejection is final** — an exception a human has rejected is never eligible for a Controller Action, regardless of type or financial impact
- **Unified audit trail** — human review, auto-resolution, and controller actions all write into the same audit history per exception
- **AI non-blocking** — every `/ai/*` endpoint returns HTTP 200 with a structured `ai_available` flag whether or not the provider succeeded; an AI failure is a return value, never a raised exception
- **Provider failure fallback** — missing key, timeout, rate limit, or bad response all degrade to a structured "AI unavailable" response; no core flow depends on AI
- **Dataset-generation idempotency** — regenerating the same (seed, num_records) dataset is a no-op, and identifiers are namespaced by record count so demo sizes never collide
- **Production request timeout handling** — the deployed reconciliation route has been hardened against slow/edge-case requests (see `PROJECT_STATE.md`)

## AI Architecture

Full detail: [`docs/ai-architecture.md`](docs/ai-architecture.md). Summary:

- **Provider abstraction** — `AIProvider`/`AIResult`; `AnthropicAIProvider` is the
  only concrete implementation and the only file importing the `anthropic` SDK
- **Allowlisted fact retrieval** — `app.ai.facts` is the fixed, small set of
  functions (thin wrappers over existing services) the AI is ever allowed to read
- **Deterministic query routing** — a plain Python regex router maps a question
  to one of those functions; there is no LLM tool-use loop and no way for the
  model to pick which backend operation runs
- **Hallucination guardrail** — every 3+ digit number in an AI response must
  appear in the facts payload it was given, or the response is discarded and
  replaced with a structured error
- **No write access** — the AI layer is read/explain-only; it has no code path
  to a review action or a Controller Action
- **Graceful degradation** — every core flow (reconciliation, dashboard,
  review, evaluation) works fully with zero AI dependency

**Transparency note:** live Anthropic generation requires a configured
`ANTHROPIC_API_KEY` and available API credits. No live key exists in this
project's development environment — every AI code path has been verified with a
mocked provider (automated tests) and a temporary local mock (manual UI
verification); the real Anthropic API has not been called from this project.
Without a key, every `/ai/*` endpoint returns a structured "AI unavailable"
response and the rest of the app is unaffected.

## Demo

See [`docs/demo-script.md`](docs/demo-script.md) for the full walkthrough. In short:

1. Generate a demo dataset and run reconciliation — see the dashboard's match/exception charts
2. Open an eligible exception (e.g. `fee_mismatch`) → **Detect** (financial discrepancy panel) → **Explain** (optional, AI) → **Decide** (Controller Action shows eligibility computed server-side) → **Execute** → **Audit** (the action appears in the same audit trail as human review actions)
3. Re-execute or reload to show idempotency (same resulting reference, no duplicate audit entry)
4. Open a non-eligible exception (e.g. `missing_settlement`) to show it requires human review, with no execute button
5. Run the baseline held-out evaluation, then the stress/dirty-data evaluation, and compare the two side by side

## Technology Stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, Alembic, Pydantic
- **AI:** Anthropic SDK behind a provider abstraction
- **Frontend:** React 19, Vite, Tailwind CSS v4, Recharts, Axios, React Router
- **Testing:** Python `unittest` (backend), Vite production build (frontend)

## Repository Structure

```
razorrecon-ai/
├── ARCHITECTURE.md
├── DECISIONS.md
├── PROJECT_STATE.md
├── README.md
├── render.yaml
├── backend/
│   ├── app/
│   │   ├── actions/            # Controller Action engine (Phase 8)
│   │   ├── ai/                 # provider, facts allowlist, query router, service
│   │   ├── api/                # FastAPI routers
│   │   ├── auto_resolution/    # bounded auto-resolution engine
│   │   ├── data_generation/    # deterministic synthetic generator
│   │   ├── db/                 # SQLAlchemy ORM models
│   │   ├── evaluation/         # held-out scoring + stress/dirty-data benchmark
│   │   ├── models/             # domain dataclasses
│   │   ├── reconciliation/     # deterministic matching engine
│   │   ├── review/             # human review workflow
│   │   ├── services/           # orchestration layer
│   │   └── tests/              # unittest suite
│   ├── alembic/                # schema migrations
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/                # single Axios boundary
│   │   ├── components/
│   │   ├── context/             # RunContext
│   │   ├── hooks/
│   │   └── pages/               # Dashboard, Transactions, Exceptions,
│   │                             # Exception Detail, Review Queue, AI
│   │                             # Controller, Evaluation
│   └── package.json
├── data/
│   ├── demo/                   # generated demo datasets (n100/n250/n500)
│   ├── eval/                   # held-out evaluation dataset (n250)
│   └── ground_truth/           # generator's answer key (never read by the engine)
├── scripts/
│   └── generate_data.py
└── docs/
    ├── ai-architecture.md
    ├── api.md
    ├── deployment.md
    ├── demo-script.md
    └── evaluation.md
```

## Local Development

**1. Backend setup**

```bash
# create/activate a Python environment, then:
pip install -r backend/requirements.txt
```

**2. PostgreSQL**

Any local PostgreSQL install works. Create the dev database:

```bash
createdb razorrecon
```

Copy `.env.example` to `.env` at the repo root and set `DATABASE_URL`:

```
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/razorrecon
```

**3. Run migrations**

```bash
cd backend
PYTHONPATH=. python -m alembic upgrade head
```

**4. Start the API**

```bash
cd backend
PYTHONPATH=. uvicorn app.api.main:app --reload
```

Interactive docs at `http://localhost:8000/docs`.

**5. Start the frontend**

```bash
cd frontend
npm install
npm run dev
```

**6. Run tests**

```bash
# unit tests (no DB)
PYTHONPATH=backend python -m unittest discover -s backend/app/tests -p "test_*.py"

# API/integration tests need a separate razorrecon_test database, migrated the same way:
createdb razorrecon_test
cd backend
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/razorrecon_test PYTHONPATH=. python -m alembic upgrade head
cd ..
PYTHONPATH=backend python -m unittest discover -s backend/app/tests -p "test_*.py"
```

Full details: [`docs/api.md`](docs/api.md).

## Deployment

Target: **Vercel** (frontend) + **Render Web Service** (backend) + **Render
PostgreSQL** (database). Docker is not used or required — the app runs directly
from `backend/requirements.txt` on Render's Python runtime.

- **Backend (Render):** root dir `backend`; start command
  `alembic upgrade head && uvicorn app.api.main:app --host 0.0.0.0 --port $PORT`;
  env vars `DATABASE_URL` (required), `ANTHROPIC_API_KEY` (optional),
  `AI_MODEL` (optional), `CORS_ALLOWED_ORIGINS` (required once a frontend URL
  exists). Note: `render.yaml`'s start command only takes effect automatically
  for a service created via Render's Blueprint flow — a manually created Web
  Service needs the start command pasted into its dashboard settings.
- **Database (Render PostgreSQL):** the app normalizes Render's raw
  `postgres://` connection string to `postgresql+psycopg://` automatically at
  startup.
- **Frontend (Vercel):** root dir `frontend`; build command `npm run build`;
  output dir `dist`; env var `VITE_API_BASE_URL` set to the Render backend URL;
  `vercel.json` adds a SPA catch-all rewrite for client-side routing.
- **CORS:** configured via `CORS_ALLOWED_ORIGINS` on the backend; falls back to
  local Vite dev origins when unset, so local development is unaffected.

No public deployment URL is published in this repository yet — see
`PROJECT_STATE.md` for the exact remaining manual steps. Full details:
[`docs/deployment.md`](docs/deployment.md).

## Testing

- **Backend:** 165/165 tests pass (`unittest discover`, verified against a
  local PostgreSQL instance for the DB-backed suites — `test_api.py`,
  `test_ai.py`, `test_evaluation.py`, `test_stress_evaluation.py`,
  `test_datasets.py` — plus unit-only coverage for the domain engines,
  generator, and validation helpers).
- **Frontend:** `npm run build` passes cleanly (Vite production build,
  669 modules, single ~720KB bundle — no code-splitting yet).
- **Deployment verification:** local dev server and local frontend verified;
  the public Render/Vercel deployment has not yet been end-to-end verified from
  this session (see `PROJECT_STATE.md`'s "Next Task").

## Limitations

- All data is synthetic and generator-produced — no real merchant, bank, or
  payment-gateway integration exists.
- **D009**: a documented, investigated boundary case where `amount_mismatch`
  and `partial_settlement` are observationally indistinguishable for a small
  subset of transactions (see `DECISIONS.md` D009/D020).
- The stress benchmark measures the deterministic reconciliation/
  auto-resolution engines under noise only — it does not exercise the AI layer
  or the Controller Action engine under noisy input.
- Live AI generation requires a configured `ANTHROPIC_API_KEY` and available
  Anthropic API credits; no live key exists in this project's development
  environment, and the app is fully functional without one.
- The natural-language query router uses regex pattern matching, not a general
  NLU system — coverage is limited to a fixed set of question categories; an
  unusual phrasing may fall through to a generic fact set or an "unsupported"
  response.
- Dashboard and evaluation metrics are scoped to one run at a time; there is no
  cross-run aggregation.
- No authentication/authorization exists — out of scope for this buildathon submission.
- Larger-scale/production-volume batch processing has not been implemented or tested.

## Future Production Hardening

The following are explicitly **not** implemented — listed here to separate
future direction from current functionality:

- Real merchant/bank/payment-gateway integrations (replacing synthetic data)
- Asynchronous large-batch reconciliation processing
- Stronger semantic query routing (e.g. LLM-driven tool-use) beyond the current regex router
- Authentication and authorization
- Rate limiting
- Production-grade workflow orchestration and observability
- Frontend bundle code-splitting
