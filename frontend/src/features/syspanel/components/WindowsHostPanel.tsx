import { HardDrive } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { Panel } from "@/shared/ui/Panel";
import { useWindowsHost } from "../hooks/useMachine";
import type { WindowsDisk } from "../types/syspanel.types";
import { Bar, ram, uptime } from "./meters";

const WSL_NAMES = new Set(["vmmemwsl", "vmmem"]);

function DiskRow({ d }: { d: WindowsDisk }) {
  const pct = (d.used_gb / d.total_gb) * 100;
  const freePct = 100 - pct;
  return (
    <li className="py-1.5">
      <div className="flex items-baseline justify-between gap-2 text-sm tabular-nums">
        <span className="font-semibold text-slate-700">
          {d.drive} {d.label ? <span className="font-normal text-slate-400">{d.label}</span> : null}
        </span>
        <span className={cn("text-xs", freePct < 10 ? "font-semibold text-red-700" : "text-slate-500")}>
          còn {d.free_gb.toLocaleString("vi-VN")} / {d.total_gb.toLocaleString("vi-VN")} GB
        </span>
      </div>
      <Bar pct={pct} tone={freePct < 10 ? "bg-red-500" : freePct < 20 ? "bg-amber-500" : "bg-emerald-500"} />
    </li>
  );
}

/**
 * Tab «Máy Windows»: chương trình tốn RAM nhất (gộp theo tên) + từng ổ đĩa. Chỉ xem.
 * RAM / CPU tổng nằm ở ô tóm tắt đầu trang (cùng query, không hỏi server 2 lần).
 */
export function WindowsHostPanel() {
  const q = useWindowsHost();
  const w = q.data;
  if (!w) {
    return q.isError ? (
      <p className="mt-4 text-sm text-red-700">Không tải được số liệu máy Windows.</p>
    ) : (
      <p className="mt-4 text-sm text-slate-400">Đang đọc số liệu máy Windows…</p>
    );
  }
  if (!w.available) return <p className="mt-4 text-sm text-slate-500">Máy Windows: {w.error}</p>;

  const top = w.top ?? [];
  const maxMb = Math.max(1, ...top.map((p) => p.mem_mb));
  return (
    <section className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <span className="text-sm font-semibold">Chương trình tốn RAM nhất (Windows)</span>
          <span className="text-xs text-slate-400">Chỉ xem · gộp theo tên · CPU tính trên cả máy · tự cập nhật 10 giây</span>
        </div>
        <div className="hidden grid-cols-[minmax(0,1.6fr)_5rem_minmax(0,1fr)] gap-x-4 px-4 pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400 md:grid">
          <span>Chương trình</span>
          <span>CPU</span>
          <span>RAM</span>
        </div>
        <ul className="divide-y divide-slate-100">
          {top.map((p) => {
            const isWsl = WSL_NAMES.has(p.name.toLowerCase());
            return (
              <li
                key={p.name}
                className={cn(
                  "grid gap-x-4 gap-y-1 px-4 py-2.5 md:grid-cols-[minmax(0,1.6fr)_5rem_minmax(0,1fr)] md:items-center",
                  isWsl && "bg-indigo-50/60",
                )}
              >
                <div className="min-w-0">
                  <span className="font-semibold text-slate-800">{p.label}</span>
                  <span className="ml-2 font-mono text-[11px] text-slate-400">
                    {p.name}
                    {p.count > 1 ? ` ×${p.count}` : ""}
                  </span>
                </div>
                <div
                  className="text-sm tabular-nums text-slate-700"
                  title={isWsl ? "CPU của WSL xem ở ô «CPU WSL» đầu trang — Windows không tính vào tiến trình này" : undefined}
                >
                  <span className="text-xs text-slate-400 md:hidden">CPU </span>
                  {isWsl || p.cpu_pct == null ? "—" : `${p.cpu_pct}%`}
                </div>
                <div className="min-w-0">
                  <div className="text-sm tabular-nums text-slate-700">
                    <span className="text-xs text-slate-400 md:hidden">RAM </span>
                    {ram(p.mem_mb)}
                  </div>
                  <Bar pct={(p.mem_mb / maxMb) * 100} tone={p.mem_mb >= 1024 ? "bg-amber-500" : "bg-indigo-400"} />
                </div>
              </li>
            );
          })}
        </ul>
      </Panel>

      <div className="space-y-4">
        <Panel className="p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            <HardDrive className="size-4" /> Ổ đĩa Windows
          </div>
          <ul className="mt-1">
            {(w.disks ?? []).map((d) => (
              <DiskRow key={d.drive} d={d} />
            ))}
          </ul>
        </Panel>
        <p className="px-1 text-xs text-slate-500">
          {w.cpu_name} · bật {uptime(w.uptime_s)} · {w.process_count} tiến trình · cập nhật {w.age_s} giây trước
        </p>
      </div>
    </section>
  );
}
