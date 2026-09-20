import { SearchField } from "@/shared/ui/SearchField";
import { selectClass } from "@/shared/ui/controls";

export function AccountsFilters({
  platform,
  qDraft,
  onPlatformChange,
  onDraftChange,
  onSearch,
}: {
  platform: string;
  qDraft: string;
  onPlatformChange: (value: string) => void;
  onDraftChange: (value: string) => void;
  onSearch: () => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <select
        className={selectClass}
        value={platform}
        onChange={(e) => onPlatformChange(e.target.value)}
      >
        <option value="">All platforms</option>
        <option value="facebook">facebook</option>
        <option value="threads">threads</option>
        <option value="tiktok">tiktok</option>
      </select>
      <SearchField
        placeholder="Tìm tên…"
        value={qDraft}
        onChange={onDraftChange}
        onSubmit={onSearch}
      />
    </div>
  );
}
