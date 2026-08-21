export default function EvaluationPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Evaluation</h1>
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
        <p className="text-sm font-medium text-slate-600">Ground-truth evaluation is not wired up yet</p>
        <p className="mt-2 text-sm text-slate-400">
          Phase 1's held-out evaluation dataset and ground-truth labels exist on the backend
          (<code className="font-mono">data/ground_truth/eval</code>), but there is no API endpoint yet
          that scores reconciliation output against them. This page is reserved for that
          precision/recall view once that endpoint is added — it intentionally shows no numbers
          rather than inventing them.
        </p>
        <p className="mt-3 text-xs text-slate-400">
          Known, documented limitation in the meantime: a small subset of very small transactions
          have an observationally ambiguous boundary between <code>amount_mismatch</code> and{" "}
          <code>partial_settlement</code> (DECISIONS.md D009) — expect this page to reflect that,
          not 100% accuracy, once it's built.
        </p>
      </div>
    </div>
  );
}
