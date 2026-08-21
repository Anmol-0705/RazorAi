import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../api/client";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";
import ConfirmDialog from "../components/ConfirmDialog";
import { LoadingState, ErrorState } from "../components/States";
import { formatMoney, formatPercent, formatDateTime, titleCase } from "../lib/format";

const ACTIONS = [
  { key: "start-review", label: "Start Review", tone: "default" },
  { key: "approve", label: "Approve", tone: "default", confirm: "Approve this resolution?" },
  { key: "reject", label: "Reject", tone: "danger", confirm: "Reject this proposed resolution?" },
  { key: "mark-resolved", label: "Mark Resolved", tone: "default", confirm: "Mark this exception resolved?" },
];

export default function ExceptionDetailPage() {
  const { id } = useParams();
  const { data: detail, error, loading, refetch } = useAsync(() => api.getExceptionDetail(id), [id]);
  const [note, setNote] = useState("");
  const [pendingAction, setPendingAction] = useState(null); // action being confirmed
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [reviewer, setReviewer] = useState("reviewer@razorpay.com");

  if (loading) return <LoadingState label="Loading exception…" />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!detail) return null;

  const exc = detail.exception;
  const result = detail.result;

  async function runAction(actionKey) {
    setSubmitting(true);
    setFeedback(null);
    try {
      await api.reviewAction(exc.id, actionKey, { reviewer, note });
      setNote("");
      setFeedback({ tone: "success", text: `${titleCase(actionKey.replace("-", "_"))} recorded.` });
      await refetch();
    } catch (err) {
      setFeedback({ tone: "error", text: err.message });
    } finally {
      setSubmitting(false);
      setPendingAction(null);
    }
  }

  async function handleAddNote() {
    if (!note.trim()) return;
    setSubmitting(true);
    setFeedback(null);
    try {
      await api.reviewAction(exc.id, "add-note", { reviewer, note });
      setNote("");
      setFeedback({ tone: "success", text: "Note added." });
      await refetch();
    } catch (err) {
      setFeedback({ tone: "error", text: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  function requestAction(action) {
    if (action.confirm) {
      setPendingAction(action);
    } else {
      runAction(action.key);
    }
  }

  const diff = result ? Number(result.amount_difference) : null;

  return (
    <div className="space-y-5">
      <div>
        <Link to="/exceptions" className="text-xs text-sky-700 hover:underline">
          ← Back to exceptions
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold text-slate-900">{titleCase(exc.exception_type)}</h1>
          <StatusBadge value={exc.severity} />
          <StatusBadge value={exc.review_status} />
        </div>
        <p className="mt-1 font-mono text-xs text-slate-500">
          Transaction {exc.payment_reference} · Exception {exc.id}
        </p>
      </div>

      {result && (
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Financial discrepancy</h2>
          <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Metric label="Payment amount" value={formatMoney(result.payment_amount, result.currency)} />
            <Metric label="Settled amount" value={formatMoney(result.settled_amount, result.currency)} />
            <Metric
              label="Difference"
              value={formatMoney(result.amount_difference, result.currency)}
              tone={diff > 0 ? "bad" : "default"}
            />
          </div>
          <p className="mt-3 text-sm text-slate-600">{result.reason}</p>
        </section>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Payment details</h2>
          <dl className="mt-2 space-y-1 text-sm">
            <Row label="Order ID" value={result?.order_id} />
            <Row label="Payment method" value={titleCase(result?.payment_method)} />
            <Row label="Payment status" value={<StatusBadge value={result?.payment_status} />} />
          </dl>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Settlement details</h2>
          <dl className="mt-2 space-y-1 text-sm">
            <Row label="Settlement reference" value={result?.settlement_reference} mono />
            <Row label="Settlement status" value={<StatusBadge value={result?.settlement_status} />} />
            <Row label="Fee" value={formatMoney(result?.fee, result?.currency)} />
            <Row label="Tax" value={formatMoney(result?.tax, result?.currency)} />
          </dl>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Reconciliation</h2>
          <dl className="mt-2 space-y-1 text-sm">
            <Row label="Match status" value={<StatusBadge value={result?.match_status} />} />
            <Row label="Match strategy" value={titleCase(result?.match_strategy)} />
            <Row label="Confidence" value={formatPercent(result?.confidence)} />
          </dl>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Exception classification</h2>
          <dl className="mt-2 space-y-1 text-sm">
            <Row label="Financial impact" value={formatMoney(exc.financial_impact)} />
            <Row label="Recommended action" value={titleCase(exc.recommended_action)} />
            <Row label="Auto-resolvable" value={exc.auto_resolvable ? "Yes" : "No"} />
            <Row label="Detected" value={formatDateTime(exc.created_at)} />
          </dl>
        </section>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Human review</h2>
        <p className="mt-1 text-xs text-slate-500">
          Current status: <StatusBadge value={exc.review_status} />
        </p>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            type="text"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            placeholder="Reviewer email"
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm sm:w-56"
          />
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional for actions, required for Add Note)"
            className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {ACTIONS.map((action) => (
            <button
              key={action.key}
              type="button"
              disabled={submitting}
              onClick={() => requestAction(action)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${
                action.tone === "danger"
                  ? "border border-rose-300 text-rose-700 hover:bg-rose-50"
                  : "border border-slate-300 text-slate-700 hover:bg-slate-50"
              }`}
            >
              {action.label}
            </button>
          ))}
          <button
            type="button"
            disabled={submitting || !note.trim()}
            onClick={handleAddNote}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Add Note
          </button>
        </div>

        {feedback && (
          <p className={`mt-3 text-sm ${feedback.tone === "error" ? "text-rose-600" : "text-emerald-700"}`}>
            {feedback.text}
          </p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Audit history</h2>

        {detail.auto_resolutions.length === 0 && detail.review_audits.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">No automated or human actions recorded yet.</p>
        ) : (
          <ul className="mt-3 space-y-2 text-sm">
            {detail.auto_resolutions.map((r) => (
              <li key={r.id} className="rounded-md bg-violet-50 p-2">
                <span className="font-medium text-violet-800">{titleCase(r.resolution_type)}</span>
                <span className="ml-2 text-xs text-slate-500">{formatDateTime(r.created_at)}</span>
                <p className="text-slate-600">{r.reason}</p>
                <p className="text-xs text-slate-400">
                  {r.actor} · {titleCase(r.previous_status)} → {titleCase(r.new_status)}
                </p>
              </li>
            ))}
            {detail.review_audits.map((a) => (
              <li key={a.id} className="rounded-md bg-slate-50 p-2">
                <span className="font-medium text-slate-800">{titleCase(a.action)}</span>
                <span className="ml-2 text-xs text-slate-500">{formatDateTime(a.created_at)}</span>
                {a.note && <p className="text-slate-600">{a.note}</p>}
                <p className="text-xs text-slate-400">
                  {a.actor} · {titleCase(a.previous_status)} → {titleCase(a.new_status)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ConfirmDialog
        open={!!pendingAction}
        title={pendingAction?.label}
        description={pendingAction?.confirm}
        confirmLabel={pendingAction?.label}
        tone={pendingAction?.tone === "danger" ? "danger" : "default"}
        busy={submitting}
        onCancel={() => setPendingAction(null)}
        onConfirm={() => runAction(pendingAction.key)}
      />
    </div>
  );
}

function Metric({ label, value, tone = "default" }) {
  const toneClass = tone === "bad" ? "text-rose-700" : "text-slate-900";
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-xl font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}

function Row({ label, value, mono = false }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className={mono ? "font-mono text-xs text-slate-700" : "text-slate-800"}>{value ?? "—"}</dd>
    </div>
  );
}
