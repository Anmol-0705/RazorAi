import { LoadingState } from "./States";

/**
 * Renders one AI call's outcome, always keeping "SYSTEM FACTS" (real,
 * backend-derived data) visually separate from "AI EXPLANATION"
 * (the model's interpretation of those facts) — the AI's text never
 * replaces or is styled the same as the actual transaction facts.
 */
export default function AIResultCard({ loading, response, aiLabel = "AI Explanation", children }) {
  if (loading) return <LoadingState label="Asking the AI…" />;
  if (!response) return null;

  if (!response.ai_available) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
        <span className="font-medium">AI unavailable:</span> {response.error || "no reason given"}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {response.facts && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">System Facts</p>
          <pre className="mt-1 max-h-48 overflow-auto rounded-md border border-slate-200 bg-slate-50 p-2 text-xs text-slate-600">
            {JSON.stringify(response.facts, null, 2)}
          </pre>
        </div>
      )}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-violet-600">
          {aiLabel} <span className="font-normal normal-case text-violet-400">— AI-generated interpretation</span>
        </p>
        <div className="mt-1 space-y-2 rounded-md border border-violet-200 bg-violet-50 p-3 text-sm text-violet-900">
          {children}
        </div>
      </div>
    </div>
  );
}
