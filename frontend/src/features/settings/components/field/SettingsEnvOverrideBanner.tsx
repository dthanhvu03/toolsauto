export function SettingsEnvOverrideBanner() {
  return (
    <div className="mb-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-900">
      Set via <strong>environment</strong> on the server — cannot edit here.
    </div>
  );
}
