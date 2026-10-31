import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { uploadFile } from "../api/studioApi";
import { useAction } from "../hooks/useStudio";

/** Upload video tự quay (→ dự án) hoặc nguyên liệu (``brand``: logo / intro / nhạc → chỉ vào kho). */
export function UploadBox({ channels, brand = false }: { channels: { id: number; name: string }[]; brand?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [channelId, setChannelId] = useState<number | "">("");
  const [name, setName] = useState("");
  const act = useAction(
    (file: File) => uploadFile(file, { channelId: channelId || null, brand }),
    brand ? "Đã đưa vào kho nguyên liệu." : "Đã nhận — Studio đang dựng, thẻ sẽ hiện ở «Đang làm».",
    [["studio-projects"], ["studio-assets"]]
  );
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-dashed border-slate-300 bg-white p-3">
      <input
        ref={input}
        type="file"
        accept={brand ? "video/*,audio/*,image/*" : "video/*"}
        className="hidden"
        onChange={(e) => setName(e.target.files?.[0]?.name ?? "")}
      />
      <button type="button" className="h-9 rounded-lg border border-slate-200 px-3 text-sm" onClick={() => input.current?.click()}>
        {name || (brand ? "Chọn logo / intro / nhạc…" : "Chọn video tự quay…")}
      </button>
      {!brand ? (
        <select className={selectClass} value={channelId} onChange={(e) => setChannelId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Chưa gắn kênh</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      ) : null}
      <button
        type="button"
        className={`${primaryBtnClass} inline-flex items-center gap-1.5`}
        disabled={!name || act.busy}
        onClick={() => {
          const f = input.current?.files?.[0];
          if (f) act.run(f);
        }}
      >
        <Upload className="size-4" /> {act.busy ? "Đang gửi…" : "Đưa vào Studio"}
      </button>
      {act.msg ? <span className={`text-xs ${act.msg.startsWith("Lỗi") ? "text-red-700" : "text-emerald-700"}`}>{act.msg}</span> : null}
    </div>
  );
}
