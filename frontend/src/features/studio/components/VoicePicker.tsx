import { useEffect, useRef, useState } from "react";
import { ghostBtnClass, selectClass } from "@/shared/ui/controls";
import * as api from "../api/studioApi";
import { useVoices } from "../hooks/useStudio";
import type { Voice } from "../types/studio.types";

const GROUPS: { gender: Voice["gender"]; label: string }[] = [
  { gender: "female", label: "Nữ" },
  { gender: "male", label: "Nam" },
];

/** Giọng VieNeu của một kênh + nghe thử (PLAN-112). ``value`` null = theo mẫu. */
export function VoicePicker({
  value,
  disabled,
  onChange,
  onError,
}: {
  value: string | null;
  disabled?: boolean;
  onChange: (voice: string | null) => void;
  onError: (msg: string) => void;
}) {
  const q = useVoices();
  const voices = q.data?.voices ?? [];
  const online = q.data?.online ?? false;
  const [phase, setPhase] = useState<"idle" | "loading" | "playing">("idle");
  const audio = useRef<HTMLAudioElement | null>(null);

  const stop = () => {
    const a = audio.current;
    if (a) {
      a.pause();
      URL.revokeObjectURL(a.src);
    }
    audio.current = null;
    setPhase("idle");
  };
  useEffect(() => stop, []);

  const preview = async () => {
    if (!value) return;
    stop();
    setPhase("loading");
    try {
      const a = new Audio(URL.createObjectURL(await api.fetchVoicePreview(value)));
      audio.current = a;
      a.onended = stop;
      await a.play();
      setPhase("playing");
    } catch (e) {
      stop();
      onError(`Lỗi: ${(e as Error).message}`);
    }
  };

  const known = voices.some((v) => v.name === value);
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-xs text-slate-500">
        Giọng lồng tiếng
        <select
          className={`${selectClass} mt-1 block w-64 max-w-full`}
          value={value ?? ""}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">Theo mẫu (nữ / nam)</option>
          {value && !known ? <option value={value}>{value}</option> : null}
          {GROUPS.map((g) => (
            <optgroup key={g.gender} label={g.label}>
              {voices
                .filter((v) => v.gender === g.gender)
                .map((v) => (
                  <option key={v.name} value={v.name} title={v.description}>
                    {v.name}
                    {v.region ? ` · ${v.region}` : ""}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </label>
      <button
        type="button"
        className={ghostBtnClass + " h-9"}
        disabled={!value || !online || phase === "loading"}
        title={value ? "Đọc một câu mẫu bằng giọng này" : "Chọn một giọng để nghe thử"}
        onClick={() => (phase === "playing" ? stop() : preview())}
      >
        {phase === "loading" ? "Đang đọc…" : phase === "playing" ? "■ Dừng" : "▶ Nghe thử"}
      </button>
      {q.isLoading ? null : !online ? (
        <span className="pb-2 text-xs text-amber-600">Server giọng VieNeu đang tắt — lồng tiếng dùng giọng dự phòng (edge-tts).</span>
      ) : (
        <span className="pb-2 text-xs text-slate-400">Chỉ dùng khi mẫu của kênh có lồng tiếng (reup_dub).</span>
      )}
    </div>
  );
}
