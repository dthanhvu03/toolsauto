import { ExternalLink } from "lucide-react";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { StatCard } from "@/features/overview/components/StatCard";
import { FbProQueueHints } from "../components/FbProQueueHints";
import { FbProTaskCards } from "../components/FbProTaskCards";
import { FbProTasksFilters } from "../components/FbProTasksFilters";
import { useFbProTasksController } from "../hooks/useFbProTasksController";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { primaryBtnClass } from "@/shared/ui/controls";

export function FbProTasksPage() {
  const ctl = useFbProTasksController();
  const dash = ctl.dash;
  const classicQs = ctl.selectedKey ? `?key=${encodeURIComponent(ctl.selectedKey)}` : "";

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Nhiệm vụ Facebook tuần này"
        subtitle="Sửa ghi chú / reset tuần ngay trên SPA"
        classicHref={`/app/fb-pro-tasks/${classicQs}`}
      />
      <ActionMsg text={ctl.msg} />

      <QueryBody
        isLoading={ctl.query.isLoading}
        isError={ctl.query.isError}
        loadingText="Đang tải…"
        errorText="Lỗi tải nhiệm vụ FB"
      >
        {dash ? (
          <>
            <FbProTasksFilters
              selectedKey={ctl.selectedKey}
              options={dash.scope_options}
              onKeyChange={ctl.setKey}
            />
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Tiến độ tuần" value={`${dash.overall_pct}%`} hint={dash.week_label} />
              <StatCard
                label="Còn lại"
                value={dash.days_left > 0 ? `${dash.days_left} ngày` : "Hôm nay"}
                hint={
                  dash.days_left > 0
                    ? "CN–T7 · Asia/Ho_Chi_Minh"
                    : "Hết hạn hôm nay / đã qua tuần"
                }
              />
              <StatCard label="Scope" value={dash.page_slug || dash.account_name || "—"} />
              <StatCard
                label="Job auto"
                value={`${dash.auto.posts ?? 0}/${dash.auto.reels ?? 0}`}
                hint="posts / reels"
              />
            </div>

            <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full bg-indigo-600"
                style={{ width: `${Math.min(100, dash.overall_pct)}%` }}
              />
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
              {dash.target_page ? (
                <span className="max-w-xl truncate text-xs text-slate-400">{dash.target_page}</span>
              ) : null}
              {dash.meta_url ? (
                <a
                  href={dash.meta_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline"
                >
                  Mở dashboard Meta <ExternalLink className="size-3" />
                </a>
              ) : null}
            </div>

            <Panel className="mt-6">
              <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
                3 nhiệm vụ tuần
              </div>
              <FbProTaskCards tasks={dash.tasks} />
            </Panel>

            {dash.notes !== undefined ? (
              <Panel className="mt-6">
                <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Ghi chú</div>
                <div className="space-y-2 p-4">
                  <textarea
                    className="min-h-[5rem] w-full rounded-lg border border-slate-200 p-2 text-sm"
                    value={ctl.notes}
                    onChange={(e) => ctl.setNotes(e.target.value)}
                  />
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className={primaryBtnClass} disabled={ctl.saving} onClick={ctl.save}>
                      Lưu ghi chú
                    </button>
                    <button type="button" className={primaryBtnClass} disabled={ctl.saving} onClick={ctl.resetWeek}>
                      Reset tuần
                    </button>
                  </div>
                </div>
              </Panel>
            ) : null}

            <Panel className="mt-6">
              <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
                Gợi ý queue
              </div>
              <FbProQueueHints hints={dash.queue_hints} />
            </Panel>
          </>
        ) : null}
      </QueryBody>
    </div>
  );
}
