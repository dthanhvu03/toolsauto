import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Cpu, HardDrive, MemoryStick, Monitor, Server, Zap } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";
import { Panel } from "@/shared/ui/Panel";
import { fetchSyspanel } from "../api/syspanelApi";
import { useProcesses, useWindowsHost } from "../hooks/useMachine";
import type { ProcessesResponse, WindowsHostResponse } from "../types/syspanel.types";
import { Bar, gb, loadTone } from "./meters";

const RAM_ALERT = 85;
const DISK_FREE_ALERT = 10;

type Tone = "red" | "amber";
type Issue = { tone: Tone; text: string };

function Tile({
  icon,
  label,
  value,
  sub,
  pct,
  tone,
  hint,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  pct?: number;
  tone?: string;
  hint?: ReactNode;
}) {
  return (
    <Panel className="p-3.5">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
        {value} {sub ? <span className="text-sm font-normal text-slate-400">{sub}</span> : null}
      </div>
      {pct != null ? <Bar pct={pct} tone={tone ?? loadTone(pct)} /> : null}
      {hint ? <p className="mt-1.5 truncate text-xs text-slate-500">{hint}</p> : null}
    </Panel>
  );
}

/** Việc cần để mắt tới — rút từ số liệu đang có, không thêm ngưỡng nào ngoài RAM / ổ đĩa / tiến trình lỗi. */
function issues(p: ProcessesResponse | undefined, w: WindowsHostResponse | undefined): Issue[] {
  const out: Issue[] = [];
  if (w?.available && w.mem_total_mb) {
    const pct = ((w.mem_used_mb ?? 0) / w.mem_total_mb) * 100;
    if (pct > RAM_ALERT)
      out.push({ tone: "red", text: `RAM Windows còn ${gb(w.mem_total_mb - (w.mem_used_mb ?? 0))} — đóng bớt Chrome / Cursor nếu máy chậm` });
  }
  for (const d of w?.disks ?? []) {
    const free = (d.free_gb / d.total_gb) * 100;
    if (free < DISK_FREE_ALERT)
      out.push({ tone: "amber", text: `Ổ ${d.drive} còn ${d.free_gb.toLocaleString("vi-VN")} GB (${Math.round(free)}%)` });
  }
  if (p) {
    const wslPct = (p.machine.mem_used_mb / p.machine.mem_total_mb) * 100;
    if (wslPct > RAM_ALERT) out.push({ tone: "red", text: `RAM WSL đã dùng ${Math.round(wslPct)}%` });
    for (const a of p.apps.filter((x) => x.status === "errored"))
      out.push({ tone: "red", text: `${a.label} (${a.name}) đang lỗi — xem tab Tiến trình` });
    for (const s of (p.services ?? []).filter((x) => x.status !== "online"))
      out.push({ tone: "red", text: `Bot ${s.label} không chạy — ${s.manage ?? "xem tab Tiến trình"}` });
    if (p.error) out.push({ tone: "amber", text: p.error });
    if (p.services_error) out.push({ tone: "amber", text: p.services_error });
  }
  if (w && !w.available && w.error) out.push({ tone: "amber", text: w.error });
  return out;
}

/** Đầu trang Panel hệ thống: 6 ô số liệu Windows + WSL và danh sách «Cần chú ý». Luôn hiện, mọi tab. */
export function HealthOverview() {
  const p = useProcesses().data;
  const w = useWindowsHost().data;
  const legacy = useQuery({ queryKey: ["admin-syspanel"], queryFn: fetchSyspanel, refetchInterval: 15_000 }).data;

  const winOk = w?.available;
  const winMemPct = winOk && w.mem_total_mb ? ((w.mem_used_mb ?? 0) / w.mem_total_mb) * 100 : undefined;
  const worstDisk = winOk
    ? [...(w.disks ?? [])].sort((a, b) => a.free_gb / a.total_gb - b.free_gb / b.total_gb)[0]
    : undefined;
  const m = p?.machine;
  const wslMemPct = m ? (m.mem_used_mb / m.mem_total_mb) * 100 : undefined;
  const list = issues(p, w);
  const dash = <span className="text-slate-300">—</span>;

  return (
    <section className="mt-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Tile
          icon={<Monitor className="size-3.5" />}
          label="RAM Windows"
          value={winOk ? gb(w.mem_used_mb ?? 0) : dash}
          sub={winOk ? `/ ${gb(w.mem_total_mb ?? 0)}` : undefined}
          pct={winMemPct}
          hint={winOk && w.wsl_mem_mb != null ? `WSL giữ ${gb(w.wsl_mem_mb)}` : w?.available === false ? "không đọc được" : "đang đọc…"}
        />
        <Tile
          icon={<Cpu className="size-3.5" />}
          label="CPU Windows"
          value={winOk ? `${Math.round(w.cpu_pct ?? 0)}%` : dash}
          pct={winOk ? w.cpu_pct : undefined}
          tone={winOk && (w.cpu_pct ?? 0) > 85 ? "bg-red-500" : "bg-indigo-500"}
          hint={winOk ? `${w.cpus} luồng · cả máy, gồm WSL` : undefined}
        />
        <Tile
          icon={<HardDrive className="size-3.5" />}
          label="Ổ đĩa"
          value={worstDisk ? `${worstDisk.drive} còn ${worstDisk.free_gb.toLocaleString("vi-VN")} GB` : dash}
          pct={worstDisk ? (worstDisk.used_gb / worstDisk.total_gb) * 100 : undefined}
          tone={worstDisk && worstDisk.free_gb / worstDisk.total_gb < 0.1 ? "bg-red-500" : "bg-emerald-500"}
          hint={legacy ? `ổ đầy nhất · WSL còn ${Math.round(legacy.disk_total_gb - legacy.disk_used_gb)} GB` : "ổ đầy nhất"}
        />
        <Tile
          icon={<MemoryStick className="size-3.5" />}
          label="RAM WSL"
          value={m ? gb(m.mem_used_mb) : dash}
          sub={m ? `/ ${gb(m.mem_total_mb)}` : undefined}
          pct={wslMemPct}
          hint={p ? `${p.apps.filter((a) => a.status === "online").length}/${p.apps.length} app PM2 đang chạy` : undefined}
        />
        <Tile
          icon={<Server className="size-3.5" />}
          label="CPU WSL"
          value={m ? `${Math.round(m.cpu_pct)}%` : dash}
          pct={m?.cpu_pct}
          tone={m && m.cpu_pct > 85 ? "bg-red-500" : "bg-indigo-500"}
          hint={m ? `${m.cpus} nhân · render / Whisper chạy thì tăng vọt` : undefined}
        />
        <Tile
          icon={<Zap className="size-3.5" />}
          label="GPU"
          value={m?.gpu ? gb(m.gpu.mem_used_mb) : m ? <span className="text-sm font-normal text-slate-400">Không thấy GPU</span> : dash}
          sub={m?.gpu ? `/ ${gb(m.gpu.mem_total_mb)}` : undefined}
          pct={m?.gpu ? (m.gpu.mem_used_mb / m.gpu.mem_total_mb) * 100 : undefined}
          tone="bg-violet-500"
          hint={m?.gpu ? `${m.gpu.name} · đang dùng ${m.gpu.util_pct}%` : undefined}
        />
      </div>

      <Panel className="mt-3 px-4 py-3">
        {p && w ? (
          list.length ? (
            <ul className="space-y-1.5">
              {list.map((it) => (
                <li key={it.text} className="flex items-start gap-2 text-sm">
                  <AlertTriangle className={cn("mt-0.5 size-4 shrink-0", it.tone === "red" ? "text-red-600" : "text-amber-500")} />
                  <span className={it.tone === "red" ? "text-red-800" : "text-amber-900"}>{it.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="flex items-center gap-2 text-sm text-emerald-800">
              <CheckCircle2 className="size-4" /> Mọi thứ ổn — không có tiến trình lỗi, RAM và ổ đĩa còn dư.
            </p>
          )
        ) : (
          <p className="text-sm text-slate-400">Đang kiểm tra…</p>
        )}
      </Panel>
    </section>
  );
}
