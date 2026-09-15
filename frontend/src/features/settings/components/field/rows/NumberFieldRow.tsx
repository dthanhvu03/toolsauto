function parseNumber(raw: string, integer: boolean): number {
  if (integer) {
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : 0;
  }
  const n = parseFloat(raw);
  return Number.isFinite(n) ? n : 0;
}

export function NumberFieldRow({
  value,
  onChange,
  unit,
  disabled,
  min,
  max,
  integer = true,
}: {
  value: number;
  onChange: (v: number) => void;
  unit?: string | null;
  disabled?: boolean;
  min?: number;
  max?: number;
  integer?: boolean;
}) {
  const str = Number.isFinite(value) ? String(value) : "";
  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        inputMode="decimal"
        disabled={disabled}
        min={min}
        max={max}
        value={str}
        onChange={(e) => onChange(parseNumber(e.target.value, integer))}
        className="h-9 w-32 rounded-lg border border-slate-200 bg-white px-3 font-mono text-sm text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100"
      />
      {unit ? <span className="text-xs font-medium text-slate-500">{unit}</span> : null}
    </div>
  );
}
