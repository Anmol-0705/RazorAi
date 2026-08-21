export default function StatCard({ label, value, sub, tone = "default" }) {
  const toneClass =
    {
      default: "text-slate-900",
      good: "text-emerald-700",
      bad: "text-rose-700",
      warn: "text-amber-700",
    }[tone] || "text-slate-900";

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${toneClass}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}
