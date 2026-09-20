export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "ok" | "warn" | "bad";
}) {
  const box =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50"
      : tone === "warn"
        ? "border-amber-200 bg-amber-50"
        : tone === "bad"
          ? "border-red-200 bg-red-50"
          : "border-slate-200 bg-white";
  const valueColor =
    tone === "ok"
      ? "text-emerald-800"
      : tone === "warn"
        ? "text-amber-900"
        : tone === "bad"
          ? "text-red-800"
          : "text-slate-900";
  return (
    <div className={`rounded-2xl border p-4 shadow-sm ${box}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${valueColor}`}>{value}</div>
      {hint ? <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div> : null}
    </div>
  );
}
