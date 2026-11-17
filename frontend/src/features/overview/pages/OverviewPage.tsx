import { Film, ListTodo, Orbit } from "lucide-react";
import { formatTs } from "@/shared/lib/time";
import { ScreenSettingsButton } from "@/features/settings/components/ScreenSettingsButton";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { ChannelTable } from "../components/ChannelTable";
import { QuickLink } from "../components/QuickLink";
import { StatCard } from "../components/StatCard";
import { useOverview } from "../hooks/useOverview";
import { useQuery } from "@tanstack/react-query";
import { fetchBotUsers } from "@/features/bot-users/api/botUsersApi";
import { fetchProcesses } from "@/features/syspanel/api/syspanelApi";
import { ExecutivePanels } from "../components/ExecutivePanels";

export function OverviewPage() {
  const q = useOverview();
  const growth = useQuery({
    queryKey: ["bot-users-summary"],
    queryFn: () => fetchBotUsers("", "", 1, 25, true),
    refetchInterval: 60_000,
  });
  const runtime = useQuery({
    queryKey: ["admin-processes"],
    queryFn: fetchProcesses,
    refetchInterval: 30_000,
  });
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
      <PageHeader
        actions={<ScreenSettingsButton screen="overview" />} title="Điều hành hệ thống" subtitle="Dịch vụ đang chạy · tăng trưởng khách · vận hành nội dung" />
      <ExecutivePanels />
            <section aria-labelledby="runtime-heading" className="mt-5">
              <div className="mb-2 flex items-center justify-between gap-3">
                <h2 id="runtime-heading" className="font-semibold text-slate-900">Sức khỏe dịch vụ</h2>
                <a href="/app/go/syspanel" className="text-sm font-medium text-indigo-700">Chi tiết</a>
              </div>
              {runtime.data?.error ? <p className="text-sm text-amber-800">Chưa lấy được trạng thái tiến trình: {runtime.data.error}</p> : null}
              {runtime.isError ? <p className="text-sm text-amber-800">Không tải được trạng thái dịch vụ.</p> : null}
              {runtime.data ? (() => {
                const services = [...runtime.data.apps, ...(runtime.data.services ?? [])];
                const monitored = services.filter((service) => !(service.name === "DB_Backup" && service.status === "stopped"));
                const running = monitored.filter((service) => service.status === "online").length;
                const down = monitored.filter((service) => service.status !== "online");
                return <Panel className="p-4">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className={`text-2xl font-semibold tabular-nums ${down.length ? "text-amber-800" : "text-emerald-800"}`}>
                      {running}/{monitored.length}
                    </span>
                    <span className="text-sm text-slate-600">dịch vụ online · sao lưu DB dừng theo lịch là bình thường</span>
                    {down.length ? <span className="text-sm text-amber-800">Cần xem: {down.map((service) => service.label || service.name).join(", ")}</span> : null}
                  </div>
                  {runtime.data.services_error ? <p className="mt-2 text-xs text-amber-800">Bot/systemd: {runtime.data.services_error}</p> : null}
                  {!services.length ? <p className="text-sm text-slate-500">Chưa có dữ liệu tiến trình.</p> : null}
                </Panel>;
              })() : <Panel className="p-4 text-sm text-slate-500">{runtime.isLoading ? "Đang đọc trạng thái dịch vụ…" : "Trạng thái dịch vụ chưa khả dụng."}</Panel>}
            </section>

            <section aria-labelledby="growth-heading" className="mt-5">
              <div className="mb-2 flex items-center justify-between gap-3">
                <h2 id="growth-heading" className="font-semibold text-slate-900">Tăng trưởng theo bot</h2>
                <a href="/app/go/bot-users" className="text-sm font-medium text-indigo-700">Khách các bot</a>
              </div>
              {growth.isError ? <Panel className="p-4 text-sm text-amber-800">Không tải được báo cáo Cashbot / AI Pass Store.</Panel> : null}
              {growth.data?.errors.map((error) => <p key={error} className="mb-2 text-sm text-amber-800">{error}</p>)}
              {growth.data ? <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {growth.data.bots.map((bot) => <Panel key={bot.bot} className="min-w-0 p-4">
                  <h3 className="font-semibold text-slate-900">{bot.label}</h3>
                  {bot.available === false ? <p className="mt-3 text-sm text-amber-800">Chưa đọc được dữ liệu bot này.</p> : <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-3 text-sm">
                    <div><dt className="text-xs text-slate-500">Tổng khách</dt><dd className="mt-0.5 font-semibold tabular-nums">{bot.total.toLocaleString("vi-VN")}</dd></div>
                    <div><dt className="text-xs text-slate-500">Mới 7 ngày</dt><dd className="mt-0.5 font-semibold tabular-nums">{bot.new_7d.toLocaleString("vi-VN")}</dd></div>
                    <div><dt className="text-xs text-slate-500">Hoạt động 7 ngày</dt><dd className="mt-0.5 font-semibold tabular-nums">{bot.active_7d.toLocaleString("vi-VN")}</dd></div>
                    <div><dt className="text-xs text-slate-500">Có đơn</dt><dd className="mt-0.5 font-semibold tabular-nums">{bot.buyers.toLocaleString("vi-VN")}</dd></div>
                  </dl>}
                </Panel>)}
                <p className="sm:col-span-2 xl:col-span-3 text-xs text-slate-500">Mỗi bot đếm khách riêng; một người dùng nhiều bot xuất hiện ở từng bot. «Có đơn» theo định nghĩa riêng của Cashbot và AI Pass Store.</p>
              </div> : <Panel className="p-4 text-sm text-slate-500">{growth.isLoading ? "Đang tổng hợp khách các bot…" : "Báo cáo tăng trưởng chưa khả dụng."}</Panel>}
            </section>

      <QueryBody
        isLoading={q.isLoading}
        isError={q.isError || (!q.isLoading && !d)}
        loadingText="Đang tải vận hành Buffer…"
        errorText={stale ? "API Buffer chưa tương thích bản giao diện." : "Không tải được vận hành Buffer. Các khối khác vẫn hoạt động độc lập."}
      >
        {d ? (
            <section aria-labelledby="buffer-heading" className="mt-6">
              <h2 id="buffer-heading" className="font-semibold text-slate-900">Vận hành nội dung · Buffer</h2>
            <div className="mt-5 grid grid-cols-2 gap-3 [overflow-wrap:anywhere] lg:grid-cols-4">
              <StatCard
                label="Bài đã hẹn"
                value={String(scheduled)}
                hint={empty.length ? `${empty.length} kênh hết bài · xem bên dưới` : "mọi kênh còn bài"}
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

            <div className="mt-6 flex items-center justify-between gap-3">
              <h2 className="font-semibold text-slate-900">Tình trạng các kênh</h2>
              <span className="text-xs text-slate-500">{d.channels.length} kênh</span>
            </div>
            <Panel className="mt-3">
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
                      <span className="min-w-0 break-words font-medium [overflow-wrap:anywhere]">{j.channel || "—"}</span>
                      <span className="text-xs text-slate-400">{formatTs(j.finished_at)}</span>
                      <span className="basis-full break-words text-sm text-red-700 [overflow-wrap:anywhere]" title={j.error}>
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
            </section>
        ) : null}
      </QueryBody>
    </div>
  );
}
