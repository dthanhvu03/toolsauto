import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";

export function QuickLink({
  to,
  title,
  desc,
  icon: Icon,
}: {
  to: string;
  title: string;
  desc: string;
  icon: LucideIcon;
}) {
  return (
    <Link
      to={to}
      className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-200"
    >
      <span className="rounded-lg bg-indigo-50 p-2 text-indigo-700">
        <Icon className="size-5" />
      </span>
      <div>
        <div className="font-semibold text-slate-900">{title}</div>
        <div className="mt-1 text-xs text-slate-500">{desc}</div>
      </div>
    </Link>
  );
}
