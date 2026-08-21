import { titleCase } from "../lib/format";

const PALETTES = {
  // match_status
  matched: "bg-emerald-100 text-emerald-800",
  partial: "bg-amber-100 text-amber-800",
  unmatched: "bg-rose-100 text-rose-800",
  duplicate: "bg-orange-100 text-orange-800",
  // review_status
  pending: "bg-slate-200 text-slate-800",
  in_review: "bg-sky-100 text-sky-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-rose-100 text-rose-800",
  auto_resolved: "bg-violet-100 text-violet-800",
  // severity
  low: "bg-slate-200 text-slate-700",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-rose-100 text-rose-800",
  // run status
  running: "bg-sky-100 text-sky-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
};

export default function StatusBadge({ value, className = "" }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const palette = PALETTES[value] || "bg-slate-200 text-slate-700";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${palette} ${className}`}
    >
      {titleCase(value)}
    </span>
  );
}
