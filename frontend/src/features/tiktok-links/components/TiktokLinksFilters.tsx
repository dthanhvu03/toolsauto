import { SearchField } from "@/shared/ui/SearchField";

export function TiktokLinksFilters({
  qDraft,
  onDraftChange,
  onSearch,
}: {
  qDraft: string;
  onDraftChange: (value: string) => void;
  onSearch: () => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <SearchField
        placeholder="Tìm URL / tài khoản / page…"
        value={qDraft}
        onChange={onDraftChange}
        onSubmit={onSearch}
      />
    </div>
  );
}
