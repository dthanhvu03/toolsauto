import { selectClass } from "@/shared/ui/controls";

export function ComplianceViolationFilters({
  days,
  action,
  onDaysChange,
  onActionChange,
}: {
  days: number;
  action: string;
  onDaysChange: (value: number) => void;
  onActionChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 p-4">
      <select
        className={selectClass}
        value={action}
        onChange={(e) => onActionChange(e.target.value)}
      >
        <option value="">Tất cả hành động</option>
        <option value="VIOLATION">Bị chặn</option>
        <option value="WARNING">Cảnh báo</option>
        <option value="SAFE">An toàn</option>
      </select>
      <select
        className={selectClass}
        value={String(days)}
        onChange={(e) => onDaysChange(Number(e.target.value))}
      >
        <option value="7">7 ngày</option>
        <option value="30">30 ngày</option>
        <option value="90">90 ngày</option>
      </select>
    </div>
  );
}
