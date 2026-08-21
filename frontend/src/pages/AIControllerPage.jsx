import { useState } from "react";
import api from "../api/client";
import { useRunContext } from "../context/RunContext";
import AIResultCard from "../components/AIResultCard";
import { EmptyState } from "../components/States";

const EXAMPLES = [
  "What is causing most reconciliation failures?",
  "How much money is at risk?",
  "Show high severity unresolved exceptions.",
  "Which payment method has the highest exception rate?",
  "How many exceptions were automatically resolved?",
];

export default function AIControllerPage() {
  const { runId } = useRunContext();
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState([]); // [{question, loading, response, error}]

  if (!runId) {
    return <EmptyState title="No reconciliation run selected" hint="Run reconciliation from the Dashboard first." />;
  }

  async function ask(q) {
    const trimmed = q.trim();
    if (!trimmed) return;
    const entryIndex = history.length;
    setHistory((h) => [...h, { question: trimmed, loading: true, response: null, error: null }]);
    setQuestion("");
    try {
      const response = await api.askAIController({ question: trimmed, runId });
      setHistory((h) => h.map((e, i) => (i === entryIndex ? { ...e, loading: false, response } : e)));
    } catch (err) {
      setHistory((h) => h.map((e, i) => (i === entryIndex ? { ...e, loading: false, error: err.message } : e)));
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">AI Controller</h1>
        <p className="text-xs text-slate-500">
          Ask questions about this run's reconciliation data. The backend computes every number
          first — the AI only phrases the answer from those facts, and clearly says so.
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => ask(ex)}
              className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50"
            >
              {ex}
            </button>
          ))}
        </div>

        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
        >
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about this run…"
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={!question.trim()}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Ask
          </button>
        </form>
      </div>

      {history.length === 0 ? (
        <EmptyState title="No questions asked yet" hint="Try one of the examples above." />
      ) : (
        <div className="space-y-4">
          {[...history].reverse().map((entry, idx) => (
            <div key={idx} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-slate-900">{entry.question}</p>
              {entry.error ? (
                <p className="mt-2 text-sm text-rose-600">{entry.error}</p>
              ) : (
                <div className="mt-2">
                  <AIResultCard loading={entry.loading} response={entry.response} aiLabel="AI Answer">
                    {entry.response?.answer && <p>{entry.response.answer}</p>}
                    {entry.response?.caveats && (
                      <p className="text-xs text-violet-700">Caveat: {entry.response.caveats}</p>
                    )}
                  </AIResultCard>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
