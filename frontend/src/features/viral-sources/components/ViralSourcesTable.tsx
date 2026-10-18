import { formatAgo } from "@/shared/lib/formatAgo";
import { dangerBtnClass, ghostBtnClass, selectClass } from "@/shared/ui/controls";
import type { BufferPage, ViralSourceRow } from "../types/viralSources.types";

function channelHref(row: ViralSourceRow) {
  if (row.url.startsWith("http")) return row.url;
  if (row.handle) return `https://www.tiktok.com/@${row.handle}`;
  return row.url;
}

export function ViralSourcesTable({
  items,
  pages,
  busyId,
  onToggle,
  onScan,
  onDelete,
  onSetPage,
}: {
  items: ViralSourceRow[];
  pages: BufferPage[];
  busyId?: number | null;
  onToggle: (id: number) => void;
  onScan: (id: number) => void;
  onDelete: (id: number) => void;
  onSetPage: (id: number, target_page: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[800px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">Nền tảng</th>
            <th className="px-3 py-2">Kênh</th>
            <th className="px-3 py-2">Page đích</th>
            <th className="px-3 py-2">Bật</th>
            <th className="px-3 py-2">Quét cuối</th>
            <th className="px-3 py-2">Tìm thấy</th>
            <th className="px-3 py-2">Thao tác</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? (
            <tr>
              <td colSpan={7} className="px-3 py-8 text-center text-slate-400">
                Không có nguồn
              </td>
            </tr>
          ) : (
            items.map((s) => (
              <tr key={s.id} className={s.enabled ? "hover:bg-slate-50/80" : "opacity-60"}>
                <td className="px-3 py-2 text-xs font-semibold">{s.platform}</td>
                <td className="max-w-[14rem] truncate px-3 py-2 text-xs">
                  <a href={channelHref(s)} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                    {s.handle ? `@${s.handle}` : s.url}
                  </a>
                </td>
                <td className="max-w-[16rem] px-3 py-2 text-xs text-slate-500">
                  <select
                    className={selectClass}
                    value={s.target_pages[0] ?? ""}
                    disabled={busyId === s.id}
                    onChange={(e) => onSetPage(s.id, e.target.value)}
                  >
                    <option value="">Chưa chọn</option>
                    {pages.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                        {p.slots ? ` · ${p.slots}` : ""}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-2 text-xs">{s.enabled ? "ON" : "OFF"}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{formatAgo(s.last_scanned_at)}</td>
                <td className="px-3 py-2 tabular-nums text-xs">{s.last_found ?? "—"}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    <button type="button" className={ghostBtnClass} disabled={busyId === s.id} onClick={() => onToggle(s.id)}>
                      {s.enabled ? "Tắt" : "Bật"}
                    </button>
                    <button type="button" className={ghostBtnClass} disabled={busyId === s.id} onClick={() => onScan(s.id)}>
                      Quét
                    </button>
                    <button
                      type="button"
                      className={dangerBtnClass}
                      disabled={busyId === s.id}
                      onClick={() => {
                        if (window.confirm(`Xóa nguồn #${s.id}?`)) onDelete(s.id);
                      }}
                    >
                      Xóa
                    </button>
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
