import { inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";

const STATUS_OPTS = [
  { value: "all", label: "Tất cả" },
  { value: "DONE", label: "Đã lên Buffer" },
  { value: "FAILED", label: "Lỗi" },
  { value: "active", label: "Đang xử lý" },
];

export function JobsFilters({
  status,
  qDraft,
  onStatusChange,
  onDraftChange,
  onSearch,
}: {
  status: string;
  qDraft: string;
  onStatusChange: (value: string) => void;
  onDraftChange: (value: string) => void;
  onSearch: () => void;
}) {
  return (
    <form className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center" onSubmit={(e) => { e.preventDefault(); onSearch(); }}>
      <select aria-label="Trạng thái lượt đăng" className={`${selectClass} !h-11 w-full !text-base sm:w-auto sm:!text-sm`} value={status} onChange={(e) => onStatusChange(e.target.value)}>
        {STATUS_OPTS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <div className="flex min-w-0 flex-1 gap-2">
        <input aria-label="Tìm lịch đăng theo mã hoặc caption" className={`${inputClass} !h-11 !min-w-0 w-full !text-base sm:!text-sm`} placeholder="Tìm mã / caption…" value={qDraft} onChange={(e) => onDraftChange(e.target.value)} />
        <button type="submit" className={`${primaryBtnClass} !h-11 shrink-0 !px-5`}>Tìm</button>
      </div>
    </form>
  );
}
