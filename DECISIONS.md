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

## D010 — Auto-resolution is a separate, stricter gate than the classifier
Phase 3 adds `backend/app/auto_resolution/`, kept deliberately separate
from `backend/app/reconciliation/`: the reconciliation engine decides
what happened; auto-resolution decides whether it's safe to close
automatically. The reconciliation classifier's `auto_resolvable` flag
(D008/D009 context) is only a first-pass candidate signal — the
auto-resolution engine re-checks each candidate against its own bounded
caps (`AutoResolutionConfig`) before acting, and a case failing that
stricter check falls through to human review even if the classifier
marked it a candidate. Concretely: `duplicate_settlement` is now a
classifier candidate too (previously `REQUEST_INFO`/not auto-resolvable
in Phase 2), but is only actually auto-resolved when the duplicate's
amount exactly matches the primary settlement — a mismatched-amount
"duplicate" could be a real second transaction and is never
auto-resolved. Auto-resolution is idempotent by construction: an
exception whose `review_status` is no longer `PENDING` is left alone on
a repeat run, so replays never double-apply or double-log a resolution.

## D011 — ReviewAudit reused as-is for both human and automated actors
`ReviewAudit` (Phase 1 schema-only) is populated for the first time in
Phase 3 for human review actions (`approve`/`reject`/`mark_resolved`/
`add_note`/`start_review` in `backend/app/review/workflow.py`) and was
generic enough to need no changes: `reviewer` holds either a human
identifier or a system actor string, `decision` reuses `ReviewStatus`.
Auto-resolution actions get their own richer, dedicated
`AutoResolutionRecord` type instead of overloading `ReviewAudit`,
because the task requires fields `ReviewAudit` doesn't carry
(resolution type, financial impact, previous/new status) and conflating
"a human reviewed this" with "the system auto-resolved this" into one
schema would make the audit trail harder to query later.

## D012 — ORM models are a separate persistence layer, not a Phase 1-3 rewrite
Phase 4 needed real SQLAlchemy/PostgreSQL persistence. Rather than
converting the Phase 1-3 frozen dataclasses (`app.models.*`) into
SQLAlchemy declarative classes — which would mean rewriting working,
fully-tested domain models and coupling `app.reconciliation`/
`app.auto_resolution`/`app.review` to a database — Phase 4 adds a
parallel ORM layer (`backend/app/db/models.py`) with the same field
names/shapes, and thin converter functions in `app.services.*` at the
boundary. This keeps the 62 Phase 1-3 unit tests passing unmodified
with zero database dependency, and matches this phase's explicit "do
not rebuild Phase 1-3 functionality" instruction. The cost is a small
amount of duplication between dataclass fields and ORM columns; this
was judged acceptable given the schemas are meant to be stable
contracts (per PROJECT_STATE.md's original Phase 1 framing) and rarely
change independently.

## D013 — Reconciliation/exception IDs are scoped per-run at persistence time
`app.reconciliation.engine` and `app.auto_resolution.engine` assign IDs
deterministically (uuid5 over payment/settlement/exception identifiers)
so that re-running the *same* in-memory reconciliation twice produces
byte-identical output — this was a deliberate Phase 2/3 property for
reproducibility and testing. Persisting two different runs of the same
dataset would otherwise try to insert the same primary key twice
(discovered via `test_api.py`'s repeated-reconciliation tests: the
first version of this phase's persistence code hit a
`UniqueViolation`/`ForeignKeyViolation` on a second run over an
unchanged dataset). Fixed by scoping every persisted row's id (and its
FK references) to `f"{run_id}:{domain_id}"` in
`reconciliation_service.py`, leaving the Phase 2/3 engines themselves
unchanged. `db.flush()` is also called between inserting
`reconciliation_results`, `exception_cases`, and
`auto_resolution_records` within one run's transaction, since there is
no ORM `relationship()` between those tables to give SQLAlchemy's
unit-of-work automatic FK-aware insert ordering.

## D014 — Local PostgreSQL used directly; no Docker Compose added
This environment already has PostgreSQL 18 running as a local Windows
service (confirmed via `pg_hba.conf`/process list), so Phase 4 did not
add Docker/docker-compose for Postgres — task step 15 said to add
Docker only if "necessary for local testing." Connection details live
in `.env` (gitignored) with `.env.example` committed as a template. A
second database, `razorrecon_test`, was created for `test_api.py` so
integration tests never touch dev data. A docker-compose file remains
a reasonable addition for portability to environments without a local
Postgres install, but wasn't needed here.

## D015 — Enriched read responses instead of new endpoints for the UI
Building the Transactions and Exception Detail views surfaced a real
integration gap: `GET /reconciliation/runs/{id}/results` and
`GET /exceptions/{id}` only returned reconciliation-engine fields
(match status, strategy, confidence, amount difference) with no
payment/settlement detail (order id, gross amount, payment method,
settlement status, settled amount, fee, tax) and no exception-type/
review-status for a result row — because `PaymentORM`/`SettlementORM`
were never joined against `ReconciliationResultORM`/`ExceptionCaseORM`
in Phase 4. Rather than add new endpoints, `reconciliation_service.py`
gained `_enrich_results()`, which batch-joins the payment/settlement/
exception rows by reference and is reused by both
`list_results()` (Transactions) and `exception_service.get_exception_detail()`
(Exception Detail, via a `result` field on `ExceptionDetailResponse`).
The new response fields are all optional (`None` when a payment,
settlement, or exception doesn't exist for that row — e.g. an orphaned
settlement has no payment), so this is additive, not a breaking schema
change; no existing response field changed shape. Caught one real bug
in this pass: the `/exceptions/{id}` route built `ExceptionDetailResponse`
without passing the `result` field through at all — fixed and covered
by a new `test_api.py` test.

## D016 — CORS restricted to the Vite dev origins, not opened broadly
The frontend (Vite on `:5173`) and backend (FastAPI on `:8000`) are
different origins, so the browser blocked every request until
`CORSMiddleware` was added to `app.api.main.create_app()`. Given
D014/PROJECT_STATE.md's explicit "no authentication yet" stance, this
was scoped narrowly — `allow_origins` lists only
`http://localhost:5173` and `http://127.0.0.1:5173` (`allow_credentials=False`)
rather than `"*"` or any non-local origin, so it doesn't quietly widen
the backend's exposure while auth is still absent.

## D017 — Deterministic regex router, not LLM tool-use, for controller questions
Phase 6A's natural-language finance controller needed a "constrained
query/data-retrieval approach" per its own safety requirement — the
backend must decide what data a question needs before any model call.
Two ways to do that: (a) let Claude pick from a small tool list via
tool-use, or (b) a plain-Python router. Chose (b)
(`backend/app/ai/query_router.py`, regex pattern matching against the
question text) because: the task's example questions map cleanly onto
a handful of fixed categories, a regex router has zero risk of the
model selecting an unintended backend operation (there is no operation
selection for it to influence at all), and it avoids adding an
agentic tool-use loop the task explicitly said to keep out of scope
("do not build an autonomous agent framework"). Tradeoff, accepted and
documented in PROJECT_STATE.md: coverage is only as good as the regex
categories — an oddly-phrased question may fall through to a generic
`dashboard_overview` fact set, or occasionally to "unsupported," rather
than the most specific category. This can be revisited with an
LLM-driven tool-use router later if question coverage becomes a real
problem in practice; the facts allowlist (`app.ai.facts`) is
unaffected either way — it's already the same, small, fixed set.

## D018 — Hallucination guardrail: reject unknown numbers, don't just prompt against them
The safety preamble instructs the model to copy numbers verbatim from
the given facts, but a prompt instruction alone is not enforcement.
`backend/app/ai/service.py._check_for_fabricated_numbers` adds a
structural check: after a successful AI call, every 3+ digit number in
the model's free-text fields is required to appear as a substring
somewhere in the JSON-serialized facts payload it was given; if not,
the whole response is discarded and replaced with a structured error,
never shown as a trustworthy figure. Numbers under 3 digits are
exempt — they're too common in ordinary prose (rankings, small counts)
to reliably signal a fabricated figure, whereas a fabricated financial
amount is almost always 3+ digits. This is a heuristic, not a proof —
documented as a known limitation in PROJECT_STATE.md rather than
oversold as complete hallucination prevention.

## D019 — Evaluation scores against a reused production reconciliation run, not a copy
Phase 7's evaluator (`backend/app/evaluation/`) had to decide whether
to call the production reconciliation pipeline directly or reimplement
matching for scoring purposes. It calls
`app.services.reconciliation_service.run_reconciliation` unmodified,
against a fixed `run_id` (`eval-recon-n250`) so repeated evaluations
replay the same persisted run instead of accumulating a new one on
every call — the same idempotency mechanism already used by demo
reconciliation runs (D013), applied here for a different reason (score
stability, not accidental duplicate submission). This guarantees "the
evaluator must use the same reconciliation implementation used in
production" is true by construction, not by convention — there is
no second matching algorithm to keep in sync.

## D020 — D009 scored as an equivalence class, not merged in ground truth or split as two strict classes
Continuing D009's boundary-case finding (an `amount_mismatch` and a
`partial_settlement` record can be genuinely indistinguishable from
observable fields alone): the evaluator scores
`{amount_mismatch, partial_settlement}` as one equivalence class for
per-class exception-type correctness, reporting the exact
"boundary cases" count and agreement rate separately rather than either
(a) editing `ground_truth.json` to remove the ambiguity — which would
misrepresent what the generator actually produced — or (b) scoring them
as strict, separate classes — which would report a "classification
error" for a case with no available feature that could have avoided it,
overstating a defect. `invalid_reference`'s expected exception type is
similarly mapped to `missing_settlement` (D008's already-documented
behavior) rather than scored as a mystery mismatch. Both mappings live
in one place, `scoring.EXPECTED_EXCEPTION_TYPES`, so the exact
concessions being made are auditable in one small table rather than
scattered through ad-hoc score-adjustment logic.

## D021 — Action Engine eligibility reuses auto-resolution's bounds directly, not a copy
Phase 8's Action Engine (`backend/app/actions/engine.py`) needed a
safety policy deciding which exceptions are safe to act on
automatically. Rather than writing a second set of rupee caps/type
checks, `auto_resolution/engine.py`'s private `_decide()` was split
into two functions: `policy_decision()` (public) — the pure
type/financial-impact bounds check, no `review_status` involved — and
`_decide()` (still private) — `policy_decision()` plus the
idempotency/`PENDING`-only gate `auto_resolve()` needs. All 12 existing
`test_auto_resolution.py` tests pass unmodified after the split,
confirming zero behavior change to Phase 3. `app.actions.engine`
imports `policy_decision` directly. This guarantees the Action Engine
can never be more permissive than the auto-resolution engine it's
built on, and a future change to the caps only has one place to edit.
Deliberately *not* gated on `review_status == PENDING` like
`auto_resolve()` is: by the time a user reaches Exception Detail, an
eligible exception has almost always already been auto-resolved by the
normal reconciliation flow (`review_status == AUTO_RESOLVED`), and
gating on `PENDING` would make the "Execute Controller Action" button
never appear for the common case. Instead, the Action Engine adds its
own, different guard: an exception a human has explicitly `REJECTED`
is never eligible, regardless of type/impact, since executing an
action would silently override that decision.

## D022 — Action execution reuses ReviewAuditORM instead of a new audit table
The bounded finance action needed "before state, action, after state,
rule, actor, timestamp" recorded in the audit trail. Rather than adding
a fourth audit-shaped table (`ReviewAuditORM` already exists for human
review, `AutoResolutionRecordORM` for automated resolution), action
execution writes one `ReviewAuditORM` row per execution
(`action="controller_action"`, `note` carries the action type/reason/
rule/resulting reference, `previous_status`/`new_status` carry the
before/after state) alongside its own dedicated `ActionExecutionORM`
row (which carries the richer, action-specific fields the task
requires: `action_type`, `rule_id`, `idempotency_key`,
`resulting_reference`). This means an executed action shows up in the
same "Audit history" list a human review action does — a real,
demonstrable closed loop — without a fourth parallel audit
representation to keep in sync. `action` is a `String(20)` column
(existing values: `start_review`, `approve`, `reject`, `mark_resolved`,
`add_note`); `controller_action` was chosen to fit that width rather
than widening the column for one new value.

## D023 — Stress evaluation noises only the settlement side, never payments
The Stress / Dirty Data benchmark (Part B) needed to inject realistic
data-quality noise while keeping ground-truth scoring valid.
`app.evaluation.scoring.score()` aligns every ground-truth row to the
run's output via `Payment.transaction_id` /
`ExceptionCaseORM.payment_reference` — both payment-side identifiers.
Perturbing them would silently break that alignment (a "noisy" score
would really just be measuring a broken join, not engine robustness).
`app.evaluation.stress.apply_noise()` therefore only ever perturbs
`Settlement.transaction_reference`, `.settled_amount`, and
`.settled_at` — `Payment.transaction_id` (and every other payment
field) is byte-identical to the clean baseline in every noisy run,
verified directly by `test_stress_evaluation.py`'s
`test_payment_records_are_never_perturbed`. This is not just a scoring
convenience: real-world reconciliation data-quality issues (bank
statement re-exports, delayed settlement feeds, truncated references)
overwhelmingly originate on the settlement/bank-statement side of the
pipeline, not on the merchant's own transaction record, so the
boundary matches the failure mode it's modeling.

## D024 — Stress evaluation runs the engines in memory, never through the DB-persisted service
The baseline evaluation (D019) persists its dataset and calls
`app.services.reconciliation_service.run_reconciliation` specifically
to prove "the evaluator uses the exact same code path production
routes use, through the database, not just the same function in
isolation." The stress benchmark cannot follow that same pattern:
`PaymentORM.transaction_id` and `SettlementORM.settlement_id` are
globally unique columns, and the noisy dataset (D023) intentionally
reuses the baseline eval dataset's exact payment identities — trying
to insert it under a second `dataset_id` would collide with the
already-persisted baseline eval rows on those unique constraints.
Instead, `app.evaluation.stress_service.run_stress_evaluation` calls
`app.reconciliation.engine.reconcile` and
`app.auto_resolution.engine.auto_resolve` directly — the identical,
unmodified pure functions `reconciliation_service` itself calls
internally, just without the database round-trip. This still satisfies
"run the actual production reconciliation engine against the noisy
dataset": it is the same function, not a second matching algorithm: no
different decision was ever written for the stress case. Only the
persistence boundary differs, and it differs for a reason (unique-key
collision), documented here rather than silently worked around.

## D025 — Demo dataset identifiers are namespaced by num_records, not just seed
Following D021-D024's ConflictError safety net (which correctly turned
a same-seed/different-num_records collision into a clean 409 instead
of a crash), the actual production UX need was for the demo UI's
100/250/500 options to coexist under one seed. Investigated why they
collided: `_build_payment`'s `transaction_id`/`order_id` are pure
functions of `(seed, index)` only (never `num_records`), so any two
datasets sharing a seed always collide on their overlapping index
range — globally true regardless of size. Less obviously,
`Payment.id`/`Settlement.id`/`Settlement.settlement_id` (drawn from
the single seeded `random.Random` stream) were *empirically* found to
collide too (27-63 colliding ids per size-pair across n100/n250/n500)
even though they're not literally `f(seed, index)` formulas — because
`_condition_sequence`'s `rng.shuffle()` consumes a different amount of
Mersenne Twister state per `num_records`, occasionally realigning the
underlying word stream in a way far above pure 128-bit chance. Fixed
at two levels: (1) `generate_dataset()` now seeds
`random.Random(f"{seed}:{num_records}")` instead of `random.Random(seed)`,
giving every `(seed, num_records)` pair its own independent RNG
trajectory — the same collision-avoidance guarantee already relied on
for two genuinely different seeds never colliding — while a *repeated*
call with the identical `(seed, num_records)` still reseeds
identically and stays fully reproducible; (2) `transaction_id`,
`order_id`, and `settlement_id` additionally carry an explicit
`N{num_records}` segment as a belt-and-suspenders, construction-level
guarantee (not just statistical confidence) for the fields that
actually carry a DB uniqueness constraint or are user-visible.
`corrupted_ref` (the `invalid_reference` anomaly's deliberately-bogus
settlement reference) was deliberately left unnamespaced — it has no
uniqueness constraint and its `900000-999999` draw range already never
overlaps any real index-based id regardless of `num_records`, so
touching it would be an unrelated rename, not a fix. Already-persisted
datasets (D021-D024's `demo-seed42-n100`/`n250`, and any pre-fix
dataset in general) are never regenerated — `dataset_service`'s
existing-`dataset_id` pre-check still returns them exactly as stored,
so this change only affects *newly generated* datasets, verified with
a legacy-format row inserted directly to simulate already-hosted data
(`test_pre_existing_legacy_format_dataset_is_reused_not_regenerated`).
