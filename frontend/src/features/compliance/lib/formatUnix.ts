export function formatUnix(ts?: number | null): string {
  if (!ts) return "—";
  try {
    return new Date(ts * 1000).toLocaleString("vi-VN", { hour12: false });
  } catch {
    return "—";
  }
}
