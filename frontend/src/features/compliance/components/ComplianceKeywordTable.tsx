import type { ComplianceKeyword } from "../types/compliance.types";
import { dangerBtnClass, ghostBtnClass } from "@/shared/ui/controls";

export function ComplianceKeywordTable({
  rows,
  onToggle,
  onDelete,
}: {
  rows: ComplianceKeyword[];
  onToggle: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  if (rows.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-slate-400">Không có từ khóa</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">Từ khóa</th>
            <th className="px-3 py-2">Danh mục</th>
            <th className="px-3 py-2">Mức độ</th>
            <th className="px-3 py-2">Nguồn</th>
            <th className="px-3 py-2">Trạng thái</th>
            <th className="px-3 py-2">Thao tác</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-slate-50/80">
              <td className="px-3 py-2 font-medium">{r.keyword}</td>
              <td className="px-3 py-2 text-xs text-slate-600">{r.category}</td>
              <td className="px-3 py-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                    r.severity === "VIOLATION"
                      ? "bg-red-50 text-red-700"
                      : "bg-amber-50 text-amber-700"
                  }`}
                >
                  {r.severity}
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-slate-400">{r.source || "—"}</td>
              <td className="px-3 py-2 text-xs">
                {r.is_active ? (
                  <span className="font-medium text-emerald-700">active</span>
                ) : (
                  <span className="text-slate-400">tắt</span>
                )}
              </td>
              <td className="px-3 py-2">
                <div className="flex gap-1">
                  <button type="button" className={ghostBtnClass} onClick={() => onToggle(r.id)}>
                    {r.is_active ? "Tắt" : "Bật"}
                  </button>
                  <button
                    type="button"
                    className={dangerBtnClass}
                    onClick={() => {
                      if (window.confirm(`Xóa từ khóa ${r.keyword}?`)) onDelete(r.id);
                    }}
                  >
                    Xóa
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
