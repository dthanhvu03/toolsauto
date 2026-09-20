import type { PageAnalysisItem } from "../types/insights.types";
import { formatK } from "../lib/formatK";

const STATUS_TONE: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700",
  rose: "bg-rose-50 text-rose-700",
  cyan: "bg-cyan-50 text-cyan-700",
  amber: "bg-amber-50 text-amber-700",
};

export function InsightsPageCards({ items }: { items: PageAnalysisItem[] }) {
  if (items.length === 0) {
    return <p className="px-4 py-6 text-center text-sm text-slate-400">Chưa có phân tích page</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <article
          key={item.page_url || item.page_name}
          className="rounded-xl border border-slate-200 bg-white p-4"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-slate-900">{item.page_name}</div>
              <span
                className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                  STATUS_TONE[item.color || "amber"] || STATUS_TONE.amber
                }`}
              >
                {item.status}
              </span>
            </div>
            <div className="text-right">
              <div className="text-lg font-semibold tabular-nums">{formatK(item.views || 0)}</div>
              <div className="text-xs font-semibold text-slate-500">
                {item.growth_pct >= 0 ? "+" : ""}
                {item.growth_pct}%
              </div>
            </div>
          </div>
          {item.advice ? (
            <p className="mt-3 text-xs italic text-slate-600">“{item.advice}”</p>
          ) : null}
        </article>
      ))}
    </div>
  );
}
