import { formatTs } from "@/shared/lib/time";
import type { ChannelOps } from "../types/overview.types";

/** Một dòng mỗi kênh: còn bao nhiêu bài đã hẹn, kho chờ, bao giờ hết bài. */
export function ChannelTable({ channels }: { channels: ChannelOps[] }) {
  const active = channels.filter((c) => c.scheduled || c.ready_waiting || c.posted_7d);
  const idle = channels.length - active.length;
  return (
    <div>
      <ul aria-label="Tình trạng các kênh" className="divide-y divide-slate-100 md:hidden">
        {active.map((c) => {
          const empty = c.scheduled === 0 && c.ready_waiting === 0;
          const low = !empty && c.scheduled <= 2 && c.ready_waiting === 0;
          return <li key={c.id} className="min-w-0 p-4">
            <div className="flex items-start justify-between gap-3">
              <h3 className="min-w-0 break-words font-semibold text-slate-900 [overflow-wrap:anywhere]">{c.name}</h3>
              <span className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium ${empty ? "bg-red-50 text-red-700" : low ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-700"}`}>
                {empty ? "Hết bài" : low ? "Sắp hết bài" : "Còn bài"}
              </span>
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
              <div><dt className="text-xs text-slate-500">Đã hẹn</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{c.scheduled}</dd></div>
              <div><dt className="text-xs text-slate-500">Kho chờ</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{c.ready_waiting}</dd></div>
              <div><dt className="text-xs text-slate-500">Lên 7 ngày</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{c.posted_7d}</dd></div>
            </dl>
            <p className="mt-3 text-xs text-slate-500">Bài kế tiếp: <span className="font-medium text-slate-700">{c.next_at ? formatTs(c.next_at) : "Chưa có lịch"}</span></p>
          </li>;
        })}
      </ul>
      <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">Kênh</th>
            <th className="px-3 py-2 text-right">Đã hẹn</th>
            <th className="px-3 py-2">Bài kế tiếp</th>
            <th className="px-3 py-2 text-right">Kho chờ</th>
            <th className="px-3 py-2 text-right">Lên 7 ngày</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {active.map((c) => {
            const empty = c.scheduled === 0 && c.ready_waiting === 0;
            const low = !empty && c.scheduled <= 2 && c.ready_waiting === 0;
            return (
              <tr key={c.id} className={empty ? "bg-red-50/60" : low ? "bg-amber-50/60" : undefined}>
                <td className="px-3 py-2 font-medium text-slate-800">{c.name}</td>
                <td className="px-3 py-2 text-right tabular-nums">{c.scheduled}</td>
                <td className="whitespace-nowrap px-3 py-2 text-xs tabular-nums text-slate-600">
                  {c.next_at ? formatTs(c.next_at) : empty ? <span className="font-semibold text-red-700">Hết bài</span> : "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{c.ready_waiting}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-500">{c.posted_7d}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      {!active.length ? <p className="px-4 py-8 text-center text-sm text-slate-500">Chưa có kênh hoạt động trong 7 ngày qua.</p> : null}
      {idle ? <p className="px-3 py-2 text-[11px] text-slate-400">{idle} kênh không hoạt động 7 ngày qua (ẩn).</p> : null}
    </div>
  );
}
