import { useState } from "react";
import api from "../api/client";
import { useRunContext } from "../context/RunContext";

const SIZES = [100, 250, 500];
const DEMO_SEED = 42;

export default function RunControl() {
  const { datasetId, setDataset, setRun, bumpRefresh } = useRunContext();
  const [size, setSize] = useState(SIZES[0]);
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState(null); // { tone: 'success' | 'error', text }

  async function handleGenerate() {
    setGenerating(true);
    setMessage(null);
    try {
      const result = await api.generateDemoDataset({ seed: DEMO_SEED, numRecords: size });
      setDataset(result.dataset_id);
      setMessage({
        tone: "success",
        text: result.created
          ? `Generated dataset ${result.dataset_id} (${result.payment_count} payments, ${result.settlement_count} settlements).`
          : `Dataset ${result.dataset_id} already existed — reused it (${result.payment_count} payments).`,
      });
    } catch (err) {
      setMessage({ tone: "error", text: err.message });
    } finally {
      setGenerating(false);
    }
  }

  async function handleRun() {
    if (!datasetId) return;
    setRunning(true);
    setMessage(null);
    try {
      const result = await api.runReconciliation({ datasetId });
      if (result.status === "failed") {
        setMessage({ tone: "error", text: `Run ${result.run_id} failed: ${result.error}` });
      } else {
        setRun(result.run_id, datasetId);
        setMessage({ tone: "success", text: `Run ${result.run_id} completed.` });
        bumpRefresh();
      }
    } catch (err) {
      setMessage({ tone: "error", text: err.message });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Dataset &amp; reconciliation run</h2>
      <p className="mt-1 text-xs text-slate-500">
        Generate a deterministic demo dataset (seed {DEMO_SEED}), then run reconciliation against it.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <div className="flex overflow-hidden rounded-md border border-slate-300">
          {SIZES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSize(s)}
              className={`px-3 py-1.5 text-sm font-medium ${
                size === s ? "bg-slate-900 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={handleGenerate}
          disabled={generating}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {generating ? "Generating…" : "Generate demo dataset"}
        </button>

        <button
          type="button"
          onClick={handleRun}
          disabled={!datasetId || running}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {running ? "Running reconciliation…" : "Run reconciliation"}
        </button>

        {datasetId && (
          <span className="text-xs text-slate-400">
            Dataset: <span className="font-mono">{datasetId}</span>
          </span>
        )}
      </div>

      {message && (
        <p className={`mt-3 text-sm ${message.tone === "error" ? "text-rose-600" : "text-emerald-700"}`}>
          {message.text}
        </p>
      )}
    </div>
  );
}
