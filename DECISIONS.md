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

## D008 — Reconciliation thresholds are business rules, not ground truth
The reconciliation engine (Phase 2) needs a standard fee schedule
(2% fee, 18% tax on fee) and thresholds (amount/fee tolerance, the
90%-of-expected-net partial-settlement cutoff, the delayed-settlement
timestamp window) to classify amount and timing discrepancies. These
constants happen to match the synthetic generator's defaults, but they
are checked in as `ReconciliationConfig` business rules the engine
would need against real data too — the engine never imports or reads
`app.data_generation.ground_truth` or `GroundTruthCondition`. Verified
against the seeded demo datasets: `duplicate_settlement`,
`fee_mismatch`, `delayed_settlement`, `partial_settlement`, and
`invalid_reference` exception counts match ground truth exactly at
n=100/250, and within 1 at n=500 (one small-amount case where the
90% fraction threshold and the generator's own amount-mismatch delta
range overlap — an accepted heuristic edge case, not a bug). The
engine's `missing_settlement` count is ground-truth `missing_settlement`
+ `invalid_reference`, because a payment whose settlement was
misdirected is correctly flagged missing on the payment side too.

## D009 — Phase 2.5: amount-mismatch/partial-settlement boundary is a
## documented, accepted limit — not a bug
Investigated the n=500 edge case from D008 (one `amount_mismatch` case
reclassified as `partial_settlement`) before starting Phase 3.
Findings, computed directly from the seeded datasets:
- Added `ReconciliationConfig.partial_settlement_min_absolute_diff`
  (default 1.00): a shortfall must clear this absolute floor, not just
  the 90%-of-expected-net fraction, to count as `partial_settlement`.
  This is a real fix for small-value transactions, where a few paise
  of rounding noise could otherwise cross the 90% fraction line and
  get mislabeled partial. Regression tests cover this directly
  (`SmallAmountRegressionTests` in `test_reconciliation.py`).
- The specific n=500 case (payment amount 100.48, shortfall 44.08) is
  provably **not fixable** by any monotonic rule over
  (fraction-of-net-settled, absolute shortfall) without breaking a
  different, legitimately-labeled `partial_settlement` case in the same
  dataset (shortfall 25.78, a *smaller* absolute number than the
  mismatch case, but with fraction/absolute values that look identical
  in shape). This isn't a classifier weakness: `Settlement.fee` and
  `Settlement.tax` are identical (both "standard") in both the
  generator's `amount_mismatch` and `partial_settlement` code paths, so
  no observable field distinguishes them at this boundary. Ground
  truth's label for this one record is an artifact of which code path
  the generator happened to take, not a recoverable property of the
  data. Read another way, this record is legitimately ambiguous by
  real-world standards too: 45% of an expected payout going missing on
  a ₹100 transaction reads as a partial payout, not simple rounding
  noise — the engine's classification is defensible independent of the
  generator's label.
- Decision: keep the fraction-based rule (unchanged 90% threshold) as
  the primary signal, add the absolute floor as a secondary safeguard
  for small amounts, and treat this one boundary case as an accepted,
  explained limitation rather than force-fitting a threshold that would
  only move the error onto a different record. Re-verified after the
  fix: `duplicate_settlement`, `fee_mismatch`, `delayed_settlement`
  counts still match ground truth exactly at n=100/250/500;
  `amount_mismatch`/`partial_settlement` unchanged from D008 (exact at
  n=100/250, off by the same single case at n=500).
- Also added (Phase 2.5): when a payment is missing its settlement,
  `ReconciliationResult.reason` now notes if any orphan (invalid-
  reference) settlements exist in the same batch, so a later evaluation
  layer can flag the ambiguity between "genuinely missing" and
  "settlement was misdirected elsewhere" without the engine claiming a
  causal link it cannot prove (references in the invalid-reference
  anomaly are uncorrelated with any real payment by construction).
