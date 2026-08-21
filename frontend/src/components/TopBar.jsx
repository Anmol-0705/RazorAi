import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../context/RunContext";
import api from "../api/client";
import StatusBadge from "./StatusBadge";
import { formatDateTime } from "../lib/format";

export default function TopBar() {
  const { runId, refreshKey } = useRunContext();

  const { data: run } = useAsync(() => {
    if (!runId) return Promise.resolve(null);
    return api.getRun(runId).catch(() => null);
  }, [runId, refreshKey]);

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-5">
      <div className="flex items-center gap-2 text-sm text-slate-500 md:hidden">
        <span className="font-semibold text-slate-900">RazorRecon AI</span>
      </div>
      <div className="hidden text-sm text-slate-500 md:block">Finance operations console</div>

      {run ? (
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="hidden sm:inline">
            Run <span className="font-mono text-slate-700">{run.run_id.slice(0, 8)}</span>
          </span>
          <span>{run.record_count} records</span>
          <StatusBadge value={run.status} />
          <span className="hidden md:inline">{formatDateTime(run.completed_at || run.started_at)}</span>
        </div>
      ) : (
        <span className="text-xs text-slate-400">No reconciliation run yet</span>
      )}
    </header>
  );
}
