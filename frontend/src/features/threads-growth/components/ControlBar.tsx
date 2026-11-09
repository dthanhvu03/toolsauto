import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LogIn, Power } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { ghostBtnClass } from "@/shared/ui/controls";
import * as api from "../api/threadsGrowthApi";
import type { Overview, OwnPost } from "../api/threadsGrowthApi";

function Meter({ label, used, max }: { label: string; used: number; max: number }) {
  const ratio = max ? Math.min(used / max, 1) : 0;
  return (
    <div className="min-w-[9rem] flex-1">
      <div className="flex items-baseline justify-between text-xs text-slate-500">
        <span>{label}</span>
        <span>
          <b className="text-sm text-slate-800">{used}</b> / {max}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn("h-full rounded-full", ratio >= 1 ? "bg-amber-500" : "bg-indigo-500")}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
    </div>
  );
}

/** Cảnh báo tự suy ra từ dữ liệu sẵn có — chỉ nêu sự việc. */
function alertsOf(ov: Overview, own: OwnPost[]): string[] {
  const out: string[] = [];
  if (!ov.login.ready) out.push(`Chưa đăng nhập Threads (${ov.login.login_status}) — kéo khách không chạy được.`);
  let streak = 0;
  for (const p of own) {
    if (p.status !== "failed") break;
    streak += 1;
  }
  if (streak >= 2) out.push(`Bài riêng lỗi ${streak} lần liên tiếp: ${own[0].error_message ?? ""}`);
  for (const e of ov.customers?.errors ?? []) out.push(`Đọc khách từ bot lỗi: ${e}`);
  return out;
}

export function ControlBar({ ov, own }: { ov: Overview; own: OwnPost[] }) {
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const done = { onSuccess: () => { setErr(""); qc.invalidateQueries({ queryKey: ["growth"] }); }, onError: (e: Error) => setErr(e.message) };
  const toggle = useMutation({ mutationFn: () => api.toggleGrowth(!ov.enabled), ...done });
  const login = useMutation({ mutationFn: api.startLogin, ...done });
  const profile = ov.login.profile_path?.split("/").pop();
  const alerts = alertsOf(ov, own);
  const w = ov.worker;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <button
          type="button"
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending || (!ov.enabled && !ov.login.ready)}
          className={cn(
            "inline-flex h-10 items-center gap-2 rounded-xl px-4 text-sm font-semibold disabled:opacity-50",
            ov.enabled ? "bg-emerald-600 text-white hover:bg-emerald-700" : "bg-slate-200 text-slate-700 hover:bg-slate-300",
          )}
          title={ov.enabled ? "Bấm để tắt" : "Bấm để bật"}
        >
          <Power className="h-4 w-4" />
          {ov.enabled ? "Đang chạy" : "Đang tắt"}
        </button>

        <div className="text-sm">
          <div className={ov.login.ready ? "text-slate-700" : "font-medium text-amber-700"}>
            {ov.login.logging_in ? "Đang mở cửa sổ đăng nhập…" : ov.login.ready ? "Đã đăng nhập" : "Chưa đăng nhập"}
          </div>
          {profile && <div className="text-xs text-slate-400">profile {profile}</div>}
        </div>
        <button
          type="button"
          className={cn(ghostBtnClass, "inline-flex items-center gap-1")}
          disabled={login.isPending || ov.login.logging_in || ov.enabled}
          title={ov.enabled ? "Tắt kéo khách trước khi đăng nhập lại" : "Mở Chromium trên màn hình Windows"}
          onClick={() => login.mutate()}
        >
          <LogIn className="h-3.5 w-3.5" /> Đăng nhập lại
        </button>

        <div className="flex min-w-[18rem] flex-1 gap-4">
          <Meter label="Reply 24 giờ" used={ov.quota.posted_last_day} max={ov.limits.max_replies_per_day} />
          <Meter label="Reply 1 giờ" used={ov.quota.posted_last_hour} max={ov.limits.max_replies_per_hour} />
        </div>
      </div>

      <p className="mt-3 text-xs text-slate-500">
        Tự đăng khi điểm ≥ <b>{w.auto_post_min_relevance}</b> · bỏ dưới <b>{ov.limits.min_relevance}</b> · quét mỗi{" "}
        {w.scan_interval_min} phút · bài ≤ {w.max_post_age_hours}h{w.vietnamese_only && " · chỉ tiếng Việt"}
        {w.own_posts_enabled && w.own_post_times && ` · bài riêng lúc ${w.own_post_times}`}
        {w.followup_enabled && ` · trả lời người hỏi lại ≤ ${w.followup_max_per_day ?? "?"}/ngày`}
        {ov.enabled && !ov.quota.allowed && ov.quota.reason && (
          <span className="text-slate-700"> · reply kế tiếp: {ov.quota.reason}</span>
        )}
      </p>

      {alerts.length > 0 && (
        <ul className="mt-3 space-y-1">
          {alerts.map((a) => (
            <li key={a} className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> <span className="break-words">{a}</span>
            </li>
          ))}
        </ul>
      )}
      {ov.login.login_error && !ov.login.ready && (
        <p className="mt-2 text-xs text-amber-700">{ov.login.login_error.slice(0, 200)}</p>
      )}
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
    </section>
  );
}
