import { ListTodo, Settings, Users, Zap } from "lucide-react";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { useOverview } from "../hooks/useOverview";
import { OverviewAccountsList } from "../components/OverviewAccountsList";
import { QuickLink } from "../components/QuickLink";
import { StatCard } from "../components/StatCard";

export function OverviewPage() {
  const q = useOverview();

  if (q.isLoading) {
    return <p className="text-sm text-slate-500">Đang tải tổng quan…</p>;
  }
  if (q.isError || !q.data) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Không tải được /api/admin/overview. Kiểm tra đăng nhập / FastAPI.
        <button type="button" className="ml-3 underline" onClick={() => q.refetch()}>
          Thử lại
        </button>
      </div>
    );
  }

  const d = q.data;
  const counts = d.queue.counts || {};

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Tổng quan"
        subtitle={
          <>
            Worker: <strong>{d.state.worker_status || "—"}</strong>
            {d.state.safe_mode ? " · SAFE MODE" : ""}
            {d.state.current_job_id ? ` · job #${d.state.current_job_id}` : ""}
          </>
        }
        classicHref="/app/classic"
        classicLabel="Classic overview"
        classicHover="hover:text-slate-700"
      />

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Tài khoản" value={`${d.accounts_active}/${d.accounts_count}`} hint="active/total" />
        <StatCard label="Job PENDING" value={String(counts.PENDING ?? 0)} />
        <StatCard label="Viral NEW" value={String(d.queue.viral_new ?? 0)} />
        <StatCard label="Viral FAILED" value={String(d.queue.viral_failed ?? 0)} />
      </div>

      <Panel className="mt-6">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
          Hàng đợi theo status
        </div>
        <div className="flex flex-wrap gap-2 p-4">
          {Object.keys(counts).length === 0 ? (
            <span className="text-sm text-slate-400">Không có job</span>
          ) : (
            Object.entries(counts)
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

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <QuickLink to="/app/settings" title="Cài đặt vận hành" desc="React native" icon={Settings} />
        <QuickLink to="/app/go/jobs" title="Hàng đợi job" desc="React list" icon={ListTodo} />
        <QuickLink to="/app/go/viral" title="Nội dung viral" desc="React list" icon={Zap} />
        <QuickLink to="/app/go/accounts" title="Tài khoản" desc="React list" icon={Users} />
      </div>

      <Panel className="mt-6">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Tài khoản</div>
        <OverviewAccountsList accounts={d.accounts} />
      </Panel>
    </div>
  );
}
