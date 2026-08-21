# DECISIONS.md

Log of binding project decisions. Append-only; add new entries at the
bottom with date/phase. Do not rewrite history.

## D001 — Deterministic core, AI at the edges
Reconciliation, matching, totals, and exception classification that
affects money must be deterministic (pure rule-based Python), never
LLM-computed. AI is used only for explanations, advisory
classification hints, and natural-language querying over already-
computed data.

## D002 — Product must survive LLM outage
All core financial features (ingestion, reconciliation, auto-
resolution, review queue, dashboards, evaluation) must work with the
LLM provider fully unavailable. AI features must fail gracefully
(clear "AI unavailable" state), never block core flows.

## D003 — Modular LLM provider abstraction
The AI layer is implemented behind a single provider-agnostic
interface so the underlying LLM provider can be swapped without
touching reconciliation or API logic.

## D004 — Stack lock-in for buildathon scope
Frontend: React + Vite + Tailwind + Recharts + Axios.
Backend: FastAPI + SQLAlchemy + PostgreSQL + Pydantic.
Infra: Docker + Docker Compose.
Chosen for fast iteration and reliable containerized deployment within
buildathon time constraints; not to be swapped without explicit
instruction.

## D005 — Repository hosting constraint (environment-specific)
This chat sandbox has no outbound network access, so it cannot clone
from or push to a remote GitHub repo. Work in this session happens in
a local-only git repo. Syncing to the real GitHub repo is the
project owner's responsibility until this is resolved (e.g. via
Claude Code locally, which has network access).

## D006 — Phase 1 built with stdlib, not Pydantic/SQLAlchemy yet
This sandbox has no network access, so `pip install` cannot fetch
pydantic/sqlalchemy/pytest. Rather than write untestable code, Phase 1
domain models use `dataclasses` with explicit validation functions,
and tests use `unittest` (stdlib). The validation rules and field
shapes are written to map directly onto Pydantic validators and
SQLAlchemy columns later. Migrating to the real stack happens once
dependency installation is possible (Docker build, or a networked
environment) — tracked as a known issue in PROJECT_STATE.md, not
silently deferred.

## D007 — Anomaly counts are exact, not probabilistic
The generator converts target anomaly weights into exact per-condition
counts (rounded, drift absorbed into normal_match) and then does a
seeded shuffle, rather than sampling each record's condition
independently at random. This guarantees every configured anomaly
type actually appears at the requested dataset sizes (100/250/500),
which pure random sampling could fail to do at small n, while
remaining fully deterministic under a fixed seed.
