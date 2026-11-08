import { ActionMsg } from "@/shared/ui/ActionMsg";
import { ghostBtnClass } from "@/shared/ui/controls";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { useSyspanelController } from "../hooks/useSyspanelController";

/** Tab «Hàng đợi (hệ cũ)»: job đăng bài hệ cũ theo trạng thái + các nút xử lý. Giữ nguyên hành vi trang cũ. */
export function LegacyJobsPanel() {
  const { query, data, msg, busy, retryFailed, cancelStuck, worker } = useSyspanelController();
  const total = data ? Object.values(data.jobs).reduce((s, n) => s + n, 0) : 0;

  return (
    <section className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <span className="text-sm font-semibold">Hàng đợi job đăng bài (hệ cũ)</span>
          <span className="text-xs text-slate-400">tự cập nhật 15 giây</span>
        </div>
        <QueryBody isLoading={query.isLoading} isError={query.isError} loadingText="Đang tải…" errorText="Lỗi tải hàng đợi">
          {data ? (
            <div className="p-4">
              <p className="text-sm text-slate-600">
                Tổng <b className="tabular-nums text-slate-900">{total}</b> job · {Object.keys(data.jobs).length} trạng thái
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {total === 0 ? (
                  <span className="text-sm text-slate-400">Không có job</span>
                ) : (
                  Object.entries(data.jobs)
                    .sort((a, b) => b[1] - a[1])
                    .map(([st, n]) => (
                      <span
                        key={st}
                        className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium tabular-nums text-slate-700"
                      >
                        {st}: {n}
                      </span>
                    ))
                )}
              </div>
            </div>
          ) : null}
        </QueryBody>
      </Panel>

      <Panel className="p-4">
        <div className="text-sm font-semibold">Xử lý hàng đợi</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className={ghostBtnClass} disabled={busy} onClick={retryFailed} title="Đưa job FAILED về chờ chạy lại">
            Chạy lại job lỗi
          </button>
          <button type="button" className={ghostBtnClass} disabled={busy} onClick={cancelStuck} title="Huỷ job đang chạy quá lâu">
            Huỷ job kẹt
          </button>
          <span className="mx-1 hidden w-px bg-slate-200 sm:block" />
          <button type="button" className={ghostBtnClass} disabled={busy} onClick={() => worker("pause")}>
            Tạm dừng worker
          </button>
          <button type="button" className={ghostBtnClass} disabled={busy} onClick={() => worker("resume")}>
            Chạy tiếp worker
          </button>
          <button type="button" className={ghostBtnClass} disabled={busy} onClick={() => worker("safe-mode")}>
            Chế độ an toàn
          </button>
        </div>
        <ActionMsg text={msg} />
        {data ? (
          <p className="mt-3 text-xs text-slate-400">
            Ổ WSL ({data.disk_label}): {data.disk_used_gb} / {data.disk_total_gb} GB ({Math.round(data.disk_pct)}%)
          </p>
        ) : null}
      </Panel>
    </section>
  );
}
