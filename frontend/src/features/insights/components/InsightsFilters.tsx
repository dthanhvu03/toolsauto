import { selectClass } from "@/shared/ui/controls";

export function InsightsFilters({
  platform,
  days,
  onPlatformChange,
  onDaysChange,
}: {
  platform: string;
  days: number;
  onPlatformChange: (value: string) => void;
  onDaysChange: (value: number) => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <select
        className={selectClass}
        value={platform}
        onChange={(e) => onPlatformChange(e.target.value)}
      >
        <option value="">Tất cả nền tảng</option>
        <option value="facebook">Facebook</option>
        <option value="tiktok">TikTok</option>
        <option value="instagram">Instagram</option>
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
