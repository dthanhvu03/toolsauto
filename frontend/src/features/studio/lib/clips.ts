import type { Clip } from "../types/studio.types";
import { round2 } from "./status";

/** Bỏ khoảng [from, to] (giây asset) khỏi mọi đoạn của ``asset`` — đoạn bị cắt giữa thành hai. */
export function cutRange(clips: Clip[], asset: number, duration: number, from: number, to: number): Clip[] {
  const a = Math.max(0, Math.min(from, to));
  const b = Math.max(from, to);
  const out: Clip[] = [];
  for (const c of clips) {
    if (c.asset !== asset) {
      out.push(c);
      continue;
    }
    const end = c.end ?? duration;
    if (b <= c.start || a >= end) {
      out.push(c);
      continue;
    }
    if (a - c.start >= 0.2) out.push({ ...c, end: round2(a) });
    if (end - b >= 0.2) out.push({ ...c, start: round2(b), end: c.end === null && b < duration ? null : round2(end) });
  }
  return out;
}

export function keptSeconds(clips: Clip[], durations: Record<number, number>): number {
  return clips.reduce((n, c) => n + Math.max(0, (c.end ?? durations[c.asset] ?? 0) - c.start), 0);
}
