import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ExternalLink, ListTodo, Settings, Users, Zap } from "lucide-react";
import { fetchOverview } from "@/shared/api/adminApi";

export function OverviewPage() {
  const q = useQuery({ queryKey: ["admin-overview"], queryFn: fetchOverview });

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
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Tổng quan</h1>
          <p className="mt-1 text-sm text-slate-500">
            Worker: <strong>{d.state.worker_status || "—"}</strong>
            {d.state.safe_mode ? " · SAFE MODE" : ""}
            {d.state.current_job_id ? ` · job #${d.state.current_job_id}` : ""}
          </p>
        </div>
        <a
          href="/app/classic"
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-400 hover:text-slate-700"
        >
          Classic overview <ExternalLink className="size-3" />
        </a>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Tài khoản" value={`${d.accounts_active}/${d.accounts_count}`} hint="active/total" />
        <Stat label="Job PENDING" value={String(counts.PENDING ?? 0)} />
        <Stat label="Viral NEW" value={String(d.queue.viral_new ?? 0)} />
        <Stat label="Viral FAILED" value={String(d.queue.viral_failed ?? 0)} />
      </div>

      <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Hàng đợi theo status</div>
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
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <QuickLink to="/app/settings" title="Cài đặt vận hành" desc="React native" icon={Settings} />
        <QuickLink to="/app/go/jobs" title="Hàng đợi job" desc="React list" icon={ListTodo} />
        <QuickLink to="/app/go/viral" title="Nội dung viral" desc="React list" icon={Zap} />
        <QuickLink to="/app/go/accounts" title="Tài khoản" desc="React list" icon={Users} />
      </div>

      <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Tài khoản</div>
        <ul className="divide-y divide-slate-100">
          {d.accounts.slice(0, 12).map((a) => (
            <li key={a.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
              <span className="font-medium text-slate-800">
                {a.name}{" "}
                <span className="text-xs font-normal text-slate-400">{a.platform}</span>
              </span>
              <span
                className={
                  a.is_active ? "text-xs font-semibold text-emerald-600" : "text-xs text-slate-400"
                }
              >
                {a.is_active ? "active" : "off"} · {a.login_status || "—"}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      {hint ? <div className="mt-0.5 text-[11px] text-slate-400">{hint}</div> : null}
    </div>
  );
}

function QuickLink({
  to,
  title,
  desc,
  icon: Icon,
}: {
  to: string;
  title: string;
  desc: string;
  icon: typeof Settings;
}) {
  return (
    <Link
      to={to}
      className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-200"
    >
      <span className="rounded-lg bg-indigo-50 p-2 text-indigo-700">
        <Icon className="size-5" />
      </span>
      <div>
        <div className="font-semibold text-slate-900">{title}</div>
        <div className="mt-1 text-xs text-slate-500">{desc}</div>
      </div>
    </Link>
  );
}
