import { SearchField } from "@/shared/ui/SearchField";
import { selectClass } from "@/shared/ui/controls";

const STATUS_OPTS = [
  { value: "active", label: "Active" },
  { value: "PENDING", label: "PENDING" },
  { value: "RUNNING", label: "RUNNING" },
  { value: "DRAFT", label: "DRAFT" },
  { value: "DONE", label: "DONE" },
  { value: "FAILED", label: "FAILED" },
];

export function JobsFilters({
  status,
  platform,
  qDraft,
  onStatusChange,
  onPlatformChange,
  onDraftChange,
  onSearch,
}: {
  status: string;
  platform: string;
  qDraft: string;
  onStatusChange: (value: string) => void;
  onPlatformChange: (value: string) => void;
  onDraftChange: (value: string) => void;
  onSearch: () => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <select
        className={selectClass}
        value={status}
        onChange={(e) => onStatusChange(e.target.value)}
      >
        {STATUS_OPTS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <select
        className={selectClass}
        value={platform}
        onChange={(e) => onPlatformChange(e.target.value)}
      >
        <option value="">All platforms</option>
        <option value="facebook">facebook</option>
        <option value="threads">threads</option>
      </select>
      <SearchField
        placeholder="Tìm id / account / caption…"
        value={qDraft}
        onChange={onDraftChange}
        onSubmit={onSearch}
      />
    </div>
  );
}
