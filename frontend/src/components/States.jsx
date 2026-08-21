export function LoadingState({ label = "Loading…" }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function EmptyState({ title = "Nothing here yet", hint }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 py-16 text-center">
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {hint && <p className="text-sm text-slate-400">{hint}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  const message = error?.message || "Something went wrong.";
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-rose-200 bg-rose-50 py-12 text-center">
      <p className="text-sm font-medium text-rose-700">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-rose-300 bg-white px-3 py-1.5 text-sm font-medium text-rose-700 hover:bg-rose-100"
        >
          Retry
        </button>
      )}
    </div>
  );
}
