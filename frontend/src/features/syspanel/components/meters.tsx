import { cn } from "@/shared/lib/cn";

/** Thanh % dùng chung cho bảng tiến trình PM2 và khung máy Windows. */
export function Bar({ pct, tone = "bg-indigo-500" }: { pct: number; tone?: string }) {
  return (
    <span className="block h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <span className={cn("block h-full rounded-full", tone)} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </span>
  );
}

export const gb = (mb: number) => `${(mb / 1024).toFixed(1).replace(".", ",")} GB`;
export const ram = (mb: number) => (mb >= 1024 ? gb(mb) : `${mb} MB`);

export function uptime(s: number | null | undefined): string {
  if (s == null) return "—";
  if (s < 60) return `${s} giây`;
  if (s < 3600) return `${Math.floor(s / 60)} phút`;
  if (s < 86400) return `${Math.floor(s / 3600)} giờ ${Math.floor((s % 3600) / 60)} phút`;
  return `${Math.floor(s / 86400)} ngày`;
}

/** Màu thanh theo mức dùng: > 85% đỏ, > 70% vàng, còn lại xanh. */
export const loadTone = (pct: number) => (pct > 85 ? "bg-red-500" : pct > 70 ? "bg-amber-500" : "bg-emerald-500");
