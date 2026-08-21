import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../context/RunContext";
import StatusBadge from "../components/StatusBadge";
import { LoadingState, EmptyState, ErrorState } from "../components/States";
import { formatMoney, formatPercent, titleCase } from "../lib/format";

const EXCEPTION_TYPES = [
  "missing_settlement",
  "duplicate_settlement",
  "amount_mismatch",
  "partial_settlement",
  "fee_mismatch",
  "delayed_settlement",
  "invalid_reference",
];
const SEVERITIES = ["low", "medium", "high", "critical"];
const STATUSES = ["pending", "in_review", "approved", "rejected", "auto_resolved"];

export default function ExceptionsPage() {
  const { runId, refreshKey } = useRunContext();
  const [filters, setFilters] = useState({ exceptionType: "", severity: "", status: "" });

  const { data: exceptions, error, loading, refetch } = useAsync(() => {
    if (!runId) return Promise.resolve([]);
    return api.listExceptions({ runId, ...filters });
  }, [runId, filters.exceptionType, filters.severity, filters.status, refreshKey]);

  if (!runId) {
    return <EmptyState title="No reconciliation run selected" hint="Run reconciliation from the Dashboard first." />;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Exceptions</h1>

      <div className="flex flex-wrap gap-3">
        <Select
          label="Type"
          value={filters.exceptionType}
          onChange={(v) => setFilters((f) => ({ ...f, exceptionType: v }))}
          options={EXCEPTION_TYPES}
        />
        <Select
          label="Severity"
          value={filters.severity}
          onChange={(v) => setFilters((f) => ({ ...f, severity: v }))}
          options={SEVERITIES}
        />
        <Select
          label="Status"
          value={filters.status}
          onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
          options={STATUSES}
        />
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState error={error} onRetry={refetch} />}
      {!loading && !error && (!exceptions || exceptions.length === 0) && (
        <EmptyState title="No exceptions match these filters" />
      )}

      {!loading && !error && exceptions && exceptions.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                {["Type", "Severity", "Transaction", "Financial Impact", "Confidence", "Recommended", "Status", ""].map(
                  (h) => (
                    <th key={h} className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {exceptions.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2 font-medium text-slate-800">{titleCase(e.exception_type)}</td>
                  <td className="px-4 py-2">
                    <StatusBadge value={e.severity} />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-slate-600">{e.payment_reference}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{formatMoney(e.financial_impact)}</td>
                  <td className="px-4 py-2 text-slate-500">{formatPercent(e.confidence)}</td>
                  <td className="px-4 py-2 text-slate-600">{titleCase(e.recommended_action)}</td>
                  <td className="px-4 py-2">
                    <StatusBadge value={e.review_status} />
                  </td>
                  <td className="px-4 py-2">
                    <Link to={`/exceptions/${e.id}`} className="text-sky-700 hover:underline">
                      View
                    </Link>
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

function Select({ label, value, onChange, options }) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-600">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {titleCase(o)}
          </option>
        ))}
      </select>
    </label>
  );
}
