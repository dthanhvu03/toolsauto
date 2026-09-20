import { dangerBtnClass, ghostBtnClass } from "@/shared/ui/controls";
import type { AccountRow } from "../types/accounts.types";

export function AccountsList({
  rows,
  busyId,
  onToggle,
  onRename,
  onDelete,
}: {
  rows: AccountRow[];
  busyId?: number | null;
  onToggle: (id: number) => void;
  onRename: (id: number, name: string) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <ul className="divide-y divide-slate-100">
      {rows.length === 0 ? (
        <li className="px-4 py-8 text-center text-sm text-slate-400">Không có tài khoản</li>
      ) : (
        rows.map((a) => (
          <li
            key={a.id}
            className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm"
          >
            <div>
              <div className="font-semibold text-slate-900">
                {a.name} <span className="text-xs font-normal text-slate-400">#{a.id}</span>
              </div>
              <div className="mt-0.5 text-xs text-slate-500">
                {a.platform} · login {a.login_status || "—"} · limit {a.daily_limit ?? "—"}/ngày
              </div>
              {a.target_page ? (
                <div className="mt-0.5 max-w-md truncate text-[11px] text-slate-400">{a.target_page}</div>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={
                  a.is_active
                    ? "rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700"
                    : "rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-500"
                }
              >
                {a.is_active ? "ACTIVE" : "OFF"}
              </span>
              <button
                type="button"
                className={ghostBtnClass}
                disabled={busyId === a.id}
                onClick={() => onToggle(a.id)}
              >
                {a.is_active ? "Tắt" : "Bật"}
              </button>
              <button
                type="button"
                className={ghostBtnClass}
                disabled={busyId === a.id}
                onClick={() => {
                  const name = window.prompt("Tên mới", a.name);
                  if (name && name.trim() && name.trim() !== a.name) onRename(a.id, name.trim());
                }}
              >
                Đổi tên
              </button>
              <button
                type="button"
                className={dangerBtnClass}
                disabled={busyId === a.id}
                onClick={() => {
                  if (window.confirm(`Xóa account ${a.name}?`)) onDelete(a.id);
                }}
              >
                Xóa
              </button>
            </div>
          </li>
        ))
      )}
    </ul>
  );
}
