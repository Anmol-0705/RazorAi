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

### Three distinct things this evaluator's "auto-resolution" metric does *not* conflate

The phrase "auto-resolution" spans three separate layers of this
system, and the evaluator's auto-resolution precision/recall metrics
measure only the first one:

1. **Auto-resolution classification** — `app.auto_resolution.engine`
   deterministically flips an exception's `review_status` to
   `auto_resolved` when its type/financial-impact fall within the
   bounded policy (`fee_mismatch`, `delayed_settlement`,
   `duplicate_settlement`, each capped). This is a status label only —
   no money moves and nothing is "executed" at this step.
2. **Controller-action eligibility** — `app.actions.engine.check_eligibility`
   re-checks the same bounded policy (reusing
   `app.auto_resolution.engine.policy_decision` directly) to decide
   whether a bounded, synthetic finance-ops instruction is allowed to
   run for a given exception. This is also just a decision, computed
   from the same reconciliation-engine-derived fields — it has no
   access to ground truth.
3. **Actual Controller Action execution** — only happens when
   `POST /exceptions/{id}/execute-action` is called (a human clicking
   "Execute Controller Action" in the UI, or an equivalent API call),
   producing a persisted `ActionExecution` record with a synthetic
   resulting reference.

The evaluator's auto-resolution precision/recall (both the baseline
and stress benchmarks) score only layer 1 — whether the classification
agrees with hidden ground truth. **Neither evaluation benchmark ever
calls layer 3.** A precision below 1.0 means the deterministic
classifier disagreed with ground truth under the given input
conditions; it is not a count of executed, let alone unsafe, financial
actions. See "Stress / Dirty Data Evaluation" below for what this
means concretely for the stress benchmark's auto-resolution number.

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

# Stress / Dirty Data Evaluation (Part B)

## Why two benchmarks exist

The baseline above answers "does the engine reconcile correctly on
clean, controlled data?" — it deliberately proves correctness against
a fixed, unambiguous ground truth. It does **not** answer "what happens
when the input data isn't clean?", which is the more realistic
production question for a finance-ops system ingesting bank
settlement feeds. The Stress / Dirty Data benchmark exists to answer
that second question honestly, without touching or diluting the first
one: **the baseline's 250-record metrics are never modified, hidden,
or replaced by the stress numbers** — both are always shown side by
side on the Evaluation page.

## What noise is injected

`backend/app/evaluation/stress.py`'s `apply_noise()` perturbs an
in-memory copy of the same seed-1337, 250-record held-out dataset used
by the baseline. Every noise type is applied independently, per
settlement, at its own rate:

| Noise type | What it simulates |
|---|---|
| `timestamp_offset` | Small bank-feed clock skew (±45 min default) |
| `delayed_settlement_timestamp` | A genuinely late settlement feed (pushes `settled_at` ~30h past the 72h delayed-settlement threshold) |
| `rounding_diff` | Paise-level rounding drift from a re-exported bank statement (±₹0.05 default) |
| `reference_truncation` | A bank feed that clips the trailing characters of a reference |
| `missing_reference_prefix` | A feed that strips a leading segment (e.g. `TXN-`) from a reference |
| `case_whitespace` | Case changes / stray whitespace around a reference |
| `duplicate_misaligned_reference` | A settlement's reference reassigned to a *different* payment's transaction ID — a misaligned/duplicated bank record |

**Only settlement-side fields are ever perturbed** —
`Payment.transaction_id` (and every other payment field) is
byte-identical to the clean baseline in every stress run. This is a
deliberate boundary, not an oversight: `scoring.score()` aligns ground
truth to the run's output via payment-side identifiers, so perturbing
them would just break the join rather than test robustness. It also
matches where real reconciliation data-quality problems actually
originate — the settlement/bank-statement side, not the merchant's own
transaction record. See DECISIONS.md D023.

The committed dataset files under `data/eval/n250/` are never modified
or regenerated by this process — `apply_noise()` returns a new,
noised copy; `test_stress_evaluation.py`'s
`test_source_dataset_on_disk_is_not_mutated` verifies this directly by
reloading from disk after noise injection and comparing.

## How the seed makes it reproducible

A single `random.Random(seed)` stream (default seed `9001`) is
consumed in a fixed, sorted iteration order
(`sorted(settlements, key=lambda s: s.settlement_id)`). The same seed
always produces byte-identical noisy settlements and an identical
noise log — verified by
`test_stress_evaluation.py`'s `NoiseReproducibilityTests` and by
`StressEvaluationApiTests.test_repeated_stress_run_is_deterministic`,
which runs the full `POST /evaluation/stress/run` endpoint twice and
asserts identical `metrics` and `noise_summary`.

## How it's scored

`backend/app/evaluation/stress_service.py` calls
`app.reconciliation.engine.reconcile` and
`app.auto_resolution.engine.auto_resolve` — the same unmodified pure
functions the baseline evaluation and every reconciliation API route
use — directly against the noisy in-memory dataset, then scores with
the same `app.evaluation.scoring.score()` the baseline uses. This is
run in memory rather than through the persisted
`reconciliation_service` pipeline the baseline goes through, because
the noisy dataset intentionally reuses the baseline's exact payment/
settlement identifiers (to keep ground-truth alignment valid), and
those are globally-unique database columns — persisting a second copy
under them would collide with the already-persisted baseline rows. See
DECISIONS.md D024 for the full reasoning; the engines invoked are
identical either way, so this does not change what's actually being
measured.

Only `reconcile()` and `auto_resolve()` are called — `app.actions`
(the Controller Action Engine) is never imported or invoked anywhere
in `stress.py` or `stress_service.py`, and nothing here persists to
the database or calls `POST /exceptions/{id}/execute-action`. **The
stress benchmark executes zero Controller Actions, every run.** Its
"Auto-Resolution Classification Agreement" metric (labeled
"Auto-Resolution Precision" prior to this clarification) measures
layer 1 only, from the three-layer distinction above: whether
`auto_resolve()`'s classification agrees with hidden ground truth
under the injected noise. It is not, and has never been, a report of
executed or unsafe financial actions.

## Baseline vs. Stress — reference numbers from this session

Both were run against the real 250-record held-out dataset in this
session (seed 9001 for noise). Numbers will regenerate identically on
any future run with the same seeds — these are not fabricated or
hand-picked:

| Metric | Baseline | Stress |
|---|---|---|
| Match rate | 80.8% | 71.2% |
| Reconciliation precision / recall / F1 | 1.0 / 1.0 / 1.0 | 0.94 / 0.74 / 0.83 |
| Exception detection precision / recall / F1 | 1.0 / 1.0 / 1.0 | 0.75 / 0.95 / 0.84 |
| Auto-resolution classification agreement | 1.0 (44/44 correct, 0 unsafe) | 0.85 (34/40 correct) |

Match rate and precision/recall degrade meaningfully but the system
keeps functioning — exception detection *recall* actually rises under
noise (more things correctly get flagged as exceptions, since noise
frequently breaks a previously-clean match), while detection precision
falls (some noise gets flagged that a human would recognize as
harmless). This is the honest signal the benchmark is built to surface:
graceful degradation, not silent failure and not a claim of unaffected
accuracy.

## Limitations

- The specific degradation numbers above are a property of this
  session's default `NoiseConfig` rates (e.g. 15% timestamp-offset
  rate, 6% reference-truncation rate) — they are not universal
  constants, and changing the config changes the numbers. What stays
  constant is that the *same* config + seed always reproduces the
  *same* numbers.
- Noise is applied independently per type per settlement (not
  correlated), which may understate or overstate real-world
  data-quality patterns where multiple issues on the same record
  cluster together or apart differently.
- This benchmark measures the deterministic reconciliation/
  auto-resolution engines only — it does not exercise the AI layer or
  the Action Engine (Phase 8) under noise.
- **Not a production performance claim**, exactly like the baseline:
  this is a synthetic robustness demonstration, not a measurement of
  real bank feed data, which may exhibit noise patterns, rates, or
  correlations this benchmark does not model.
