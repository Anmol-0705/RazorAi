import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../context/RunContext";
import StatusBadge from "../components/StatusBadge";
import { LoadingState, EmptyState, ErrorState } from "../components/States";
import { formatMoney, titleCase } from "../lib/format";

const STATUS_FILTERS = ["", "matched", "partial", "unmatched", "duplicate"];

export default function TransactionsPage() {
  const { runId, refreshKey } = useRunContext();
  const [status, setStatus] = useState("");

  const { data: results, error, loading, refetch } = useAsync(() => {
    if (!runId) return Promise.resolve([]);
    return api.getRunResults(runId, status ? { status } : {});
  }, [runId, status, refreshKey]);

  if (!runId) {
    return <EmptyState title="No reconciliation run selected" hint="Run reconciliation from the Dashboard first." />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">Transactions</h1>
        <div className="flex overflow-hidden rounded-md border border-slate-300 text-sm">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s || "all"}
              type="button"
              onClick={() => setStatus(s)}
              className={`px-3 py-1.5 font-medium ${
                status === s ? "bg-slate-900 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {s ? titleCase(s) : "All"}
            </button>
          ))}
        </div>
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState error={error} onRetry={refetch} />}
      {!loading && !error && (!results || results.length === 0) && (
        <EmptyState title="No transactions match this filter" />
      )}

      {!loading && !error && results && results.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                {[
                  "Transaction ID",
                  "Order ID",
                  "Amount",
                  "Method",
                  "Payment Status",
                  "Settlement Status",
                  "Reconciliation",
                  "Exception",
                ].map((h) => (
                  <th key={h} className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {results.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono text-xs text-slate-700">{r.payment_reference}</td>
                  <td className="px-4 py-2 text-xs text-slate-500">{r.order_id || "—"}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{formatMoney(r.payment_amount, r.currency)}</td>
                  <td className="px-4 py-2 text-slate-600">{titleCase(r.payment_method)}</td>
                  <td className="px-4 py-2">
                    <StatusBadge value={r.payment_status} />
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge value={r.settlement_status} />
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge value={r.match_status} />
                  </td>
                  <td className="px-4 py-2">
                    {r.exception_id ? (
                      <Link to={`/exceptions/${r.exception_id}`} className="text-sky-700 hover:underline">
                        {titleCase(r.exception_type)}
                      </Link>
                    ) : (
                      <span className="text-slate-400">None</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
