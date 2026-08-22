# demo-script.md

A concise walkthrough for demonstrating RazorRecon AI (Razorpay AI
Builder Buildathon, Track 04 — AI Finance Controller). Assumes the
backend and frontend are both running locally (see docs/api.md) or
against the deployed environment (see docs/deployment.md).

## 1. Generate data and reconcile (existing flow)

1. Dashboard → generate a demo dataset (seed 42, 100 records) → run
   reconciliation.
2. Point out the dashboard's match-status/exception-type charts and
   the explicit "this run only, not an aggregate" labeling.

## 2. Detect → explain → decide → execute → audit (Phase 8, the closed loop)

This is the core new story: the product now closes the loop from
detection to a bounded, safe, automated resolution — not just
detection and human review.

1. Exceptions → filter by type `fee_mismatch` → open one.
2. **Detect**: the Financial Discrepancy panel shows the real payment/
   settlement numbers computed by the deterministic reconciliation
   engine.
3. **Explain** (optional): click "Explain with AI" — note the SYSTEM
   FACTS / AI EXPLANATION split; the AI only phrases numbers already
   shown above it.
4. **Decide**: scroll to "Controller Action" — it already shows
   `Eligible: Yes`, the action type
   (`settlement_adjustment_instruction`), the reason, the rule ID, and
   the financial impact — computed server-side, before any button is
   clicked.
5. **Execute**: click "Execute Controller Action". Show the resulting
   synthetic reference (`SYN-SAI-...`), the updated exception status,
   and the new entry in "Action history".
6. **Audit**: scroll to "Audit history" — the same action appears
   there too (`Controller Action`), alongside any human review
   actions, in one unified trail.
7. Click "Execute Controller Action" again (if still visible) or
   reload the page — point out it's a no-op: the same resulting
   reference, no duplicate audit entry. This demonstrates the
   idempotency requirement live.
8. Open a `missing_settlement` or `amount_mismatch` exception instead
   — show "Controller Action" now reads `Requires human review` with
   no button, proving the eligibility policy (not the UI) gates
   execution.

Talking point: the LLM never picked this action or executed it — the
Action Engine (`app.actions.engine`) is a separate, deterministic,
rule-based module the AI has no code path into. See
`docs/ai-architecture.md`'s "The AI cannot execute" section.

## 3. Baseline vs. Stress evaluation (Part B)

1. Evaluation page → "Run Evaluation" (baseline, if not already run)
   — point out the 250-record held-out metrics (typically ~100%
   precision/recall on this fixed dataset).
2. Scroll to "Stress / Dirty Data Evaluation" → "Run Stress
   Evaluation".
3. Show the "Noise Injected" section — real counts of how many
   settlements were perturbed and by which noise type, not a claim.
4. Show the baseline-vs-stress comparison cards — match rate,
   precision/recall, auto-resolution precision all visibly drop under
   noise (real numbers from this session: match rate 80.8% → 71.2%,
   auto-resolution precision 1.0 → 0.85).
5. Talking point: this is intentional and expected — it demonstrates
   *honest degradation* under realistic data-quality stress, not a
   flaw. The baseline metrics directly above are never altered by
   running the stress benchmark.
6. Run the stress evaluation a second time — point out the metrics are
   byte-identical (same seed, same noise, same result), proving
   reproducibility rather than randomness.

## Things to explicitly say out loud

- "Nothing here calls a real bank or moves real money — every action
  is a synthetic instruction recorded inside this application."
- "The AI explains and recommends; a separate deterministic engine —
  reusing the exact same safety caps as auto-resolution — decides what
  can execute automatically, and executes it."
- "The stress benchmark doesn't touch the baseline's numbers — both
  are always shown side by side, and both are reproducible from a
  fixed seed, not cherry-picked."
