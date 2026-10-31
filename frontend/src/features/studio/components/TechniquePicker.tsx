import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/shared/lib/cn";
import { useAssets, useSetup, useVoices } from "../hooks/useStudio";
import type { Techniques } from "../types/studio.types";

/** Mặc định bật hết các kỹ thuật */
export const DEFAULT_TECHNIQUES: Techniques = {
  subtitles: true,
  dub: true,
  vieneu_voice: "",
  hook: "",
  music_asset_id: null,
  mirror: false,
  lut: "",
};

const box = "flex min-w-0 flex-col gap-1 rounded-lg border px-2.5 py-2 text-sm";
const on = "border-indigo-200 bg-indigo-50/60";
const off = "border-slate-200 bg-white";
const field = "h-8 w-full min-w-0 rounded-md border border-slate-200 bg-white px-2 text-xs";

function Check({ checked, disabled, onChange, label }: { checked: boolean; disabled?: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className={cn("flex items-center gap-1.5 font-medium", disabled ? "text-slate-400" : "text-slate-800")}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

/**
 * Chọn kỹ thuật cho video đưa vào Studio. Đã mở toàn bộ cho mọi loại video.
 */
export function TechniquePicker({
  value,
  onChange,
  collected,
}: {
  value: Techniques;
  onChange: (t: Techniques) => void;
  collected?: boolean;
}) {
  const setup = useSetup();
  const voices = useVoices();
  const assets = useAssets("audio");
  // chỉ nhạc đã phân tích xong (có tiếng)
  const music = (assets.data?.assets ?? []).filter((a) => a.kind === "audio" && a.origin === "brand" && a.has_audio);
  const luts = setup.data?.luts ?? [];
  const set = (patch: Partial<Techniques>) => onChange({ ...value, ...patch });
  const musicTouched = useRef(false);
  
  useEffect(() => {
    if (value.music_asset_id == null && music.length && !musicTouched.current) set({ music_asset_id: music[0].id });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [music.length]);

  const vlist = voices.data?.voices ?? [];

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
      <div className={cn(box, value.subtitles ? on : off)}>
        <Check checked={value.subtitles} onChange={(v) => set({ subtitles: v })} label="Phụ đề tiếng Việt" />
        <span className="text-[11px] text-slate-500">Bỏ tick nếu video gốc đã có chữ sẵn</span>
      </div>

      <div className={cn(box, value.dub ? on : off)}>
        <Check checked={value.dub} onChange={(v) => set({ dub: v })} label="Lồng tiếng Việt" />
        {value.dub ? (
          <select className={field} value={value.vieneu_voice} onChange={(e) => set({ vieneu_voice: e.target.value })}>
            <option value="">Giọng của kênh / mặc định</option>
            {(["female", "male"] as const).map((g) => (
              <optgroup key={g} label={g === "female" ? "Nữ" : "Nam"}>
                {vlist
                  .filter((v) => v.gender === g)
                  .map((v) => (
                    <option key={v.name} value={v.name}>
                      {v.name}
                      {v.region ? ` · ${v.region}` : ""}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        ) : null}
        <span className="text-[11px] text-slate-500">Video đã là tiếng Việt / không có lời thì tự giữ tiếng gốc</span>
      </div>

      <div className={cn(box, value.hook.trim() ? on : off)}>
        <span className="font-medium text-slate-800">Câu hook mở đầu</span>
        <input className={field} placeholder="vd: Xem tới cuối nha! (trống = không)" value={value.hook} onChange={(e) => set({ hook: e.target.value })} />
      </div>

      <div className={cn(box, value.music_asset_id ? on : off)}>
        <Check
          checked={!!value.music_asset_id}
          disabled={!music.length}
          onChange={(v) => {
            musicTouched.current = true;
            set({ music_asset_id: v ? (music[0]?.id ?? null) : null });
          }}
          label="Nhạc nền"
        />
        {music.length ? (
          value.music_asset_id ? (
            <select className={field} value={value.music_asset_id} onChange={(e) => set({ music_asset_id: Number(e.target.value) })}>
              {music.map((a) => (
                <option key={a.id} value={a.id}>
                  #{a.id} {a.title}
                </option>
              ))}
            </select>
          ) : null
        ) : (
          <span className="text-[11px] text-slate-500">
            Chưa có nhạc — tải vào{" "}
            <Link to="/app/go/studio-assets" className="underline">
              Nguyên liệu
            </Link>
          </span>
        )}
      </div>

      <div className={cn(box, collected ? on : off)}>
        <Check checked={!!collected} disabled onChange={() => undefined} label="Ghi nguồn @kênh" />
        <span className="text-[11px] text-slate-500">{collected ? "Ghi nguồn từ link gốc" : "Video của anh: không cần"}</span>
      </div>

      <div className={cn(box, value.mirror ? on : off)} title="Lật trái ↔ phải">
        <span className="flex items-center gap-1.5">
          <Check checked={value.mirror} onChange={(v) => set({ mirror: v })} label="Lật gương" />
        </span>
        <span className="text-[11px] text-slate-500">Lật ngang toàn bộ video</span>
      </div>

      <div className={cn(box, value.lut ? on : off)}>
        <span className="flex items-center gap-1.5 font-medium text-slate-800">
          Tông màu (LUT)
        </span>
        {luts.length ? (
          <select className={field} value={value.lut} onChange={(e) => set({ lut: e.target.value })}>
            <option value="">Màu gốc</option>
            {luts.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-[11px] text-slate-500">Chưa có file .cube trong storage/media/luts</span>
        )}
      </div>
    </div>
  );
}
