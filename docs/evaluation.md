# Evaluation Methodology (Phase 7)

This document explains the held-out ground-truth evaluation pipeline
in `backend/app/evaluation/`. It's evidence-based and deliberately
conservative — it documents what the numbers mean, what they don't,
and one genuine known limitation (D009) rather than presenting a
clean, oversold result.

## What the ground truth represents

`data/eval/n250/{payments,settlements}.json` is Phase 1's deterministic
synthetic generator output for **seed 1337, 250 records** — disjoint
from the seed-42 demo datasets used elsewhere in the app (see
DECISIONS.md D005/D007). `data/ground_truth/eval/n250/ground_truth.json`
is the true, generator-assigned condition for every one of those 250
payments (`normal_match` or one of seven anomaly types), kept in a
physically separate directory tree so the reconciliation engine can
never read it at runtime — only the evaluation pipeline does, and only
after the engine has already produced its predictions.

Condition distribution in this held-out set:

| Condition | Count |
|---|---|
| normal_match | 137 |
| partial_settlement | 20 |
| amount_mismatch | 20 |
| missing_settlement | 18 |
| fee_mismatch | 15 |
| delayed_settlement | 15 |
| duplicate_settlement | 15 |
| invalid_reference | 10 |

## Why the test set is held out

Seed 1337 was generated once in Phase 1 and has never been used to
tune or debug the reconciliation engine — all engine development and
manual verification in Phases 2-2.5 used the seed-42 demo datasets.
Scoring against a set the engine's thresholds were never fitted to is
what makes the resulting metrics meaningful rather than circular.

## How predictions are generated

`app.evaluation.service.run_evaluation`:

1. Loads the committed dataset from disk (`app.evaluation.loader`) —
   never re-invokes the generator, so scoring is always against the
   exact fixed records, not a freshly (if equivalently) regenerated set.
2. Persists it under a dedicated `dataset_id` (`eval-n250`), idempotently
   (same pattern as demo dataset generation — a repeat call is a no-op).
3. Calls `app.services.reconciliation_service.run_reconciliation` — the
   **exact same function** the `POST /reconciliation/runs` API route
   calls — against a fixed reconciliation `run_id` (`eval-recon-n250`),
   so repeated evaluations replay the same underlying run rather than
   recomputing (and rather than accumulating a new reconciliation run
   row every time). This is the same reconciliation + auto-resolution
   pipeline used everywhere else in the app; there is no
   evaluation-only matching algorithm.
4. Loads the persisted `ReconciliationResultORM`/`ExceptionCaseORM` rows
   for that run and scores them against ground truth
   (`app.evaluation.scoring.score`) — pure functions, no DB, no
   randomness.
5. Persists an `EvaluationRunORM` row (metrics as JSON) and returns it.

## How records are matched

Ground truth is indexed by `payment_transaction_id`. For each ground
truth payment, the evaluator looks up every reconciliation result and
exception whose `payment_reference` equals that transaction ID and
aggregates: which `match_status` values it has, and which
`exception_type`s (if any) were raised against it.

One asymmetry worth calling out: `duplicate_settlement`'s ground truth
condition is attached to a single payment, but the engine produces
*two* reconciliation results for it (the primary settlement, matched
cleanly, and the extra one, flagged `duplicate`) — the aggregation
above correctly attributes the `duplicate_settlement` exception to the
payment even though it lives on the second row. Similarly, an
`invalid_reference` orphan settlement produces its own reconciliation
result keyed by the *corrupted* reference, which never matches any real
ground-truth payment ID and is therefore never scored directly — only
the real payment whose settlement went missing is scored (see below).

## How anomalies are scored

Four groups of metrics, all computed from the aggregation above:

- **Reconciliation** — `match_rate = matched_count / total_records`;
  precision/recall/F1 for the binary "cleanly matched, no exception"
  positive class (ground truth `normal_match` vs. a `matched` status
  with zero attached exceptions).
- **Exceptions** — precision/recall/F1 for binary anomaly *detection*
  (any ground-truth condition other than `normal_match` vs. "at least
  one exception was raised for this payment"), independent of which
  exact exception type was assigned. Per-class type correctness is
  reported separately (see D009 below), plus the count of exceptions
  still `pending`/`in_review` after the run.
- **Auto-resolution** — of the exceptions the classifier marked
  `auto_resolvable` ("eligible"), how many the auto-resolution engine
  actually resolved, and of those, how many correspond to a ground
  truth condition the engine is designed to consider safe
  (`fee_mismatch`, `delayed_settlement`, `duplicate_settlement`). Any
  auto-resolved exception whose ground truth condition is *not* one of
  those three is counted as **unsafe** — a real safety regression this
  evaluator would catch, not a metric massaged to look clean.
- **Financial** — total payment amount processed, amount reconciled
  (settled amount for `matched`/`partial` results), and amount at
  risk/unresolved (financial impact of exceptions still
  `pending`/`in_review`). All four numbers come directly from
  persisted `Decimal` fields — the evaluator does no independent
  recomputation of money.

### The `invalid_reference` → `missing_settlement` mapping

A ground-truth `invalid_reference` condition means *this payment's*
real settlement was misdirected to a corrupted, effectively random
reference that doesn't correspond to any real payment (see the
generator). From the payment's own perspective there is no settlement
at all, so the engine correctly reports `missing_settlement`, not
`invalid_reference` — this is the same, already-documented system
behavior as DECISIONS.md D008. The scorer's expected-type table
encodes this explicitly (`invalid_reference` → `missing_settlement`)
rather than reporting it as an unexplained classification error.

## How D009 is handled

DECISIONS.md D009 documents that `amount_mismatch` and
`partial_settlement` are observationally indistinguishable for a
subset of small-amount transactions — the generator's code paths for
both produce a settlement with the same "standard" fee/tax and only a
different settled amount, and no field available to the reconciliation
engine can separate them with certainty in every case.

The evaluator does **not** pretend this ambiguity doesn't exist, and
does **not** silently relabel the ground truth to make the pair
agree. Instead: for scoring per-class exception-type correctness,
`{amount_mismatch, partial_settlement}` is treated as **one
equivalence class** — a prediction of either type counts as correct
when the ground truth condition is either of the two — and the exact
number of "boundary cases" and the agreement rate *within* that pair
are always reported alongside the main exception metrics, never
folded invisibly into an aggregate. If the agreement rate is ever below
100%, that's a genuine, visible signal of one particular disagreement,
not a bug hidden by the equivalence-class handling.

## How the metrics are calculated

All of `backend/app/evaluation/scoring.py` is pure Python: a single
pass building a per-payment aggregation dict, then confusion-matrix
counting and division. No ML frameworks, no external services. See the
module's docstrings and `backend/app/tests/test_evaluation.py`'s
`ScoringUnitTests` for a hand-verified 4-record example that
independently confirms every formula (match rate, precision/recall/F1,
the D009 equivalence-class handling, auto-resolution safety detection,
and financial totals) against manually computed expected values.

## Reproducibility

Given the same dataset file and the same already-persisted
reconciliation run, `score()` always returns byte-identical metrics —
there is no randomness anywhere in the pipeline. `POST /evaluation/run`
called twice in a row reuses the same underlying reconciliation run
(`run_id=eval-recon-n250`) and returns identical `metrics` on both
calls (verified in `test_evaluation.py`'s
`test_repeated_evaluation_produces_identical_metrics`).

## What this evaluation is not

- **Not a production/customer performance claim.** This is a
  synthetic, held-out benchmark built to demonstrate reproducible
  measurement (Razorpay Track 04's 50+ record requirement), always
  labeled **"Held-out synthetic evaluation"** wherever it's shown.
- **Not proof of perfect per-class exception classification** — the
  D009 boundary is real and reported, not hidden.
- **Not an aggregate across multiple runs** — the evaluation UI always
  shows one evaluation run's numbers (`GET /evaluation/latest`),
  consistent with `dashboard_service.compute_summary`'s existing
  single-run-only behavior (see PROJECT_STATE.md's Known Issues).
