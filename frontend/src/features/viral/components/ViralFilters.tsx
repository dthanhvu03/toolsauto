import { SearchField } from "@/shared/ui/SearchField";
import { selectClass } from "@/shared/ui/controls";

export function ViralFilters({
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
    <div className="mt-4 flex flex-wrap gap-2">
      <select
        className={selectClass}
        value={status}
        onChange={(e) => onStatusChange(e.target.value)}
      >
        <option value="">All status</option>
        <option value="NEW">NEW</option>
        <option value="READY">READY</option>
        <option value="FAILED">FAILED</option>
        <option value="PROCESSING">PROCESSING</option>
        <option value="POSTED">POSTED</option>
      </select>
      <select
        className={selectClass}
        value={platform}
        onChange={(e) => onPlatformChange(e.target.value)}
      >
        <option value="">All platforms</option>
        <option value="tiktok">tiktok</option>
        <option value="facebook">facebook</option>
      </select>
      <SearchField
        placeholder="Tìm URL…"
        value={qDraft}
        onChange={onDraftChange}
        onSubmit={onSearch}
      />
    </div>
  );
}
