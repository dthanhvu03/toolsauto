import { Link } from "react-router-dom";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { StatCard } from "@/features/overview/components/StatCard";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { ghostBtnClass, primaryBtnClass } from "@/shared/ui/controls";
import { useThreadsController } from "../hooks/useThreadsController";
import type { ThreadsAccount } from "../types/threads.types";

function AccountList({
  title,
  rows,
  empty,
  actionLabel,
  onAction,
}: {
  title: string;
  rows: ThreadsAccount[];
  empty: string;
  actionLabel?: string;
  onAction?: (id: number) => void;
}) {
  return (
    <Panel>
      <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">{title}</div>
      {rows.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm text-slate-400">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {rows.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
              <span className="font-medium">{a.name}</span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">{a.login_status || a.platform}</span>
                {actionLabel && onAction ? (
                  <button type="button" className={ghostBtnClass} onClick={() => onAction(a.id)}>
                    {actionLabel}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function ThreadsPage() {
  const ctl = useThreadsController();
  const { query, data } = ctl;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Workspace Threads" subtitle="Scrape / auto / nối account ngay trên SPA" classicHref="/threads" />
      <ActionMsg text={ctl.msg} />
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={primaryBtnClass} disabled={ctl.busy} onClick={ctl.scrape}>
          Quét tin
        </button>
        <button type="button" className={primaryBtnClass} disabled={ctl.busy} onClick={ctl.toggleAuto}>
          Đảo auto
        </button>
      </div>
      <QueryBody
        isLoading={query.isLoading}
        isError={query.isError}
        loadingText="Đang tải…"
        errorText="Lỗi tải Threads"
      >
        {data ? (
          <>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <StatCard label="PENDING" value={String(data.stats.pending)} />
              <StatCard label="DONE" value={String(data.stats.success)} />
              <StatCard label="FAILED" value={String(data.stats.failed)} />
            </div>
            <p className="mt-3 text-xs text-slate-400">
              Hàng đợi đầy đủ:{" "}
              <Link to="/app/go/jobs-threads" className="text-indigo-600 hover:underline">
                Jobs Threads
              </Link>
            </p>
            <div className="mt-6 grid gap-4 lg:grid-cols-3">
              <AccountList
                title="Đã liên kết"
                rows={data.linked_accounts}
                empty="Chưa có account Threads"
                actionLabel="Gỡ"
                onAction={ctl.unlink}
              />
              <AccountList title="Đang xác minh" rows={data.verifying_accounts} empty="Không có" />
              <AccountList
                title="Chưa nối"
                rows={data.available_accounts}
                empty="Không có"
                actionLabel="Nối"
                onAction={ctl.link}
              />
            </div>
            <Panel className="mt-6">
              <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Tin mới</div>
              {data.articles.length === 0 ? (
                <p className="px-4 py-6 text-center text-sm text-slate-400">Chưa có bài news</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {data.articles.map((a) => (
                    <li key={a.id} className="px-4 py-2">
                      <div className="text-sm font-medium">{a.title}</div>
                      <div className="text-xs text-slate-400">
                        {a.source_name || "—"} · {a.status || "NEW"}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            <Panel className="mt-6">
              <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Job Threads gần đây</div>
              {data.jobs.length === 0 ? (
                <p className="px-4 py-6 text-center text-sm text-slate-400">Không có job</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {data.jobs.map((j) => (
                    <li key={j.id} className="flex items-center justify-between px-4 py-2 text-sm">
                      <span>
                        #{j.id} · {j.job_type || "—"}
                      </span>
                      <span className="text-xs text-slate-500">{j.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </>
        ) : null}
      </QueryBody>
    </div>
  );
}
