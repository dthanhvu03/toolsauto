import { SearchField } from "@/shared/ui/SearchField";
import { selectClass } from "@/shared/ui/controls";
import type { ComplianceCategory } from "../types/compliance.types";

export function ComplianceKeywordFilters({
  searchDraft,
  onDraftChange,
  onSearch,
  severity,
  category,
  categories,
  onSeverityChange,
  onCategoryChange,
}: {
  searchDraft: string;
  onDraftChange: (value: string) => void;
  onSearch: () => void;
  severity: string;
  category: string;
  categories: ComplianceCategory[];
  onSeverityChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 p-4">
      <SearchField
        placeholder="Tìm từ khóa…"
        value={searchDraft}
        onChange={onDraftChange}
        onSubmit={onSearch}
      />
      <select
        className={selectClass}
        value={severity}
        onChange={(e) => onSeverityChange(e.target.value)}
      >
        <option value="">Tất cả mức độ</option>
        <option value="VIOLATION">VIOLATION</option>
        <option value="WARNING">WARNING</option>
      </select>
      <select
        className={selectClass}
        value={category}
        onChange={(e) => onCategoryChange(e.target.value)}
      >
        <option value="">Tất cả danh mục</option>
        {categories.map((c) => (
          <option key={c.category} value={c.category}>
            {c.label || c.category} ({c.total})
          </option>
        ))}
      </select>
    </div>
  );
}
