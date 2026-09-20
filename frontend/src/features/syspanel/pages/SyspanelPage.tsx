import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { StatCard } from "@/features/overview/components/StatCard";
import { useSyspanelController } from "../hooks/useSyspanelController";

import { ActionMsg } from "@/shared/ui/ActionMsg";
import { primaryBtnClass } from "@/shared/ui/controls";

export function SyspanelPage() {
  const { query, data, msg, busy, retryFailed, cancelStuck, worker } = useSyspanelController();

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Panel hệ thống"
        subtitle="Metrics + lệnh worker native — PM2 / cookie Gemini vẫn Classic"
        classicHref="/syspanel"
      />
      <ActionMsg text={msg} />
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={primaryBtnClass} disabled={busy} onClick={retryFailed}>
          Retry FAILED
        </button>
        <button type="button" className={primaryBtnClass} disabled={busy} onClick={cancelStuck}>
          Hủy job kẹt
        </button>
        <button type="button" className={primaryBtnClass} disabled={busy} onClick={() => worker("pause")}>
          Pause worker
        </button>
        <button type="button" className={primaryBtnClass} disabled={busy} onClick={() => worker("resume")}>
          Resume
        </button>
        <button type="button" className={primaryBtnClass} disabled={busy} onClick={() => worker("safe-mode")}>
          Safe mode
        </button>
      </div>
      <QueryBody
        isLoading={query.isLoading}
        isError={query.isError}
        loadingText="Đang tải…"
        errorText="Lỗi tải syspanel"
      >
        {data ? (
          <>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="CPU" value={`${Math.round(data.cpu)}%`} />
              <StatCard
                label="RAM"
                value={`${Math.round(data.mem_pct)}%`}
                hint={`${data.mem_used_gb} / ${data.mem_total_gb} GB`}
              />
              <StatCard
                label="Disk"
                value={`${Math.round(data.disk_pct)}%`}
                hint={`${data.disk_used_gb} / ${data.disk_total_gb} GB · ${data.disk_label}`}
              />
              <StatCard
                label="Jobs"
                value={String(Object.values(data.jobs).reduce((s, n) => s + n, 0))}
                hint={`${Object.keys(data.jobs).length} status`}
              />
            </div>
            <Panel className="mt-6">
              <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
                Hàng đợi theo status
              </div>
              <div className="flex flex-wrap gap-2 p-4">
                {Object.keys(data.jobs).length === 0 ? (
                  <span className="text-sm text-slate-400">Không có job</span>
                ) : (
                  Object.entries(data.jobs)
                    .sort((a, b) => b[1] - a[1])
                    .map(([st, n]) => (
                      <span
                        key={st}
                        className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700"
                      >
                        {st}: {n}
                      </span>
                    ))
                )}
              </div>
            </Panel>
          </>
        ) : null}
      </QueryBody>
    </div>
  );
}
