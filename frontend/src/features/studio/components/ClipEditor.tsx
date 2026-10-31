import { Scissors, Trash2 } from "lucide-react";
import { useState } from "react";
import { dangerBtnClass, ghostBtnClass } from "@/shared/ui/controls";
import { assetStripUrl } from "../api/studioApi";
import { cutRange } from "../lib/clips";
import { mmss, round2 } from "../lib/status";
import type { Asset, Clip } from "../types/studio.types";

const numCls = "h-8 w-20 rounded-lg border border-slate-200 px-2 text-sm tabular-nums";

/**
 * Đoạn cắt của video chính trên dải khung hình: phần sáng = giữ. Bấm dải 2 lần để chọn khoảng
 * rồi «Bỏ khoảng này»; hoặc gõ giây đầu / cuối từng đoạn. Intro / outro hiện thành chip cố định.
 */
export function ClipEditor({
  clips,
  main,
  assets,
  disabled,
  onChange,
}: {
  clips: Clip[];
  main: Asset;
  assets: Asset[];
  disabled: boolean;
  onChange: (clips: Clip[]) => void;
}) {
  const dur = main.duration ?? 0;
  const [mark, setMark] = useState<[number | null, number | null]>([null, null]);
  const names = Object.fromEntries(assets.map((a) => [a.id, a.title || `#${a.id}`]));
  const pct = (t: number) => `${dur ? (t / dur) * 100 : 0}%`;
  // Khoảng bị bỏ = phần bù của các đoạn giữ — phủ tối, phần giữ để sáng.
  const kept = clips
    .filter((c) => c.asset === main.id)
    .map((c) => [c.start, c.end ?? dur] as const)
    .sort((x, y) => x[0] - y[0]);
  const gaps: [number, number][] = [];
  let cursor = 0;
  for (const [k0, k1] of kept) {
    if (k0 > cursor) gaps.push([cursor, k0]);
    cursor = Math.max(cursor, k1);
  }
  if (cursor < dur) gaps.push([cursor, dur]);

  const pick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (disabled || !dur) return;
    const r = e.currentTarget.getBoundingClientRect();
    const t = round2(((e.clientX - r.left) / r.width) * dur);
    setMark(([a, b]) => (a === null || b !== null ? [t, null] : [a, t]));
  };
  const setClip = (i: number, patch: Partial<Clip>) => onChange(clips.map((c, k) => (k === i ? { ...c, ...patch } : c)));
  const [a, b] = mark;

  return (
    <div>
      <div
        className="relative h-16 cursor-crosshair overflow-hidden rounded-lg bg-slate-800"
        style={{ backgroundImage: `url(${assetStripUrl(main.id)})`, backgroundSize: "100% 100%" }}
        onClick={pick}
        title="Bấm 2 lần để chọn một khoảng"
      >
        {gaps.map(([g0, g1]) => (
          <div key={g0} className="absolute inset-y-0 bg-black/70" style={{ left: pct(g0), width: pct(g1 - g0) }} />
        ))}
        {a !== null ? (
          <div
            className="absolute inset-y-0 border-x-2 border-red-400 bg-red-500/40"
            style={{ left: pct(Math.min(a, b ?? a)), width: b === null ? "2px" : pct(Math.abs(b - a)) }}
          />
        ) : null}
      </div>
      <div className="mt-1 flex justify-between text-[10px] tabular-nums text-slate-400">
        <span>0:00</span>
        <span>{mmss(dur)}</span>
      </div>

      {a !== null ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span>
            Khoảng chọn: {mmss(a)}
            {b !== null ? ` → ${mmss(b)}` : " (bấm thêm điểm cuối)"}
          </span>
          {b !== null ? (
            <button
              type="button"
              className={`${dangerBtnClass} inline-flex items-center gap-1`}
              onClick={() => {
                onChange(cutRange(clips, main.id, dur, a, b));
                setMark([null, null]);
              }}
            >
              <Scissors className="size-3.5" /> Bỏ khoảng này
            </button>
          ) : null}
          <button type="button" className={ghostBtnClass} onClick={() => setMark([null, null])}>
            Huỷ chọn
          </button>
        </div>
      ) : null}

      <ul className="mt-3 flex flex-col gap-1.5">
        {clips.map((c, i) => (
          <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="w-6 text-xs text-slate-400">{i + 1}</span>
            {c.asset === main.id ? (
              <>
                <input
                  type="number"
                  step="0.1"
                  min={0}
                  className={numCls}
                  value={c.start}
                  disabled={disabled}
                  onChange={(e) => setClip(i, { start: Math.max(0, Number(e.target.value)) })}
                />
                <span className="text-slate-400">→</span>
                <input
                  type="number"
                  step="0.1"
                  className={numCls}
                  value={c.end ?? round2(dur)}
                  disabled={disabled}
                  onChange={(e) => setClip(i, { end: Number(e.target.value) })}
                />
                <span className="text-xs text-slate-400">giây</span>
                {c.audio.length ? <span className="rounded bg-indigo-50 px-1.5 text-[11px] text-indigo-700">tiếng lồng</span> : null}
              </>
            ) : (
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{names[c.asset] ?? `asset #${c.asset}`}</span>
            )}
            {clips.length > 1 ? (
              <button
                type="button"
                className="ml-auto text-slate-400 hover:text-red-600 disabled:opacity-40"
                disabled={disabled}
                aria-label="Bỏ đoạn"
                onClick={() => onChange(clips.filter((_, k) => k !== i))}
              >
                <Trash2 className="size-4" />
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
