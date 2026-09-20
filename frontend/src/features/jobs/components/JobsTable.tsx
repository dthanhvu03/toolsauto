import { dangerBtnClass, ghostBtnClass } from "@/shared/ui/controls";
import type { JobAction, JobRow } from "../types/jobs.types";

function actionsFor(status: string): { key: JobAction; label: string; danger?: boolean }[] {
  const s = (status || "").toUpperCase();
  if (s === "FAILED") return [{ key: "retry", label: "Retry" }, { key: "reset-draft", label: "Draft" }];
  if (s === "DRAFT") return [{ key: "approve", label: "Duyệt" }, { key: "cancel", label: "Hủy", danger: true }];
  if (s === "PENDING")
    return [
      { key: "force-run", label: "Chạy" },
      { key: "reset-draft", label: "Draft" },
      { key: "cancel", label: "Hủy", danger: true },
    ];
  return [];
}

export function JobsTable({
  rows,
  busyId,
  onAction,
}: {
  rows: JobRow[];
  busyId?: number | null;
  onAction: (id: number, action: JobAction) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">ID</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Account</th>
            <th className="px-3 py-2">Target</th>
            <th className="px-3 py-2">Caption</th>
            <th className="px-3 py-2">Thao tác</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-8 text-center text-slate-400">
                Không có job
              </td>
            </tr>
          ) : (
            rows.map((j) => (
              <tr key={j.id} className="hover:bg-slate-50/80">
                <td className="px-3 py-2 font-mono text-xs">#{j.id}</td>
                <td className="px-3 py-2">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold">
                    {j.status}
                  </span>
                </td>
                <td className="px-3 py-2">{j.account_name || "—"}</td>
                <td className="max-w-[10rem] truncate px-3 py-2 text-xs text-slate-500">
                  {j.target_page || "—"}
                </td>
                <td className="max-w-[16rem] truncate px-3 py-2 text-xs text-slate-600">
                  {j.caption || j.error_message || "—"}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {actionsFor(j.status).map((a) => (
                      <button
                        key={a.key}
                        type="button"
                        className={a.danger ? dangerBtnClass : ghostBtnClass}
                        disabled={busyId === j.id}
                        onClick={() => onAction(j.id, a.key)}
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
