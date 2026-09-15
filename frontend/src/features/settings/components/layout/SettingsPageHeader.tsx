export function SettingsPageHeader({ envLabel }: { envLabel?: string }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-4">
          <a
            href="/app"
            className="text-xs font-medium text-slate-500 hover:text-indigo-600 hover:underline"
          >
            ← Dashboard
          </a>
          <div>
            <h1 className="font-display text-lg font-semibold text-slate-900">Settings</h1>
            <p className="text-xs text-slate-500">Automation runtime & integrations</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="/app/settings/classic"
            className="text-xs font-medium text-slate-400 hover:text-slate-700 hover:underline"
          >
            Classic UI
          </a>
          {envLabel ? (
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-slate-600">
              {envLabel}
            </span>
          ) : null}
        </div>
      </div>
    </header>
  );
}
