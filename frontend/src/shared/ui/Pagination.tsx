export function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="mt-3 flex items-center justify-end gap-2">
      <button
        type="button"
        disabled={page <= 1}
        className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
        onClick={() => onPageChange(Math.max(1, page - 1))}
      >
        Trước
      </button>
      <span className="text-xs text-slate-500">
        {page} / {totalPages}
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
        onClick={() => onPageChange(page + 1)}
      >
        Sau
      </button>
    </div>
  );
}
