import { useState } from "react";
import api from "../api/client";
import { useAsync } from "../hooks/useAsync";
import StatCard from "../components/StatCard";
import { LoadingState, ErrorState, EmptyState } from "../components/States";
import { formatMoney, formatPercent, formatDateTime } from "../lib/format";

function pct(value) {
  return value === null || value === undefined ? "—" : formatPercent(value);
}

export default function EvaluationPage() {
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const [stressRunning, setStressRunning] = useState(false);
  const [stressRunError, setStressRunError] = useState(null);
  const [stressRefreshKey, setStressRefreshKey] = useState(0);

  const { data: evaluation, error, loading, refetch } = useAsync(
    () => api.getLatestEvaluation().catch((err) => (err.status === 404 ? null : Promise.reject(err))),
    [refreshKey]
  );

  const {
    data: stressEvaluation,
    error: stressError,
    loading: stressLoading,
    refetch: stressRefetch,
  } = useAsync(
    () => api.getLatestStressEvaluation().catch((err) => (err.status === 404 ? null : Promise.reject(err))),
    [stressRefreshKey]
  );

  async function handleRun() {
    setRunning(true);
    setRunError(null);
    try {
      await api.runEvaluation({ datasetName: "n250" });
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setRunError(err.message);
    } finally {
      setRunning(false);
    }
  }

  async function handleRunStress() {
    setStressRunning(true);
    setStressRunError(null);
    try {
      await api.runStressEvaluation({ datasetName: "n250" });
      setStressRefreshKey((k) => k + 1);
    } catch (err) {
      setStressRunError(err.message);
    } finally {
      setStressRunning(false);
    }
  }

  const metrics = evaluation?.metrics;
  const stressMetrics = stressEvaluation?.metrics;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Evaluation</h1>
        <p className="mt-1 text-xs text-slate-500">
          Baseline measures correctness on controlled held-out data. Stress evaluation measures
          resilience when realistic data-quality noise is introduced. Neither is a measure of
          production/customer performance — both are synthetic, reproducible benchmarks.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Baseline Held-Out Synthetic Evaluation</h2>
          <p className="text-xs text-slate-500">
            <span className="rounded-full bg-slate-900 px-2 py-0.5 font-medium text-white">
              Held-out synthetic evaluation
            </span>{" "}
            — scored against a fixed, labeled dataset the reconciliation engine never sees.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={running}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {running ? "Running evaluation…" : "Run Evaluation"}
        </button>
      </div>

      {runError && <p className="text-sm text-rose-600">{runError}</p>}

      {loading && <LoadingState label="Loading evaluation…" />}
      {error && <ErrorState error={error} onRetry={refetch} />}

      {!loading && !error && !evaluation && (
        <EmptyState
          title="No evaluation has been run yet"
          hint="Click 'Run Evaluation' to score the reconciliation engine against the held-out ground-truth dataset."
        />
      )}

      {metrics && (
        <>
          <p className="text-xs text-slate-400">
            Dataset: held-out evaluation set ({evaluation.dataset_name}) · Run at{" "}
            {formatDateTime(evaluation.completed_at)} · Evaluation ID{" "}
            <span className="font-mono">{evaluation.evaluation_id.slice(0, 8)}</span>
          </p>

          <Section title="Evaluation Summary">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <StatCard label="Records Evaluated" value={metrics.reconciliation.total_records} />
              <StatCard label="Match Rate" value={pct(metrics.reconciliation.match_rate)} tone="good" />
              <StatCard label="Precision" value={pct(metrics.reconciliation.precision)} />
              <StatCard label="Recall" value={pct(metrics.reconciliation.recall)} />
              <StatCard label="F1" value={pct(metrics.reconciliation.f1)} />
            </div>
          </Section>

          <Section title="Exception Detection">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Precision" value={pct(metrics.exceptions.detection_precision)} />
              <StatCard label="Recall" value={pct(metrics.exceptions.detection_recall)} />
              <StatCard label="F1" value={pct(metrics.exceptions.detection_f1)} />
              <StatCard
                label="Unresolved Exceptions"
                value={metrics.exceptions.unresolved_exception_count}
                tone="warn"
              />
            </div>
            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              <p className="font-medium">D009 boundary — read before trusting per-class accuracy</p>
              <p className="mt-1">
                {metrics.exceptions.d009_note} Boundary cases in this run:{" "}
                <strong>{metrics.exceptions.d009_boundary_cases}</strong>, agreement rate{" "}
                <strong>{pct(metrics.exceptions.d009_boundary_agreement_rate)}</strong>. Strictly
                classified (non-boundary) cases: {metrics.exceptions.exception_type_classified_cases},
                accuracy {pct(metrics.exceptions.exception_type_accuracy)}.
              </p>
            </div>
          </Section>

          <Section title="Auto Resolution">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <StatCard label="Eligible" value={metrics.auto_resolution.eligible_count} />
              <StatCard label="Resolved" value={metrics.auto_resolution.auto_resolved_count} />
              <StatCard label="Correct" value={metrics.auto_resolution.correctly_auto_resolved_count} tone="good" />
              <StatCard
                label="Incorrect"
                value={metrics.auto_resolution.unsafe_auto_resolved_count}
                tone={metrics.auto_resolution.unsafe_auto_resolved_count > 0 ? "bad" : "good"}
              />
              <StatCard label="Precision" value={pct(metrics.auto_resolution.precision)} />
            </div>
          </Section>

          <Section title="Financial Impact">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Processed" value={formatMoney(metrics.financial.total_amount_processed)} />
              <StatCard label="Reconciled" value={formatMoney(metrics.financial.total_amount_reconciled)} tone="good" />
              <StatCard label="At Risk" value={formatMoney(metrics.financial.amount_at_risk)} tone="bad" />
              <StatCard label="Unresolved" value={formatMoney(metrics.financial.amount_unresolved)} tone="bad" />
            </div>
          </Section>

          <Section title="Methodology &amp; limitations">
            <ul className="list-disc space-y-1 pl-5 text-xs text-slate-600">
              <li>
                Ground truth is Phase 1's seeded, held-out synthetic dataset (seed 1337, 250 records) —
                generated independently from the seed-42 demo data and never read by the reconciliation
                engine at runtime.
              </li>
              <li>
                Predictions come from the same production reconciliation + auto-resolution pipeline used
                everywhere else in this app — this evaluator does not run a separate matching algorithm.
              </li>
              <li>
                Records are matched to ground truth by payment transaction ID; a payment counts as
                "matched" if the engine's reconciliation result for it has status <code>matched</code>.
              </li>
              <li>
                Exception-type correctness accounts for one already-documented system behavior: an{" "}
                <code>invalid_reference</code> condition is scored correct when the engine reports{" "}
                <code>missing_settlement</code> for that payment, because the payment's real settlement
                never arrives (it was misdirected elsewhere) — this is expected, not an error.
              </li>
              <li>
                The amount_mismatch/partial_settlement boundary (D009) is scored as one equivalence class
                rather than two strict classes, since the two are observationally indistinguishable for a
                subset of small transactions — see the callout above for exact counts.
              </li>
              <li>
                This is a synthetic, held-out benchmark for demonstrating reproducible measurement — it is
                not a claim about real production or customer transaction performance.
              </li>
            </ul>
          </Section>
        </>
      )}

      <div className="mt-8 flex items-center justify-between gap-3 border-t border-slate-200 pt-5">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Stress / Dirty Data Evaluation</h2>
          <p className="text-xs text-slate-500">
            <span className="rounded-full bg-amber-700 px-2 py-0.5 font-medium text-white">
              Stress / dirty-data benchmark
            </span>{" "}
            — the same held-out dataset with deterministic, seeded noise injected on the settlement
            side (timestamps, references, rounding). Measures resilience, not production accuracy.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRunStress}
          disabled={stressRunning}
          className="rounded-md bg-amber-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {stressRunning ? "Running stress evaluation…" : "Run Stress Evaluation"}
        </button>
      </div>

      {stressRunError && <p className="text-sm text-rose-600">{stressRunError}</p>}

      {stressLoading && <LoadingState label="Loading stress evaluation…" />}
      {stressError && <ErrorState error={stressError} onRetry={stressRefetch} />}

      {!stressLoading && !stressError && !stressEvaluation && (
        <EmptyState
          title="No stress evaluation has been run yet"
          hint="Click 'Run Stress Evaluation' to score the reconciliation engine against a noisy, seeded copy of the held-out dataset."
        />
      )}

      {stressMetrics && (
        <>
          <p className="text-xs text-slate-400">
            Dataset: {stressEvaluation.dataset_name} · Seed {stressEvaluation.seed} · Run at{" "}
            {formatDateTime(stressEvaluation.completed_at)} · Stress Evaluation ID{" "}
            <span className="font-mono">{stressEvaluation.stress_evaluation_id.slice(0, 8)}</span>
          </p>

          <Section title="Noise Injected">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Total Settlements" value={stressEvaluation.noise_summary.total_settlements} />
              <StatCard
                label="Settlements Affected"
                value={stressEvaluation.noise_summary.affected_settlements}
                tone="warn"
              />
            </div>
            <ul className="mt-3 flex flex-wrap gap-2 text-xs">
              {Object.entries(stressEvaluation.noise_summary.noise_type_counts).map(([type, count]) => (
                <li key={type} className="rounded-full bg-amber-100 px-2.5 py-1 text-amber-800">
                  {type.replaceAll("_", " ")}: {count}
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Baseline vs Stress — Reconciliation">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <StatCard label="Records Evaluated" value={stressMetrics.reconciliation.total_records} />
              <ComparisonStatCard
                label="Match Rate"
                stressValue={pct(stressMetrics.reconciliation.match_rate)}
                baselineValue={metrics ? pct(metrics.reconciliation.match_rate) : null}
              />
              <ComparisonStatCard
                label="Precision"
                stressValue={pct(stressMetrics.reconciliation.precision)}
                baselineValue={metrics ? pct(metrics.reconciliation.precision) : null}
              />
              <ComparisonStatCard
                label="Recall"
                stressValue={pct(stressMetrics.reconciliation.recall)}
                baselineValue={metrics ? pct(metrics.reconciliation.recall) : null}
              />
              <ComparisonStatCard
                label="F1"
                stressValue={pct(stressMetrics.reconciliation.f1)}
                baselineValue={metrics ? pct(metrics.reconciliation.f1) : null}
              />
            </div>
          </Section>

          <Section title="Baseline vs Stress — Exception Detection">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <ComparisonStatCard
                label="Detection Precision"
                stressValue={pct(stressMetrics.exceptions.detection_precision)}
                baselineValue={metrics ? pct(metrics.exceptions.detection_precision) : null}
              />
              <ComparisonStatCard
                label="Detection Recall"
                stressValue={pct(stressMetrics.exceptions.detection_recall)}
                baselineValue={metrics ? pct(metrics.exceptions.detection_recall) : null}
              />
              <StatCard
                label="Unresolved Exceptions"
                value={stressMetrics.exceptions.unresolved_exception_count}
                tone="warn"
              />
              <ComparisonStatCard
                label="Auto-Resolution Classification Agreement"
                stressValue={pct(stressMetrics.auto_resolution.precision)}
                baselineValue={metrics ? pct(metrics.auto_resolution.precision) : null}
              />
            </div>
            <p className="mt-3 text-xs text-slate-500">
              This benchmark measures agreement between the deterministic auto-resolution classifier and
              hidden ground truth under noisy inputs. No Controller Actions are executed during this
              benchmark.
            </p>
          </Section>

          <Section title="Financial Impact (Stress Run)">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Processed" value={formatMoney(stressMetrics.financial.total_amount_processed)} />
              <StatCard
                label="Reconciled"
                value={formatMoney(stressMetrics.financial.total_amount_reconciled)}
                tone="good"
              />
              <StatCard label="At Risk" value={formatMoney(stressMetrics.financial.amount_at_risk)} tone="bad" />
              <StatCard
                label="Unresolved"
                value={formatMoney(stressMetrics.financial.amount_unresolved)}
                tone="bad"
              />
            </div>
          </Section>

          <Section title="Methodology &amp; limitations — stress benchmark">
            <ul className="list-disc space-y-1 pl-5 text-xs text-slate-600">
              <li>
                Noise is injected deterministically from a fixed seed ({stressEvaluation.seed}) into a copy
                of the same seed-1337 held-out dataset used by the baseline above — the committed dataset on
                disk is never modified or regenerated, and the same seed always reproduces byte-identical
                noise.
              </li>
              <li>
                Noise types: timestamp offsets, delayed-settlement timestamps, small rounding differences,
                reference truncation, missing reference prefixes, case/whitespace variations, and
                duplicate/misaligned references — applied only to settlement-side fields.
              </li>
              <li>
                Payment records (and therefore ground truth alignment) are never perturbed — only the
                settlement side is noised, matching where real-world reconciliation data-quality issues
                (bank feed exports, delayed statements) actually originate.
              </li>
              <li>
                Scored by the same production reconciliation + auto-resolution engines and the same scoring
                functions as the baseline evaluation — this is not a second, separately-tuned pipeline.
              </li>
              <li>
                Degraded metrics here are expected and intentional — they demonstrate how the system
                behaves under realistic data-quality stress, not a defect. Lower stress numbers do not
                revise or replace the baseline metrics above.
              </li>
              <li>
                This is a synthetic robustness benchmark, not a production accuracy claim.
              </li>
            </ul>
          </Section>
        </>
      )}
    </div>
  );
}

function ComparisonStatCard({ label, stressValue, baselineValue }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-xl font-semibold text-slate-900">{stressValue}</p>
      {baselineValue !== null && (
        <p className="text-xs text-slate-400">baseline: {baselineValue}</p>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}
