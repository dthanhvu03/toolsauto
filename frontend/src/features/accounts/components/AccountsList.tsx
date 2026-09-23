import { dangerBtnClass, ghostBtnClass, primaryBtnClass } from "@/shared/ui/controls";
import type { AccountRow } from "../types/accounts.types";

function loginStatus(a: AccountRow) {
  return (a.login_status || "").toUpperCase();
}

export function AccountsList({
  rows,
  busyId,
  onToggle,
  onRename,
  onDelete,
  onStartLogin,
  onConfirmLogin,
}: {
  rows: AccountRow[];
  busyId?: number | null;
  onToggle: (id: number) => void;
  onRename: (id: number, name: string) => void;
  onDelete: (id: number) => void;
  onStartLogin: (id: number) => void;
  onConfirmLogin: (id: number) => void;
}) {
  return (
    <ul className="divide-y divide-slate-100">
      {rows.length === 0 ? (
        <li className="px-4 py-8 text-center text-sm text-slate-400">Không có tài khoản</li>
      ) : (
        rows.map((a) => {
          const st = loginStatus(a);
          const loggingIn = st === "LOGGING_IN";
          const needLogin = !st || st === "NEW" || st === "INVALID";
          return (
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
                  <div className="mt-0.5 max-w-md truncate text-[11px] text-slate-400">
                    {a.target_page}
                  </div>
                ) : null}
                {loggingIn ? (
                  <div className="mt-1 text-[11px] font-medium text-indigo-600">
                    Cửa sổ Chromium đã mở — login trong cửa sổ đó, rồi Xác nhận. Đừng dùng Chrome
                    Windows thường.
                  </div>
                ) : null}
                {a.login_error && !loggingIn ? (
                  <div className="mt-1 max-w-md text-[11px] text-red-600">{a.login_error}</div>
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
                {loggingIn ? (
                  <button
                    type="button"
                    className={primaryBtnClass}
                    disabled={busyId === a.id}
                    onClick={() => onConfirmLogin(a.id)}
                  >
                    Xác nhận đăng nhập
                  </button>
                ) : (
                  <button
                    type="button"
                    className={needLogin ? primaryBtnClass : ghostBtnClass}
                    disabled={busyId === a.id}
                    onClick={() => onStartLogin(a.id)}
                  >
                    {st === "ACTIVE" ? "Đăng nhập lại" : "Đăng nhập Chrome"}
                  </button>
                )}
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
          );
        })
      )}
    </ul>
  );
}
