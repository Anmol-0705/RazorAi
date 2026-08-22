import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../api/client";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";
import ConfirmDialog from "../components/ConfirmDialog";
import AIResultCard from "../components/AIResultCard";
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
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResponse, setAiResponse] = useState(null);
  const [actionSubmitting, setActionSubmitting] = useState(false);
  const [actionResult, setActionResult] = useState(null);
  const [actionError, setActionError] = useState(null);

  if (loading) return <LoadingState label="Loading exception…" />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!detail) return null;

  const exc = detail.exception;
  const result = detail.result;
  // Backend and frontend deploy independently (Render/Vercel) and are
  // never guaranteed to update atomically, so a response can briefly
  // (or, if a deploy is missed, indefinitely) come from a backend that
  // predates this field. Default defensively rather than assume it's
  // always present, same as `detail.controller_action` below.
  const actionExecutions = detail.action_executions ?? [];

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

  async function handleExplainWithAI() {
    setAiLoading(true);
    try {
      const response = await api.explainExceptionWithAI(exc.id);
      setAiResponse(response);
    } catch (err) {
      setAiResponse({ ai_available: false, error: err.message });
    } finally {
      setAiLoading(false);
    }
  }

  async function handleExecuteControllerAction() {
    setActionSubmitting(true);
    setActionError(null);
    try {
      const response = await api.executeControllerAction(exc.id);
      setActionResult(response);
      await refetch();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setActionSubmitting(false);
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
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">AI explanation</h2>
          <button
            type="button"
            onClick={handleExplainWithAI}
            disabled={aiLoading}
            className="rounded-md border border-violet-300 px-3 py-1.5 text-sm font-medium text-violet-700 hover:bg-violet-50 disabled:opacity-50"
          >
            {aiLoading ? "Asking AI…" : "Explain with AI"}
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Uses only the system facts shown above and below — the AI never invents transaction data.
        </p>
        {(aiLoading || aiResponse) && (
          <div className="mt-3">
            <AIResultCard loading={aiLoading} response={aiResponse} aiLabel="AI Explanation">
              {aiResponse?.explanation && (
                <>
                  <p>{aiResponse.explanation}</p>
                  {aiResponse.likely_cause && (
                    <p>
                      <span className="font-medium">Likely cause:</span> {aiResponse.likely_cause}
                    </p>
                  )}
                  {aiResponse.recommended_next_action && (
                    <p>
                      <span className="font-medium">Recommended next action:</span>{" "}
                      {aiResponse.recommended_next_action}
                    </p>
                  )}
                  {aiResponse.uncertainty_note && (
                    <p className="text-xs text-violet-700">Uncertainty: {aiResponse.uncertainty_note}</p>
                  )}
                </>
              )}
            </AIResultCard>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Controller Action</h2>
        <p className="mt-1 text-xs text-slate-500">
          A bounded, synthetic finance-operations instruction executed within this application — never a
          call to a real banking system, never real money movement.
        </p>

        {detail.controller_action && (
          <div className="mt-3 space-y-2 text-sm">
            <Row
              label="Eligible"
              value={
                <span className={detail.controller_action.eligible ? "text-emerald-700" : "text-amber-700"}>
                  {detail.controller_action.eligible ? "Yes" : "Requires human review"}
                </span>
              }
            />
            {detail.controller_action.eligible && (
              <Row label="Action type" value={titleCase(detail.controller_action.action_type)} />
            )}
            <Row label="Reason" value={detail.controller_action.reason} />
            <Row label="Rule" value={<span className="font-mono text-xs">{detail.controller_action.rule_id}</span>} />
            <Row label="Financial impact" value={formatMoney(exc.financial_impact)} />
          </div>
        )}

        {detail.controller_action?.eligible && (
          <div className="mt-3">
            <button
              type="button"
              onClick={handleExecuteControllerAction}
              disabled={actionSubmitting}
              className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {actionSubmitting ? "Executing…" : "Execute Controller Action"}
            </button>
          </div>
        )}

        {actionError && <p className="mt-3 text-sm text-rose-600">{actionError}</p>}

        {actionResult && (
          <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm">
            {actionResult.eligible && actionResult.action ? (
              <>
                <p className="font-medium text-emerald-800">
                  {actionResult.already_executed ? "Action already completed" : "Action completed"}
                </p>
                <p className="mt-1 text-slate-700">
                  Resulting reference:{" "}
                  <span className="font-mono text-xs">{actionResult.action.resulting_reference}</span>
                </p>
                <p className="mt-1 text-slate-700">Updated exception status: {titleCase(actionResult.exception?.review_status)}</p>
                {actionResult.audit && (
                  <p className="mt-1 text-xs text-slate-500">
                    Audit entry recorded ({actionResult.audit.actor}, {formatDateTime(actionResult.audit.created_at)})
                  </p>
                )}
              </>
            ) : (
              <p className="text-amber-800">Requires human review — {actionResult.reason}</p>
            )}
          </div>
        )}

        {actionExecutions.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Action history</p>
            <ul className="mt-2 space-y-2 text-sm">
              {actionExecutions.map((a) => (
                <li key={a.id} className="rounded-md bg-emerald-50 p-2">
                  <span className="font-medium text-emerald-800">{titleCase(a.action_type)}</span>
                  <span className="ml-2 text-xs text-slate-500">{formatDateTime(a.created_at)}</span>
                  <p className="text-slate-600">{a.reason}</p>
                  <p className="text-xs text-slate-400">
                    {a.actor} · rule {a.rule_id} · ref <span className="font-mono">{a.resulting_reference}</span>
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

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
