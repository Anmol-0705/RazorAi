import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/transactions", label: "Transactions" },
  { to: "/exceptions", label: "Exceptions" },
  { to: "/review", label: "Review Queue" },
  { to: "/evaluation", label: "Evaluation" },
];

export default function Sidebar() {
  return (
    <aside className="hidden w-56 shrink-0 border-r border-slate-200 bg-white md:flex md:flex-col">
      <div className="flex h-14 items-center border-b border-slate-200 px-5">
        <span className="text-sm font-semibold tracking-tight text-slate-900">RazorRecon AI</span>
      </div>
      <nav className="flex-1 space-y-0.5 p-3">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-slate-200 p-3 text-xs text-slate-400">
        Finance operations console
      </div>
    </aside>
  );
}
