import { useState } from "react";

export function SecretFieldRow({
  pendingValue,
  hasValue,
  onChange,
  disabled,
}: {
  pendingValue: string | undefined;
  hasValue: boolean;
  onChange: (v: string | undefined) => void;
  disabled?: boolean;
}) {
  const [show, setShow] = useState(false);
  const display = pendingValue ?? "";
  const placeholder =
    hasValue && pendingValue === undefined ? "•••••••• (unchanged)" : "Enter new value";

  return (
    <div className="flex max-w-lg flex-col gap-2">
      <div className="flex items-center gap-2">
        <input
          type={show ? "text" : "password"}
          disabled={disabled}
          value={display}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
          autoComplete="off"
          className="h-9 flex-1 rounded-lg border border-slate-200 bg-white px-3 font-mono text-sm text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100"
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => setShow((s) => !s)}
          className="rounded-lg border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          {show ? "Hide" : "Show"}
        </button>
      </div>
      {hasValue && pendingValue === undefined ? (
        <p className="text-[11px] text-slate-500">A value is stored. Type to replace.</p>
      ) : null}
    </div>
  );
}
