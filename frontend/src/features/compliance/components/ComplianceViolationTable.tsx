import type { ComplianceViolation } from "../types/compliance.types";
import { formatUnix } from "../lib/formatUnix";

function actionTone(action?: string | null) {
  if (action === "VIOLATION") return "bg-red-50 text-red-700";
  if (action === "WARNING") return "bg-amber-50 text-amber-700";
  if (action === "SAFE") return "bg-emerald-50 text-emerald-700";
  return "bg-slate-100 text-slate-600";
}

export function ComplianceViolationTable({ rows }: { rows: ComplianceViolation[] }) {
  if (rows.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-slate-400">Không có bản ghi</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">Thời gian</th>
            <th className="px-3 py-2">Nội dung</th>
            <th className="px-3 py-2">Vi phạm</th>
            <th className="px-3 py-2">Hành động</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((v) => {
            const evidences = (v.violations_found || [])
              .map((h) => h.evidence)
              .filter(Boolean)
              .slice(0, 3)
              .join(", ");
            return (
              <tr key={v.id} className="hover:bg-slate-50/80">
                <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-500">
                  {formatUnix(v.checked_at)}
                </td>
                <td className="max-w-[18rem] truncate px-3 py-2 text-xs text-slate-700">
                  {v.original_content || "—"}
                </td>
                <td className="max-w-[12rem] truncate px-3 py-2 text-xs text-red-600">
                  {evidences || "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${actionTone(
                      v.action_taken
                    )}`}
                  >
                    {v.action_taken || "—"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
