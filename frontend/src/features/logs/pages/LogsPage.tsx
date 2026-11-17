import { PageHeader } from "@/shared/ui/PageHeader";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { SearchField } from "@/shared/ui/SearchField";
import { selectClass } from "@/shared/ui/controls";
import { useLogsController } from "../hooks/useLogsController";

function fmtTs(unix?: number | null, fallback?: string) {
  if (unix) {
    try {
      return new Date(unix * 1000).toLocaleString("vi-VN", { hour12: false });
    } catch {
      return fallback || "—";
    }
  }
  return fallback || "—";
}

export function LogsPage() {
  const ctl = useLogsController();

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Nhật ký hệ thống"
        subtitle={ctl.query.data ? `${ctl.total} sự kiện domain` : "—"}
        classicHref="/app/logs"
      />
      <div className="mt-4 flex flex-wrap gap-2">
        <SearchField
          placeholder="Tìm message…"
          value={ctl.qDraft}
          onChange={ctl.setQDraft}
          onSubmit={ctl.applySearch}
        />
        <select
          className={selectClass}
          value={ctl.level}
          onChange={(e) => ctl.changeLevel(e.target.value)}
        >
          <option value="">Mọi level</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
      </div>
      <Panel className="mt-4">
        <QueryBody
          isLoading={ctl.query.isLoading}
          isError={ctl.query.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải logs"
        >
          {ctl.events.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-400">Không có sự kiện</p>
          ) : (
            <>
            <ul aria-label="Sự kiện hệ thống" className="divide-y divide-slate-100 md:hidden">
              {ctl.events.map((e, i) => <li key={`${e.ts_unix}-${e.source}-${i}`} className="space-y-2 p-4 text-sm [overflow-wrap:anywhere]">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                  <time>{fmtTs(e.ts_unix, e.timestamp)}</time>
                  <span className="rounded bg-slate-100 px-2 py-1 font-semibold text-slate-700">{e.level || "—"}</span>
                </div>
                <p className="text-xs text-slate-500">{e.source}{e.job_id != null ? ` · Job #${e.job_id}` : ""}</p>
                <p className="whitespace-pre-wrap text-slate-800">{e.message}</p>
              </li>)}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Thời gian</th>
                    <th className="px-3 py-2">Nguồn</th>
                    <th className="px-3 py-2">Level</th>
                    <th className="px-3 py-2">Job</th>
                    <th className="px-3 py-2">Message</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ctl.events.map((e, i) => (
                    <tr key={`${e.ts_unix}-${e.source}-${i}`} className="hover:bg-slate-50/80">
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-500">
                        {fmtTs(e.ts_unix, e.timestamp)}
                      </td>
                      <td className="px-3 py-2 text-xs">{e.source}</td>
                      <td className="px-3 py-2 text-xs">{e.level || "—"}</td>
                      <td className="px-3 py-2 text-xs tabular-nums">{e.job_id ?? "—"}</td>
                      <td className="max-w-[28rem] truncate px-3 py-2 text-xs text-slate-700">
                        {e.message}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          )}
        </QueryBody>
      </Panel>
      <Pagination page={ctl.page} totalPages={ctl.totalPages} onPageChange={ctl.setPage} />
    </div>
  );
}
