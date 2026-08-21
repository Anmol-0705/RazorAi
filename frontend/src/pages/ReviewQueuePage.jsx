import { useMemo } from "react";
import { Link } from "react-router-dom";
import api from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../context/RunContext";
import StatusBadge from "../components/StatusBadge";
import { LoadingState, EmptyState, ErrorState } from "../components/States";
import { formatMoney, titleCase } from "../lib/format";

const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };

export default function ReviewQueuePage() {
  const { runId, refreshKey } = useRunContext();

  const { data: pending, error, loading, refetch } = useAsync(() => {
    if (!runId) return Promise.resolve([]);
    return api.listExceptions({ runId, status: "pending" });
  }, [runId, refreshKey]);

  const { data: inReview } = useAsync(() => {
    if (!runId) return Promise.resolve([]);
    return api.listExceptions({ runId, status: "in_review" });
  }, [runId, refreshKey]);

  const queue = useMemo(() => {
    const combined = [...(pending || []), ...(inReview || [])];
    return combined.sort((a, b) => {
      const rankDiff = (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9);
      if (rankDiff !== 0) return rankDiff;
      return Number(b.financial_impact) - Number(a.financial_impact);
    });
  }, [pending, inReview]);

  if (!runId) {
    return <EmptyState title="No reconciliation run selected" hint="Run reconciliation from the Dashboard first." />;
  }
  if (loading) return <LoadingState label="Loading review queue…" />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (queue.length === 0) {
    return <EmptyState title="Review queue is empty" hint="Nothing pending or in review for this run." />;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Review Queue</h1>
        <p className="text-xs text-slate-500">
          {queue.length} exception{queue.length === 1 ? "" : "s"} awaiting review, ordered by severity then
          financial impact.
        </p>
      </div>

      <ul className="space-y-2">
        {queue.map((e) => (
          <li key={e.id}>
            <Link
              to={`/exceptions/${e.id}`}
              className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300 hover:shadow sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-900">{titleCase(e.exception_type)}</span>
                  <StatusBadge value={e.severity} />
                  <StatusBadge value={e.review_status} />
                </div>
                <p className="mt-1 font-mono text-xs text-slate-500">{e.payment_reference}</p>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <span className="font-semibold text-rose-700">{formatMoney(e.financial_impact)}</span>
                <span className="text-slate-500">{titleCase(e.recommended_action)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
