# deployment.md

Deployment target: **Vercel** (frontend) + **Render Web Service**
(backend) + **Render PostgreSQL** (database). Docker is intentionally
not used — this environment (and Render's Python runtime) can run the
existing `backend/requirements.txt` app directly.

This document only prepares the repository for deployment. No public
deployment has actually been performed or tested from this session —
see PROJECT_STATE.md for the exact remaining manual steps.

## Backend on Render

- **Root directory:** `backend`
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `alembic upgrade head && uvicorn app.api.main:app --host 0.0.0.0 --port $PORT`
  - Render injects `PORT`; the app must bind `0.0.0.0`, which the
    command above does explicitly — nothing in the FastAPI code
    hard-codes a host/port (`backend/app/api/main.py` only builds the
    `FastAPI` app; the ASGI server invocation controls host/port).
  - Running `alembic upgrade head` before `uvicorn` on every deploy
    keeps the hosted schema in sync with `backend/alembic/versions/`
    without a separate manual migration step — required on Render's
    Free plan, which has no shell/SSH access to run `alembic upgrade
    head` by hand.
  - **`render.yaml` only applies automatically if the service was
    created via Render's "Blueprint" flow** (New → Blueprint, pointing
    at this repo). A service created via "New → Web Service" and
    pointed at this repo instead ignores `render.yaml` entirely — its
    Start Command lives only in the Render dashboard
    (Settings → Start Command) and must be pasted in by hand:
    ```
    alembic upgrade head && uvicorn app.api.main:app --host 0.0.0.0 --port $PORT
    ```
    Symptom of a stale/missing Start Command: `/health` returns `200`
    (it doesn't touch any table) but every other route 500s with
    `relation "..." does not exist` because the schema was never
    migrated. Fix: update the Start Command in the dashboard as above,
    then trigger a manual deploy (or push any commit) to re-run it.
- **Environment variables:**
  - `DATABASE_URL` (required) — see PostgreSQL section below for the
    exact format. The app reads it via `app.db.base.DATABASE_URL`; if
    unset it silently falls back to a local-Postgres default and will
    fail to connect on Render, surfacing as `database: "unavailable"`
    on `GET /health` and 500s on every DB-backed route. Always set it
    explicitly in the Render dashboard.
  - `ANTHROPIC_API_KEY` (optional) — leave unset to run with AI
    features disabled; every other feature (reconciliation, dashboard,
    evaluation, review) works fully without it. **Never set this in
    the frontend/Vercel project** — it is backend-only.
  - `AI_MODEL` (optional) — defaults to `claude-opus-5` if unset.
  - `CORS_ALLOWED_ORIGINS` (required once a real frontend URL exists)
    — comma-separated list of allowed browser origins, e.g.
    `https://your-app.vercel.app`. If unset, the backend falls back to
    the local Vite dev origins only (`http://localhost:5173`), so a
    deployed frontend will be blocked by CORS until this is set.
- **Health check path:** `/health` — already exists
  (`backend/app/api/routers/health.py`), returns `200` with
  `{"status": "ok", "database": "connected" | "unavailable"}` and
  never depends on `ANTHROPIC_API_KEY`. Accepts both `GET` and `HEAD`
  (a single route registered with `methods=["GET", "HEAD"]`, no second
  implementation) so third-party uptime monitors that probe with `HEAD`
  (e.g. UptimeRobot's free HTTP monitor) get `200` instead of `405`.
- **Migration procedure:** migrations run automatically as part of the
  start command above (`alembic upgrade head`). To run them manually
  against a hosted database from a local machine:
  ```
  cd backend
  DATABASE_URL="<hosted connection string, postgresql+psycopg://...>" \
    alembic upgrade head
  ```
  `backend/alembic/env.py` already reads `DATABASE_URL` from the
  environment (via `app.db.base`) — no hard-coded connection string
  exists anywhere in the migration path.

## PostgreSQL (Render)

1. Create a new **PostgreSQL** instance on Render (any plan/region).
2. Copy its connection string from the Render dashboard. Render gives
   this as `postgres://user:pass@host/dbname` (no driver suffix).
3. Set the backend's `DATABASE_URL` to that string. The app now
   normalizes a plain `postgres://`/`postgresql://` prefix to
   `postgresql+psycopg://` automatically at startup
   (`backend/app/db/base.py`) — this project pins psycopg**3**
   (`psycopg[binary]>=3.2` in `requirements.txt`), and SQLAlchemy
   would otherwise resolve an un-suffixed URL to the (not installed)
   psycopg2 dialect and fail to connect. You can also paste the
   `+psycopg` form directly if you prefer to be explicit.
4. No code anywhere depends on the local Windows PostgreSQL service —
   `app/db/base.py` and `backend/alembic/env.py` both only ever read
   `DATABASE_URL` from the environment; the local-Postgres string is
   just a same-file fallback default for convenience when developing
   with nothing set.
5. Run migrations once the database is reachable (see "Migration
   procedure" above).

## Frontend on Vercel

- **Root directory:** `frontend`
- **Build command:** `npm run build` (Vercel's Vite preset detects
  this automatically; explicit for clarity)
- **Output directory:** `dist` (Vite's default; Vercel's Vite preset
  detects this automatically)
- **Environment variable:** `VITE_API_BASE_URL` — set to the deployed
  Render backend URL, e.g. `https://razorrecon-api.onrender.com`.
  `frontend/src/api/client.js` already reads this
  (`import.meta.env.VITE_API_BASE_URL`, falling back to
  `http://localhost:8000` only when unset) — no source file
  hard-codes `localhost:8000`. Template: `frontend/.env.example`.
- `frontend/vercel.json` adds a catch-all SPA rewrite
  (`/(.*) -> /index.html`), required because the app uses
  `react-router-dom`'s `BrowserRouter`
  (`frontend/src/App.jsx`) — without it, a hard refresh or direct link
  to any non-root route (e.g. `/exceptions/123`) 404s on Vercel's
  static file server instead of loading the SPA and letting the
  client-side router handle it.
- No secrets belong in Vercel's environment variables — only
  `VITE_API_BASE_URL`, which is a public URL, not a credential.

## CORS

The backend's allowed browser origins are configured via the
`CORS_ALLOWED_ORIGINS` environment variable on Render (comma-separated
list), read in `backend/app/api/main.py::_allowed_origins()`. After
the Vercel deployment has a real domain (either the default
`*.vercel.app` domain or a custom domain), set:

```
CORS_ALLOWED_ORIGINS=https://your-app.vercel.app
```

(add a second, comma-separated origin if you also want a custom domain
or a Vercel preview-deployment domain to work). Leaving this variable
unset does not break anything — it falls back to the original local
dev origins (`http://localhost:5173`, `http://127.0.0.1:5173`), so
`npm run dev` against a local backend continues to work exactly as
before with zero configuration.

## AI

- `ANTHROPIC_API_KEY` is **optional**. If it is absent (or invalid),
  `backend/app/ai/anthropic_provider.py` returns
  `AIResult(available=False, ...)` from every call instead of raising
  — the `/ai/*` endpoints return a structured "AI unavailable"
  response, and the frontend's `AIResultCard`/`AIControllerPage`
  render that state instead of an error. Every other feature
  (dashboard, reconciliation, evaluation, exception review) is
  fully independent of this key and works identically with or without
  it — see DECISIONS.md D001/D002.
- If a real key is supplied via Render's environment variables, the
  existing `AnthropicProvider` is used as-is — no code change is
  required to "turn AI on."
- A working key still requires available Anthropic API credits for any
  live call to succeed; an exhausted/invalid key surfaces the same
  graceful "AI unavailable" behavior as no key at all (caught in
  `AnthropicProvider`'s per-method exception handling).

## Held-out evaluation dataset

`backend/app/evaluation/loader.py` reads the committed
`data/eval/n250/` and `data/ground_truth/eval/n250/ground_truth.json`
directly from disk — deployment does not regenerate or alter this
dataset in any way, so evaluation results in production are scored
against the exact same fixed, committed records as in local
development. Reviewed for exposure risk: `GET /evaluation/*` only ever
returns aggregate metrics (`backend/app/evaluation/scoring.py`'s
`EvaluationMetrics` — counts, rates, precision/recall/F1) via
`EvaluationRunResponse.metrics`; no endpoint serializes or exposes raw
per-record `ground_truth.json` contents. No exposure issue found.
