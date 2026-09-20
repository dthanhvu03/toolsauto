import type { OverviewResponse } from "../types/overview.types";

export function OverviewAccountsList({ accounts }: { accounts: OverviewResponse["accounts"] }) {
  return (
    <ul className="divide-y divide-slate-100">
      {accounts.slice(0, 12).map((a) => (
        <li key={a.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
          <span className="font-medium text-slate-800">
            {a.name} <span className="text-xs font-normal text-slate-400">{a.platform}</span>
          </span>
          <span
            className={
              a.is_active ? "text-xs font-semibold text-emerald-600" : "text-xs text-slate-400"
            }
          >
            {a.is_active ? "active" : "off"} · {a.login_status || "—"}
          </span>
        </li>
      ))}
    </ul>
  );
}
