import type { FbProTask } from "../types/fbProTasks.types";

export function FbProTaskCards({ tasks }: { tasks: FbProTask[] }) {
  if (tasks.length === 0) {
    return <p className="px-4 py-6 text-center text-sm text-slate-400">Chưa có nhiệm vụ</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
      {tasks.map((t) => (
        <article key={t.key} className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between gap-2">
            <span
              className={`text-[10px] font-bold uppercase ${
                t.source === "auto" ? "text-emerald-700" : "text-indigo-600"
              }`}
            >
              {t.source}
            </span>
            <span className="text-xs text-slate-400">{t.pct}%</span>
          </div>
          <h3 className="mt-2 min-h-[2.5rem] text-sm font-semibold text-slate-900">{t.label}</h3>
          <p className="mt-3 text-3xl font-semibold tabular-nums text-slate-900">
            {t.current}
            <span className="text-lg text-slate-400">/{t.target}</span>
          </p>
          {t.auto != null ? (
            <p className="mt-1 text-xs text-slate-400">
              {t.source === "manual" ? `Job auto: ${t.auto}` : "Từ Job DONE (scope này)"}
            </p>
          ) : (
            <p className="mt-1 text-xs text-slate-400">Nhập tay theo Meta</p>
          )}
          <p
            className={`mt-2 text-xs font-medium ${
              t.remaining > 0 ? "text-indigo-600" : "text-emerald-700"
            }`}
          >
            {t.remaining > 0 ? `Còn thiếu ${t.remaining}` : "Đã đủ target"}
          </p>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full ${t.pct >= 100 ? "bg-emerald-500" : "bg-indigo-500"}`}
              style={{ width: `${Math.min(100, t.pct)}%` }}
            />
          </div>
        </article>
      ))}
    </div>
  );
}
