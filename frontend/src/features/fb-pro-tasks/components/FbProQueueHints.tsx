import { Link } from "react-router-dom";
import type { FbProQueueHint } from "../types/fbProTasks.types";

export function FbProQueueHints({ hints }: { hints: FbProQueueHint[] }) {
  if (hints.length === 0) {
    return (
      <p className="px-4 py-6 text-center text-sm text-slate-400">
        Không có job sẵn media cho scope này
      </p>
    );
  }

  return (
    <ul className="divide-y divide-slate-100">
      {hints.map((j) => (
        <li key={j.id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <span className="text-sm font-semibold">#{j.id}</span>
            <span className="ml-2 rounded border border-slate-200 px-1.5 py-0.5 text-[10px] uppercase text-slate-500">
              {j.status}
            </span>
            <span className="ml-1 text-xs text-slate-400">{j.is_video ? "video" : "ảnh"}</span>
            <p className="mt-0.5 max-w-xl truncate text-sm text-slate-500">
              {j.caption || j.media_name || "—"}
            </p>
          </div>
          <Link to="/app/go/jobs" className="shrink-0 text-xs font-medium text-indigo-600 hover:underline">
            Mở hàng đợi
          </Link>
        </li>
      ))}
    </ul>
  );
}
