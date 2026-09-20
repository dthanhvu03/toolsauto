import { Link } from "react-router-dom";
import type { CockpitCheckpointItem, CockpitJob } from "../types/overview.types";

function fmtTs(ts?: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("vi-VN");
}

export function CockpitAlerts({
  failed,
  checkpoints,
}: {
  failed: CockpitJob[];
  checkpoints: CockpitCheckpointItem[];
}) {
  return (
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
          Job FAILED mới nhất
        </div>
        {failed.length === 0 ? (
          <p className="px-4 py-6 text-sm text-slate-400">Không có job FAILED</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {failed.map((j) => (
              <li key={j.id} className="px-4 py-2.5 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <Link className="font-medium text-indigo-700 hover:underline" to="/app/go/jobs">
                    #{j.id}
                  </Link>
                  <span className="text-[11px] text-slate-400">{fmtTs(j.finished_at)}</span>
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {j.account_name || "—"} · {j.error || "không có lỗi"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
          Checkpoint Facebook
        </div>
        {checkpoints.length === 0 ? (
          <p className="px-4 py-6 text-sm text-slate-400">Không có checkpoint</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {checkpoints.map((c) => (
              <li key={`${c.kind}-${c.id}`} className="px-4 py-2.5 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-800">
                    {c.account_name || `${c.kind} #${c.id}`}
                  </span>
                  <span className="text-[11px] text-slate-400">{fmtTs(c.at)}</span>
                </div>
                <div className="mt-0.5 text-xs text-slate-500">{c.detail || c.kind}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
