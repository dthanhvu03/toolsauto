import { SearchField } from "@/shared/ui/SearchField";
import { selectClass } from "@/shared/ui/controls";

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
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <select className={selectClass} value={status} onChange={(e) => onStatusChange(e.target.value)}>
        {STATUS_OPTS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <SearchField placeholder="Tìm id / caption…" value={qDraft} onChange={onDraftChange} onSubmit={onSearch} />
    </div>
  );
}
