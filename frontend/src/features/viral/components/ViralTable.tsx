import { dangerBtnClass, ghostBtnClass } from "@/shared/ui/controls";
import type { ViralRowAction } from "../api/viralApi";
import type { ViralRow } from "../types/viral.types";

function actionsFor(status: string): { key: ViralRowAction; label: string; danger?: boolean }[] {
  const s = (status || "").toUpperCase();
  const out: { key: ViralRowAction; label: string; danger?: boolean }[] = [];
  if (s === "NEW" || s === "FAILED") out.push({ key: "process", label: s === "FAILED" ? "Thử lại" : "Xử lý" });
  if (s === "READY") out.push({ key: "posted", label: "Đã đăng" });
  if (s === "POSTED") out.push({ key: "unposted", label: "Hoàn tác" });
  out.push({ key: "delete", label: "Xóa", danger: true });
  return out;
}

export function ViralTable({
  items,
  busyId,
  onAction,
}: {
  items: ViralRow[];
  busyId?: number | null;
  onAction: (id: number, action: ViralRowAction) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[800px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">ID</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Views</th>
            <th className="px-3 py-2">Account</th>
            <th className="px-3 py-2">URL</th>
            <th className="px-3 py-2">Job</th>
            <th className="px-3 py-2">Thao tác</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? (
            <tr>
              <td colSpan={7} className="px-3 py-8 text-center text-slate-400">
                Không có material
              </td>
            </tr>
          ) : (
            items.map((it) => (
              <tr key={it.id} className="hover:bg-slate-50/80">
                <td className="px-3 py-2 font-mono text-xs">
                  #{it.id}
                  {it.is_mega ? (
                    <span className="ml-1 text-[10px] font-bold text-amber-600">MEGA</span>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-xs font-semibold">
                  {it.status}
                  {it.last_error ? (
                    <div className="mt-0.5 max-w-[16rem] font-normal text-[11px] text-red-600">
                      {it.last_error}
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-2 tabular-nums">{(it.views ?? 0).toLocaleString()}</td>
                <td className="px-3 py-2 text-xs">{it.account_name || "—"}</td>
                <td className="max-w-[18rem] truncate px-3 py-2 text-xs">
                  <a href={it.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                    {it.url}
                  </a>
                </td>
                <td className="px-3 py-2 text-xs text-slate-500">
                  {it.job_id ? `#${it.job_id} ${it.job_status || ""}` : "—"}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {actionsFor(it.status).map((a) => (
                      <button
                        key={a.key}
                        type="button"
                        className={a.danger ? dangerBtnClass : ghostBtnClass}
                        disabled={busyId === it.id}
                        onClick={() => {
                          if (a.key === "delete" && !window.confirm(`Xóa material #${it.id}?`)) return;
                          onAction(it.id, a.key);
                        }}
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
