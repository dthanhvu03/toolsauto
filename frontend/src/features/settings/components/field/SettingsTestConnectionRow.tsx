import type { TestConnectionState } from "../../types/settings.types";

export function SettingsTestConnectionRow({
  label,
  state,
  onTest,
  disabled,
}: {
  label: string;
  state: TestConnectionState;
  onTest: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
      <button
        type="button"
        disabled={disabled || state.status === "loading"}
        onClick={onTest}
        className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
      >
        {state.status === "loading" ? "Testing…" : label}
      </button>
      {state.status === "success" ? (
        <span className="text-xs font-medium text-emerald-700">
          OK{state.latencyMs != null ? ` · ${state.latencyMs}ms` : ""}
          {state.message ? ` · ${state.message}` : ""}
        </span>
      ) : null}
      {state.status === "error" ? (
        <span className="text-xs font-medium text-red-600">{state.message ?? "Failed"}</span>
      ) : null}
    </div>
  );
}
