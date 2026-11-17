export function SettingsUnsavedBar({
  visible,
  onDiscard,
  embedded = false,
}: {
  visible: boolean;
  onDiscard: () => void;
  embedded?: boolean;
}) {
  if (!visible) return null;
  return (
    <div className={`fixed ${embedded ? "bottom-[calc(4rem+env(safe-area-inset-bottom))] lg:bottom-0 lg:left-64" : "bottom-0"} left-0 right-0 z-30 border-t border-amber-200 bg-amber-50/95 px-4 py-3 shadow-lg backdrop-blur`}>
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3">
        <p role="status" className="text-sm font-medium text-amber-950">Có thay đổi chưa lưu.</p>
        <button
          type="button"
          onClick={onDiscard}
          className="shrink-0 rounded-lg border border-amber-300 bg-white px-4 py-2 text-sm font-semibold text-amber-900 shadow-sm hover:bg-amber-100"
        >
          Bỏ thay đổi
        </button>
      </div>
    </div>
  );
}
