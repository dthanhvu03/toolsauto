import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, MemoryStick, Power, RotateCw } from "lucide-react";
import { useState } from "react";
import { cn } from "@/shared/lib/cn";
import { ghostBtnClass } from "@/shared/ui/controls";
import { Panel } from "@/shared/ui/Panel";
import { Toast } from "@/shared/ui/Toast";
import { fetchProcesses, processAction } from "../api/syspanelApi";
import type { ProcessAction, ProcessApp } from "../types/syspanel.types";

const STATUS: Record<string, { label: string; tone: string }> = {
  online: { label: "Đang chạy", tone: "bg-emerald-100 text-emerald-800" },
  stopped: { label: "Đã tắt", tone: "bg-slate-200 text-slate-600" },
  stopping: { label: "Đang tắt…", tone: "bg-amber-100 text-amber-900" },
  launching: { label: "Đang bật…", tone: "bg-sky-100 text-sky-800" },
  errored: { label: "Lỗi", tone: "bg-red-100 text-red-800" },
};

const gb = (mb: number) => `${(mb / 1024).toFixed(1).replace(".", ",")} GB`;
const ram = (mb: number) => (mb >= 1024 ? gb(mb) : `${mb} MB`);

function uptime(s: number | null): string {
  if (s == null) return "—";
  if (s < 60) return `${s} giây`;
  if (s < 3600) return `${Math.floor(s / 60)} phút`;
  if (s < 86400) return `${Math.floor(s / 3600)} giờ ${Math.floor((s % 3600) / 60)} phút`;
  return `${Math.floor(s / 86400)} ngày`;
}

function Bar({ pct, tone = "bg-indigo-500" }: { pct: number; tone?: string }) {
  return (
    <span className="block h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <span className={cn("block h-full rounded-full", tone)} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </span>
  );
}

function AppRow({
  a,
  totalMb,
  pending,
  onAct,
}: {
  a: ProcessApp;
  totalMb: number;
  pending: ProcessAction | undefined;
  onAct: (a: ProcessApp, action: ProcessAction) => void;
}) {
  const st = STATUS[a.status] ?? { label: a.status, tone: "bg-slate-100 text-slate-600" };
  const busy = !!pending;
  return (
    <li className="grid gap-x-4 gap-y-2 px-4 py-3 md:grid-cols-[minmax(0,1.6fr)_7rem_4rem_minmax(0,1fr)_8rem_13rem] md:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-slate-800">{a.label}</span>
          <span className="font-mono text-[11px] text-slate-400">{a.name}</span>
        </div>
        {a.role ? <p className="text-xs text-slate-500">{a.role}</p> : null}
      </div>
      <div>
        <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-semibold", st.tone)}>
          {pending === "stop" ? "Đang tắt…" : pending === "start" ? "Đang bật…" : pending === "restart" ? "Đang khởi động lại…" : st.label}
        </span>
      </div>
      <div className="text-sm tabular-nums text-slate-700" title="CPU (100% = 1 nhân)">
        <span className="text-xs text-slate-400 md:hidden">CPU </span>
        {a.status === "online" ? `${a.cpu}%` : "—"}
      </div>
      <div className="min-w-0" title={`${a.mem_mb} MB`}>
        <div className="flex items-baseline justify-between text-sm tabular-nums text-slate-700">
          <span>
            <span className="text-xs text-slate-400 md:hidden">RAM </span>
            {a.status === "online" ? ram(a.mem_mb) : "—"}
          </span>
        </div>
        {a.status === "online" ? <Bar pct={(a.mem_mb / totalMb) * 100} tone={a.mem_mb >= 1024 ? "bg-amber-500" : "bg-indigo-400"} /> : null}
      </div>
      <div className="text-xs text-slate-500">
        {a.status === "online" ? `chạy ${uptime(a.uptime_s)}` : ""}
        {a.restarts ? <span className="block text-slate-400">khởi động lại {a.restarts} lần</span> : null}
      </div>
      <div className="flex gap-1.5 md:justify-end">
        {a.can_stop ? (
          <button type="button" className={`${ghostBtnClass} inline-flex items-center gap-1 text-red-700`} disabled={busy} onClick={() => onAct(a, "stop")}>
            <Power className="size-3.5" /> Tắt
          </button>
        ) : null}
        {a.can_start ? (
          <button type="button" className={`${ghostBtnClass} inline-flex items-center gap-1 border-emerald-300 text-emerald-800`} disabled={busy} onClick={() => onAct(a, "start")}>
            <Power className="size-3.5" /> Bật
          </button>
        ) : null}
        {a.can_restart ? (
          <button type="button" className={`${ghostBtnClass} inline-flex items-center gap-1`} disabled={busy} onClick={() => onAct(a, "restart")} title="Khởi động lại">
            <RotateCw className="size-3.5" /> Khởi động lại
          </button>
        ) : null}
      </div>
    </li>
  );
}

/**
 * PLAN-115 — bảng tiến trình PM2: RAM / CPU từng app + bật / tắt / khởi động lại. Lệnh chạy tách khỏi web rồi `pm2 save`
 * (máy khởi động lại vẫn giữ lựa chọn). Hỏi lại trước khi tắt (kèm «tắt thì sao»). Tự hỏi lại 5 giây, 2 giây khi đang chờ lệnh.
 */
export function ProcessTable() {
  const qc = useQueryClient();
  const [pending, setPending] = useState<Record<string, ProcessAction>>({});
  const [toast, setToast] = useState({ text: "", seq: 0 });
  const say = (text: string) => setToast((t) => ({ text, seq: t.seq + 1 }));
  const waiting = Object.keys(pending).length > 0;
  const q = useQuery({
    queryKey: ["admin-processes"],
    queryFn: fetchProcesses,
    refetchInterval: waiting ? 2_000 : 5_000,
  });
  const d = q.data;
  // lệnh đã có kết quả (trạng thái đổi) → bỏ «đang…»; chờ quá 60 giây cũng bỏ để nút bấm lại được
  const settle = (name: string, action: ProcessAction, startedAt: number) => {
    const check = (n: number) =>
      window.setTimeout(async () => {
        const fresh = await qc.fetchQuery({ queryKey: ["admin-processes"], queryFn: fetchProcesses }).catch(() => null);
        const app = fresh?.apps.find((x) => x.name === name);
        const done =
          !app ||
          (action === "stop" && app.status === "stopped") ||
          (action === "start" && app.status === "online") ||
          (action === "restart" && app.status === "online" && (app.uptime_s ?? 1e9) < (Date.now() - startedAt) / 1000 + 5);
        if (done || n >= 30) {
          setPending((p) => {
            const next = { ...p };
            delete next[name];
            return next;
          });
          if (!done) say(`${name}: chưa thấy đổi trạng thái sau 60 giây — xem lại bảng hoặc nhật ký.`);
        } else check(n + 1);
      }, 2000);
    check(0);
  };
  const mut = useMutation({
    mutationFn: ({ a, action }: { a: ProcessApp; action: ProcessAction }) => processAction(a.name, action),
    onSuccess: (r, { a, action }) => {
      say(r.message);
      setPending((p) => ({ ...p, [a.name]: action }));
      settle(a.name, action, Date.now());
    },
    onError: (e: Error) => say(`Lỗi: ${e.message}`),
  });
  const onAct = (a: ProcessApp, action: ProcessAction) => {
    if (action === "stop" && !window.confirm(`Tắt «${a.label}»?\n\nTắt thì: ${a.if_stopped || "app ngừng chạy"}.`)) return;
    if (action === "restart" && a.name === "Web_Dashboard" && !window.confirm("Khởi động lại web? Trang mất kết nối vài giây.")) return;
    mut.mutate({ a, action });
  };

  if (!d) return q.isError ? <p className="mt-4 text-sm text-red-700">Không tải được bảng tiến trình.</p> : null;
  const m = d.machine;
  const online = d.apps.filter((a) => a.status === "online");
  const appsMb = online.reduce((s, a) => s + a.mem_mb, 0);
  const top = [...online].sort((x, y) => y.mem_mb - x.mem_mb)[0];
  const memPct = (m.mem_used_mb / m.mem_total_mb) * 100;
  return (
    <section className="mt-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Panel className="p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            <MemoryStick className="size-4" /> RAM (WSL)
          </div>
          <div className="mt-1 text-xl font-semibold tabular-nums">
            {gb(m.mem_used_mb)} <span className="text-sm font-normal text-slate-400">/ {gb(m.mem_total_mb)}</span>
          </div>
          <Bar pct={memPct} tone={memPct > 85 ? "bg-red-500" : memPct > 70 ? "bg-amber-500" : "bg-emerald-500"} />
          <p className="mt-1.5 text-xs text-slate-500">
            Các app dưới đây giữ {gb(appsMb)}
            {top ? (
              <>
                {" "}
                · nhiều nhất: <b>{top.label}</b> {ram(top.mem_mb)}
              </>
            ) : null}
          </p>
        </Panel>
        <Panel className="p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            <Cpu className="size-4" /> CPU
          </div>
          <div className="mt-1 text-xl font-semibold tabular-nums">{Math.round(m.cpu_pct)}%</div>
          <Bar pct={m.cpu_pct} tone={m.cpu_pct > 85 ? "bg-red-500" : "bg-indigo-500"} />
          <p className="mt-1.5 text-xs text-slate-500">{m.cpus} nhân · render / Whisper chạy thì tăng vọt là bình thường</p>
        </Panel>
        <Panel className="p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">GPU</div>
          {m.gpu ? (
            <>
              <div className="mt-1 text-xl font-semibold tabular-nums">
                {gb(m.gpu.mem_used_mb)} <span className="text-sm font-normal text-slate-400">/ {gb(m.gpu.mem_total_mb)}</span>
              </div>
              <Bar pct={(m.gpu.mem_used_mb / m.gpu.mem_total_mb) * 100} tone="bg-violet-500" />
              <p className="mt-1.5 text-xs text-slate-500">
                {m.gpu.name} · đang dùng {m.gpu.util_pct}%
              </p>
            </>
          ) : (
            <p className="mt-2 text-sm text-slate-400">Không thấy GPU</p>
          )}
        </Panel>
      </div>

      <Panel className="mt-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <span className="text-sm font-semibold">Tiến trình (PM2)</span>
          <span className="text-xs text-slate-400">Bật / tắt được giữ lại khi khởi động lại máy · tự cập nhật 5 giây</span>
        </div>
        {d.error ? <p className="px-4 py-3 text-sm text-red-700">{d.error}</p> : null}
        <div className="hidden grid-cols-[minmax(0,1.6fr)_7rem_4rem_minmax(0,1fr)_8rem_13rem] gap-x-4 px-4 pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400 md:grid">
          <span>App</span>
          <span>Trạng thái</span>
          <span>CPU</span>
          <span>RAM</span>
          <span>Thời gian</span>
          <span />
        </div>
        <ul className="divide-y divide-slate-100">
          {d.apps.map((a) => (
            <AppRow key={a.name} a={a} totalMb={m.mem_total_mb} pending={pending[a.name]} onAct={onAct} />
          ))}
        </ul>
      </Panel>
      <Toast text={toast.text} seq={toast.seq} />
    </section>
  );
}
