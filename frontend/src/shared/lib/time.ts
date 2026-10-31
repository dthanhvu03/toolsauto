/** Epoch giây → "31/10 19:30" giờ Việt Nam (máy xem ở múi khác vẫn đúng giờ đăng). */
export function formatTs(ts?: number | null, withYear = false): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    hour12: false,
    day: "2-digit",
    month: "2-digit",
    ...(withYear ? { year: "numeric" } : {}),
    hour: "2-digit",
    minute: "2-digit",
  });
}
