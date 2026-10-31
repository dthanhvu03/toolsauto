import { AlertTriangle, Check, CircleDashed, Clock, ExternalLink, Loader2, Minus, RotateCw, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/shared/lib/cn";
import { useJobs } from "../hooks/useStudio";
import { mmss } from "../lib/status";
import type { Job, JobStep } from "../types/studio.types";

const STATE: Record<Job["state"], { label: string; tone: string }> = {
  running: { label: "Đang chạy", tone: "border-sky-200 bg-sky-50 text-sky-900" },
  queued: { label: "Đang chờ", tone: "border-slate-200 bg-slate-50 text-slate-700" },
  retry: { label: "Sẽ thử lại", tone: "border-amber-200 bg-amber-50 text-amber-900" },
  failed: { label: "Lỗi", tone: "border-red-200 bg-red-50 text-red-800" },
  review: { label: "Chờ duyệt", tone: "border-emerald-200 bg-emerald-50 text-emerald-900" },
  done: { label: "Xong", tone: "border-emerald-200 bg-emerald-50 text-emerald-900" },
  stopped: { label: "Dừng", tone: "border-slate-200 bg-slate-50 text-slate-600" },
};

const CHIP: Record<JobStep["status"], string> = {
  done: "border-emerald-200 bg-emerald-50 text-emerald-800",
  skipped: "border-slate-200 bg-white text-slate-400 line-through decoration-slate-300",
  running: "border-sky-300 bg-sky-100 text-sky-900 font-semibold",
  queued: "border-slate-300 bg-white text-slate-600",
  retry: "border-amber-300 bg-amber-50 text-amber-900",
  failed: "border-red-300 bg-red-50 text-red-800 font-semibold",
  waiting: "border-dashed border-emerald-300 bg-white text-emerald-700",
  pending: "border-dashed border-slate-200 bg-white text-slate-400",
  cancelled: "border-slate-300 bg-slate-100 text-slate-500",
  warn: "border-amber-300 bg-amber-50 text-amber-900 font-semibold",
};

function StepIcon({ s }: { s: JobStep["status"] }) {
  const c = "size-3.5 shrink-0";
  if (s === "done") return <Check className={c} />;
  if (s === "running") return <Loader2 className={`${c} animate-spin`} />;
  if (s === "failed" || s === "cancelled") return <X className={c} />;
  if (s === "warn") return <AlertTriangle className={c} />;
  if (s === "retry") return <RotateCw className={c} />;
  if (s === "skipped") return <Minus className={c} />;
  if (s === "queued") return <Clock className={c} />;
  return <CircleDashed className={c} />;
}

/** Đồng hồ chạy theo giờ máy chủ (``skew`` = giờ server − giờ trình duyệt lúc hỏi). */
function useClock(on: boolean, skew: number) {
  const [now, setNow] = useState(() => Date.now() / 1000 + skew);
  useEffect(() => {
    setNow(Date.now() / 1000 + skew);
    if (!on) return;
    const t = window.setInterval(() => setNow(Date.now() / 1000 + skew), 1000);
    return () => window.clearInterval(t);
  }, [on, skew]);
  return now;
}

function stepTitle(st: JobStep): string {
  const took = st.started_at && st.finished_at ? ` · ${mmss(st.finished_at - st.started_at)}` : "";
  const why = { skipped: "bỏ qua", waiting: "chờ anh duyệt", pending: "chưa tới" }[st.status as string];
  return [st.label + took, st.note || why].filter(Boolean).join(" — ");
}

function JobRow({ job, now }: { job: Job; now: number }) {
  const cur = job.steps.find((s) => s.stage === job.current);
  const running = job.state === "running" && cur?.started_at;
  const notes = job.steps.filter((s) => s.status === "done" && s.note).map((s) => `${s.label}: ${s.note}`);
  const st = STATE[job.state];
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("rounded-md border px-1.5 py-0.5 text-[11px] font-semibold", st.tone)}>{st.label}</span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{job.source}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800" title={job.title}>
          {job.title}
        </span>
        {job.url ? (
          <a href={job.url} target="_blank" rel="noreferrer" className="text-slate-400 hover:text-slate-700" title="Mở link gốc">
            <ExternalLink className="size-4" />
          </a>
        ) : null}
        {job.project_id ? (
          <Link to={`/app/go/studio/${job.project_id}`} className="text-xs font-medium text-indigo-700 hover:underline">
            {job.state === "review" ? "Xem & duyệt" : "Mở"} dự án #{job.project_id} →
          </Link>
        ) : null}
      </div>
      <ol className="mt-2 flex flex-wrap items-center gap-1">
        {job.steps.map((s, i) => (
          <li key={s.stage} className="flex items-center gap-1">
            {i > 0 ? <span className="h-px w-2 bg-slate-200" /> : null}
            <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]", CHIP[s.status])} title={stepTitle(s)}>
              <StepIcon s={s.status} />
              {s.label}
              {s.status === "running" && s.started_at ? <span className="tabular-nums">{mmss(now - s.started_at)}</span> : null}
            </span>
          </li>
        ))}
      </ol>
      <p
        className={cn(
          "mt-2 flex items-start gap-1.5 text-xs",
          job.state === "failed" ? "text-red-700" : job.state === "retry" ? "text-amber-800" : "text-slate-600"
        )}
      >
        {job.state === "failed" || job.state === "retry" ? <AlertTriangle className="mt-px size-3.5 shrink-0" /> : null}
        <span>
          {job.summary}
          {running ? <span className="tabular-nums"> · {mmss(now - (cur?.started_at ?? now))}</span> : null}
          {job.current === "review" && job.state === "running" ? " — mạng đẩy chậm thì video dài có thể mất vài phút; các bước khác vẫn chờ sau nó." : ""}
        </span>
      </p>
      {notes.length ? <p className="mt-1 truncate text-[11px] text-slate-400" title={notes.join("\n")}>{notes.join(" · ")}</p> : null}
    </li>
  );
}

/**
 * PLAN-114 — tiến trình từng video: bước nào xong / đang chạy (kèm đồng hồ) / chờ / lỗi gì. ``ids``: chỉ các việc này
 * (trang «Lấy từ TikTok» theo dõi lô vừa gửi); bỏ trống: mọi việc đang chạy + xong / lỗi 2 giờ qua.
 * ``hideDone``: ẩn việc đã xong / chờ duyệt / dự án anh đã bỏ (bảng Studio — các video đó đã có thẻ ngay bên dưới).
 */
export function JobsPanel({
  ids,
  title = "Tiến trình",
  max = 6,
  hideDone = false,
}: {
  ids?: number[];
  title?: string;
  max?: number;
  hideDone?: boolean;
}) {
  const q = useJobs(ids);
  const [all, setAll] = useState(false);
  const [skew, setSkew] = useState(0);
  const d = q.data;
  useEffect(() => {
    if (d?.now) setSkew(d.now - Date.now() / 1000);
  }, [d?.now, q.dataUpdatedAt]);
  const now = useClock((d?.active ?? 0) > 0, skew);
  const list = (d?.jobs ?? []).filter(
    (j) => !hideDone || (j.state !== "done" && j.state !== "review" && j.project_status !== "REJECTED")
  );
  if (!d || list.length === 0) return null;
  const shown = all ? list : list.slice(0, max);
  return (
    <section className="mt-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
        {title}
        {d.active ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-800">
            <span className="size-1.5 animate-pulse rounded-full bg-sky-500" /> {d.active} đang chạy · tự cập nhật
          </span>
        ) : null}
      </h2>
      <ul className="mt-2 flex flex-col gap-2">
        {shown.map((j) => (
          <JobRow key={j.id} job={j} now={now} />
        ))}
      </ul>
      {list.length > max ? (
        <button type="button" className="mt-2 text-xs text-indigo-700 hover:underline" onClick={() => setAll((v) => !v)}>
          {all ? "Thu gọn" : `Xem thêm ${list.length - max} việc`}
        </button>
      ) : null}
    </section>
  );
}
