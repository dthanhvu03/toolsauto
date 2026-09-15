export function UrlFieldRow({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex max-w-lg items-center gap-2">
      <input
        type="url"
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="https://"
        className="h-9 flex-1 rounded-lg border border-slate-200 bg-white px-3 font-mono text-sm text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100"
      />
      {value && !disabled ? (
        <a
          href={value}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-xs font-medium text-indigo-600 hover:underline"
        >
          Open
        </a>
      ) : null}
    </div>
  );
}
