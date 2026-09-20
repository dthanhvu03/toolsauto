export function formatAgo(epoch?: number | null): string {
  if (!epoch) return "—";
  const sec = Math.max(0, Math.floor(Date.now() / 1000) - epoch);
  if (sec < 60) return "vừa xong";
  if (sec < 3600) return `${Math.floor(sec / 60)} phút trước`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} giờ trước`;
  return `${Math.floor(sec / 86400)} ngày trước`;
}
