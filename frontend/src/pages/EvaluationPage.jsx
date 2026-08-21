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

  const { data: evaluation, error, loading, refetch } = useAsync(
    () => api.getLatestEvaluation().catch((err) => (err.status === 404 ? null : Promise.reject(err))),
    [refreshKey]
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

  const metrics = evaluation?.metrics;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Evaluation</h1>
          <p className="text-xs text-slate-500">
            <span className="rounded-full bg-slate-900 px-2 py-0.5 font-medium text-white">
              Held-out synthetic evaluation
            </span>{" "}
            — scored against a fixed, labeled dataset the reconciliation engine never sees. Not a
            measure of production/customer performance.
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
