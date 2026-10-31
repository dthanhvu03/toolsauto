import type { Asset, ProjectSpec } from "../types/studio.types";

function Volume({ label, value, onChange, disabled }: { label: string; value: number; onChange: (v: number) => void; disabled: boolean }) {
  return (
    <label className="flex items-center gap-3 text-sm">
      <span className="w-32 shrink-0 text-slate-600">{label}</span>
      <input type="range" min={0} max={2} step={0.05} value={value} disabled={disabled} className="flex-1" onChange={(e) => onChange(Number(e.target.value))} />
      <span className="w-10 text-right text-xs tabular-nums text-slate-500">{Math.round(value * 100)}%</span>
    </label>
  );
}

/** Chữ hook (dòng chữ đầu video) + âm lượng: tiếng gốc, nhạc nền, giọng lồng / nền tách. */
export function TextAudioPanel({
  spec,
  assets,
  disabled,
  onChange,
}: {
  spec: ProjectSpec;
  assets: Asset[];
  disabled: boolean;
  onChange: (spec: ProjectSpec) => void;
}) {
  const hook = spec.texts[0];
  const names = Object.fromEntries(assets.map((a) => [a.id, a.title || `#${a.id}`]));
  const dubbed = spec.clips.find((c) => c.audio.length);
  const setHook = (text: string, end?: number) => {
    const rest = spec.texts.slice(1);
    const base = hook ?? { text: "", start: 0, end: 3, pos: "top" as const, size: 72 };
    const next = { ...base, text, end: end ?? base.end };
    onChange({ ...spec, texts: text.trim() ? [next, ...rest] : rest });
  };
  const setClipAudio = (k: number, volume: number) =>
    onChange({
      ...spec,
      clips: spec.clips.map((c) => (c.audio.length ? { ...c, audio: c.audio.map((a, j) => (j === k ? { ...a, volume } : a)) } : c)),
    });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="h-9 min-w-[12rem] flex-1 rounded-lg border border-slate-200 px-3 text-sm"
          placeholder="Chữ hook đầu video (để trống = không có)"
          value={hook?.text ?? ""}
          disabled={disabled}
          onChange={(e) => setHook(e.target.value)}
        />
        <label className="flex items-center gap-1 text-xs text-slate-500">
          hiện
          <input
            type="number"
            min={1}
            step={0.5}
            className="h-9 w-16 rounded-lg border border-slate-200 px-2 text-sm"
            value={hook?.end ?? 3}
            disabled={disabled || !hook}
            onChange={(e) => setHook(hook?.text ?? "", Number(e.target.value))}
          />
          giây
        </label>
      </div>
      <Volume label="Tiếng gốc" value={spec.audio.original} disabled={disabled || !!dubbed} onChange={(v) => onChange({ ...spec, audio: { ...spec.audio, original: v } })} />
      {dubbed?.audio.map((a, k) => (
        <Volume key={a.asset} label={k === 0 ? "Giọng lồng" : "Nền (đã tách giọng)"} value={a.volume} disabled={disabled} onChange={(v) => setClipAudio(k, v)} />
      ))}
      {spec.audio.tracks.map((t, k) => (
        <Volume
          key={k}
          label={`Nhạc: ${names[t.asset] ?? `#${t.asset}`}`}
          value={t.volume}
          disabled={disabled}
          onChange={(v) => onChange({ ...spec, audio: { ...spec.audio, tracks: spec.audio.tracks.map((x, j) => (j === k ? { ...x, volume: v } : x)) } })}
        />
      ))}
    </div>
  );
}
