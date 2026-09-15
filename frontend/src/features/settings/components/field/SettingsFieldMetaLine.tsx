export function SettingsFieldMetaLine({ metaKey }: { metaKey: string }) {
  return (
    <div className="mt-1 flex items-center gap-2">
      <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
        {metaKey}
      </code>
      <button
        type="button"
        className="text-[10px] font-medium text-indigo-600 hover:underline"
        onClick={() => navigator.clipboard.writeText(metaKey)}
      >
        Copy key
      </button>
    </div>
  );
}
