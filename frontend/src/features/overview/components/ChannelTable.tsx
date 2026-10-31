import { formatTs } from "@/shared/lib/time";
import type { ChannelOps } from "../types/overview.types";

/** Một dòng mỗi kênh: còn bao nhiêu bài đã hẹn, kho chờ, bao giờ hết bài. */
export function ChannelTable({ channels }: { channels: ChannelOps[] }) {
  const active = channels.filter((c) => c.scheduled || c.ready_waiting || c.posted_7d);
  const idle = channels.length - active.length;
  return (
    <div className="overflow-x-auto">
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
      {idle ? <p className="px-3 py-2 text-[11px] text-slate-400">{idle} kênh không hoạt động 7 ngày qua (ẩn).</p> : null}
    </div>
  );
}
