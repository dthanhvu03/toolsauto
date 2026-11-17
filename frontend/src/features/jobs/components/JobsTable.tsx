import { formatTs } from "@/shared/lib/time";
import type { JobRow } from "../types/jobs.types";

const STATUS_STYLE: Record<string, string> = {
  DONE: "bg-emerald-100 text-emerald-800",
  FAILED: "bg-red-100 text-red-800",
  RUNNING: "bg-sky-100 text-sky-800",
};

/** Chỉ xem: xếp lại / huỷ lịch gọi Buffer API (tốn suất) nên vẫn làm qua Telegram. */
export function JobsTable({ rows }: { rows: JobRow[] }) {
  const now = Date.now() / 1000;
  return (
    <div>
      <ul aria-label="Các lượt đăng" className="divide-y divide-slate-100 md:hidden">
        {rows.map((j) => {
          const due = j.schedule_ts ?? 0;
          const upcoming = j.status === "DONE" && due > now;
          const text = (j.status === "FAILED" ? j.error_message : j.caption) || "";
          return <li key={j.id} className="min-w-0 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-xs text-slate-500">#{j.id}</span>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLE[j.status] ?? "bg-slate-100 text-slate-700"}`}>
                {j.status === "DONE" ? (upcoming ? "Đã hẹn" : "Đã tới giờ") : j.status === "FAILED" ? "Lỗi" : j.status}
              </span>
            </div>
            <h2 className="mt-2 break-words font-semibold [overflow-wrap:anywhere]">{j.channel || j.target_page || "Chưa có kênh"}</h2>
            <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm">
              <div><dt className="inline text-slate-500">Giờ lên: </dt><dd className="inline tabular-nums">{due > 0 ? formatTs(due) : "—"}</dd></div>
              <div><dt className="inline text-slate-500">Video: </dt><dd className="inline font-mono text-xs">{j.material_id ? `#${j.material_id}` : "—"}</dd></div>
            </dl>
            {text ? <details className={`mt-3 text-sm ${j.status === "FAILED" ? "text-red-700" : "text-slate-600"}`}>
              <summary className="flex min-h-11 cursor-pointer items-center rounded-lg bg-slate-50 px-3 font-medium">{j.status === "FAILED" ? "Xem lỗi" : "Xem caption"}</summary>
              <p className="mt-2 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{text}</p>
            </details> : null}
          </li>;
        })}
      </ul>
      {rows.length === 0 ? <p className="px-4 py-8 text-center text-sm text-slate-500 md:hidden">Không có lượt nào</p> : null}
      <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">ID</th>
            <th className="px-3 py-2">Trạng thái</th>
            <th className="px-3 py-2">Kênh</th>
            <th className="px-3 py-2">Giờ lên</th>
            <th className="px-3 py-2">Video</th>
            <th className="px-3 py-2">Caption / lỗi</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-8 text-center text-slate-400">
                Không có lượt nào
              </td>
            </tr>
          ) : (
            rows.map((j) => {
              const due = j.schedule_ts ?? 0;
              const upcoming = j.status === "DONE" && due > now;
              return (
                <tr key={j.id} className="hover:bg-slate-50/80">
                  <td className="px-3 py-2 font-mono text-xs">#{j.id}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[j.status] ?? "bg-slate-100 text-slate-700"}`}
                    >
                      {j.status === "DONE" ? (upcoming ? "Đã hẹn" : "Đã tới giờ") : j.status === "FAILED" ? "Lỗi" : j.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">{j.channel || j.target_page || "—"}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs tabular-nums text-slate-600">
                    {due > 0 ? formatTs(due) : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{j.material_id ? `#${j.material_id}` : "—"}</td>
                  <td
                    className={`max-w-[22rem] truncate px-3 py-2 text-xs ${j.status === "FAILED" ? "text-red-700" : "text-slate-600"}`}
                    title={j.status === "FAILED" ? j.error_message : j.caption}
                  >
                    {(j.status === "FAILED" ? j.error_message : j.caption) || "—"}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}
