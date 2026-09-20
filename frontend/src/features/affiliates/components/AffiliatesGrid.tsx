import { dangerBtnClass, ghostBtnClass } from "@/shared/ui/controls";
import type { AffiliateRow } from "../types/affiliates.types";

export function AffiliatesGrid({
  links,
  onEdit,
  onDelete,
}: {
  links: AffiliateRow[];
  onEdit: (row: AffiliateRow) => void;
  onDelete: (id: number) => void;
}) {
  if (links.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-slate-400">Không có link affiliate</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
      {links.map((row) => (
        <article key={row.id} className="flex flex-col rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-sm font-semibold text-slate-900">{row.keyword}</div>
          <a
            href={row.url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 truncate text-xs text-indigo-600 hover:underline"
          >
            {row.url}
          </a>
          <p className="mt-2 line-clamp-3 text-xs text-slate-600">
            {row.comment_template || `Chưa có comment — ai_status=${row.ai_status || "—"}`}
          </p>
          {row.commission_rate != null ? (
            <div className="mt-2 text-right text-[11px] font-bold text-emerald-600">
              +{row.commission_rate}%
            </div>
          ) : null}
          <div className="mt-3 flex gap-1">
            <button type="button" className={ghostBtnClass} onClick={() => onEdit(row)}>
              Sửa
            </button>
            <button
              type="button"
              className={dangerBtnClass}
              onClick={() => {
                if (window.confirm(`Xóa ${row.keyword}?`)) onDelete(row.id);
              }}
            >
              Xóa
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
