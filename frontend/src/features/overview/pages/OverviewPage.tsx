import { Film, ListTodo, Orbit } from "lucide-react";
import { formatTs } from "@/shared/lib/time";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { ChannelTable } from "../components/ChannelTable";
import { QuickLink } from "../components/QuickLink";
import { StatCard } from "../components/StatCard";
import { useOverview } from "../hooks/useOverview";

export function OverviewPage() {
  const q = useOverview();
  // Bản build mới nhưng web chưa restart → API còn trả dạng cũ (không có `channels`).
  const stale = !!q.data && !Array.isArray(q.data.channels);
  const d = stale ? undefined : q.data;
  const scheduled = d?.channels.reduce((n, c) => n + c.scheduled, 0) ?? 0;
  const waiting = d?.channels.reduce((n, c) => n + c.ready_waiting, 0) ?? 0;
  const empty = d?.channels.filter((c) => c.posted_7d && !c.scheduled && !c.ready_waiting) ?? [];
  const done24 = d?.jobs_24h.DONE ?? 0;
  const failed24 = d?.jobs_24h.FAILED ?? 0;
  const newVideos = d ? Object.values(d.materials_7d).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Tổng quan" subtitle="Video → Buffer: kênh nào còn bài, cái gì đang lỗi" />
      <QueryBody
        isLoading={q.isLoading}
        isError={q.isError || (!q.isLoading && !d)}
        loadingText="Đang tải tổng quan…"
        errorText={
          stale
            ? "Giao diện đã cập nhật nhưng web chưa khởi động lại: chạy pm2 restart Web_Dashboard."
            : "Không tải được /api/admin/overview. Kiểm tra đăng nhập / FastAPI."
        }
      >
        {d ? (
          <>
            <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Bài đã hẹn"
                value={String(scheduled)}
                hint={empty.length ? `Hết bài: ${empty.map((c) => c.name).join(", ")}` : "mọi kênh còn bài"}
                tone={empty.length ? "bad" : "ok"}
              />
              <StatCard label="Kho chờ lên Buffer" value={String(waiting)} hint="video READY chưa hẹn giờ" />
              <StatCard
                label="Đưa lên Buffer 24h"
                value={`${done24} / ${done24 + failed24}`}
                hint={failed24 ? `${failed24} lần lỗi` : "không lỗi"}
                tone={failed24 ? "warn" : "ok"}
              />
              <StatCard
                label="Ổ đĩa trống"
                value={`${d.disk.free_gb} GB`}
                hint={`${newVideos} video mới 7 ngày · ngưỡng dừng ${d.disk.pause_below_gb} GB`}
                tone={d.disk.below_pause ? "bad" : d.disk.free_gb < 5 ? "warn" : "ok"}
              />
            </div>

            <Panel className="mt-4">
              <ChannelTable channels={d.channels} />
            </Panel>

            {d.failed_jobs.latest.length ? (
              <Panel className="mt-4 p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Lỗi gần nhất ({d.failed_jobs.count} tổng)
                </div>
                <ul className="mt-2 divide-y divide-slate-100 text-sm">
                  {d.failed_jobs.latest.map((j) => (
                    <li key={j.id} className="flex flex-wrap gap-x-3 py-1.5">
                      <span className="font-mono text-xs text-slate-400">#{j.id}</span>
                      <span className="font-medium">{j.channel || "—"}</span>
                      <span className="text-xs text-slate-400">{formatTs(j.finished_at)}</span>
                      <span className="basis-full truncate text-xs text-red-700" title={j.error}>
                        {j.error || "—"}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            ) : null}

            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <QuickLink to="/app/go/jobs" title="Lịch đăng" desc="Từng lần đưa video lên Buffer" icon={ListTodo} />
              <QuickLink to="/app/go/viral" title="Kho video" desc="Video đã tải / đã xử lý" icon={Film} />
              <a
                href="/buffer-cluster"
                className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-200"
              >
                <span className="rounded-lg bg-indigo-50 p-2 text-indigo-700">
                  <Orbit className="size-5" />
                </span>
                <div>
                  <div className="font-semibold text-slate-900">Cụm Buffer</div>
                  <div className="mt-1 text-xs text-slate-500">Key, suất, cooldown theo thời gian thực</div>
                </div>
              </a>
            </div>
          </>
        ) : null}
      </QueryBody>
    </div>
  );
}
