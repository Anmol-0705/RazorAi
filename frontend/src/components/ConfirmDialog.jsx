export default function ConfirmDialog({ open, title, description, confirmLabel = "Confirm", tone = "default", onConfirm, onCancel, busy }) {
  if (!open) return null;

  const confirmClass =
    tone === "danger"
      ? "bg-rose-600 hover:bg-rose-700"
      : "bg-slate-900 hover:bg-slate-800";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4">
      <div className="w-full max-w-sm rounded-lg bg-white p-5 shadow-xl">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        {description && <p className="mt-2 text-sm text-slate-500">{description}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`rounded-md px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 ${confirmClass}`}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
