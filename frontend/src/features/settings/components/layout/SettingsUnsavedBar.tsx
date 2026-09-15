export function SettingsUnsavedBar({
  visible,
  onDiscard,
}: {
  visible: boolean;
  onDiscard: () => void;
}) {
  if (!visible) return null;
  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-amber-200 bg-amber-50/95 px-4 py-3 shadow-lg backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
        <p className="text-sm font-medium text-amber-950">You have unsaved changes.</p>
        <button
          type="button"
          onClick={onDiscard}
          className="rounded-lg border border-amber-300 bg-white px-4 py-2 text-sm font-semibold text-amber-900 shadow-sm hover:bg-amber-100"
        >
          Discard all
        </button>
      </div>
    </div>
  );
}
