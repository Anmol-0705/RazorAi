import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { useRunContext } from "../context/RunContext";
import StatCard from "../components/StatCard";
import RunControl from "../components/RunControl";
import { LoadingState, EmptyState, ErrorState } from "../components/States";
import { formatMoney, formatPercent, titleCase } from "../lib/format";

const STATUS_COLORS = {
  matched: "#059669",
  partial: "#d97706",
  unmatched: "#e11d48",
  duplicate: "#ea580c",
};
const SEVERITY_COLORS = { low: "#94a3b8", medium: "#d97706", high: "#ea580c", critical: "#e11d48" };

export default function DashboardPage() {
  const { runId, refreshKey } = useRunContext();

  const { data: summary, error: summaryError, loading: summaryLoading, refetch } = useAsync(
    () => api.getDashboardSummary(),
    [refreshKey]
  );

  const activeRunId = summary?.run_id || runId;

  const { data: exceptions } = useAsync(() => {
    if (!activeRunId) return Promise.resolve([]);
    return api.listExceptions({ runId: activeRunId, limit: 500 });
  }, [activeRunId, refreshKey]);

  const statusData = useMemo(() => {
    if (!summary) return [];
    return [
      { name: "matched", value: summary.matched },
      { name: "partial", value: summary.partial },
      { name: "unmatched", value: summary.unmatched },
      { name: "duplicate", value: summary.duplicate },
    ].filter((d) => d.value > 0);
  }, [summary]);

  const exceptionTypeData = useMemo(() => {
    if (!exceptions) return [];
    const counts = {};
    for (const e of exceptions) counts[e.exception_type] = (counts[e.exception_type] || 0) + 1;
    return Object.entries(counts)
      .map(([name, count]) => ({ name: titleCase(name), count }))
      .sort((a, b) => b.count - a.count);
  }, [exceptions]);

  const riskByCategory = useMemo(() => {
    if (!exceptions) return [];
    const openStatuses = new Set(["pending", "in_review"]);
    const sums = {};
    for (const e of exceptions) {
      if (!openStatuses.has(e.review_status)) continue;
      sums[e.exception_type] = (sums[e.exception_type] || 0) + Number(e.financial_impact);
    }
    return Object.entries(sums)
      .map(([name, amount]) => ({ name: titleCase(name), amount: Math.round(amount * 100) / 100 }))
      .sort((a, b) => b.amount - a.amount);
  }, [exceptions]);

  return (
    <div className="space-y-6">
      <RunControl />

      {summaryLoading ? (
        <LoadingState label="Loading dashboard…" />
      ) : summaryError ? (
        <ErrorState error={summaryError} onRetry={refetch} />
      ) : !summary?.run_id ? (
        <EmptyState
          title="No reconciliation run yet"
          hint="Generate a demo dataset and run reconciliation above to see metrics here."
        />
      ) : (
        <>
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500">
              Showing the most recently completed run:{" "}
              <span className="font-mono text-slate-700">{summary.run_id}</span>. Metrics are
              scoped to this run only — the backend does not aggregate across multiple runs.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <StatCard label="Total transactions" value={summary.total_transactions} />
            <StatCard label="Matched" value={summary.matched} tone="good" />
            <StatCard label="Unmatched" value={summary.unmatched} tone="bad" />
            <StatCard label="Exceptions" value={summary.exceptions} tone="warn" />
            <StatCard label="Match rate" value={formatPercent(summary.match_rate)} tone="good" />
            <StatCard label="Amount reconciled" value={formatMoney(summary.amount_reconciled)} tone="good" />
            <StatCard label="Amount at risk" value={formatMoney(summary.amount_at_risk)} tone="bad" />
            <StatCard label="Auto-resolution rate" value={formatPercent(summary.auto_resolution_rate)} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard title="Reconciliation status">
              {statusData.length === 0 ? (
                <EmptyState title="No results to chart" />
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90}>
                      {statusData.map((entry) => (
                        <Cell key={entry.name} fill={STATUS_COLORS[entry.name] || "#64748b"} />
                      ))}
                    </Pie>
                    <Legend formatter={(v) => titleCase(v)} />
                    <Tooltip formatter={(v, n) => [v, titleCase(n)]} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard title="Exception distribution by type">
              {exceptionTypeData.length === 0 ? (
                <EmptyState title="No exceptions in this run" />
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={exceptionTypeData} layout="vertical" margin={{ left: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#0f172a" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard title="Amount at risk by category" className="lg:col-span-2">
              {riskByCategory.length === 0 ? (
                <EmptyState title="No open financial risk" hint="All exceptions are resolved or approved." />
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={riskByCategory}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis />
                    <Tooltip formatter={(v) => formatMoney(v)} />
                    <Bar dataKey="amount" fill="#ea580c" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>
          </div>

          <p className="text-xs text-slate-400">
            A settlement/reconciliation trend chart needs a multi-run time series the API doesn't
            expose yet, so it's intentionally left out rather than fabricated. Exception
            classification is deterministic and rule-based; a small, documented boundary case
            between amount-mismatch and partial-settlement exists for a subset of very small
            transactions (see DECISIONS.md D009) — this UI does not claim perfect classification
            accuracy.
          </p>
        </>
      )}
    </div>
  );
}

function ChartCard({ title, children, className = "" }) {
  return (
    <div className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}
