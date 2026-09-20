import { selectClass } from "@/shared/ui/controls";
import type { FbProScopeOption } from "../types/fbProTasks.types";

export function FbProTasksFilters({
  selectedKey,
  options,
  onKeyChange,
}: {
  selectedKey: string;
  options: FbProScopeOption[];
  onKeyChange: (value: string) => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <select
        className={`${selectClass} min-w-[16rem]`}
        value={selectedKey}
        onChange={(e) => onKeyChange(e.target.value)}
        disabled={options.length === 0}
      >
        {options.length === 0 ? (
          <option value="">Chưa có account Facebook</option>
        ) : (
          options.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))
        )}
      </select>
    </div>
  );
}
