import { Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { uploadFile } from "../api/studioApi";
import { useAction } from "../hooks/useStudio";
import type { Techniques } from "../types/studio.types";
import { DEFAULT_TECHNIQUES, TechniquePicker } from "./TechniquePicker";

/**
 * Upload video (→ dự án) hoặc nguyên liệu (``brand``: logo / intro / nhạc → chỉ vào kho).
 * Video chọn kênh Buffer (1 kênh thì tự chọn) hoặc «Đăng tay» (duyệt xong tải về tự đăng, PLAN-113).
 * «Sưu tầm» = video của người khác → ghi nguồn, không lật / biến thể.
 * Kỹ thuật chọn bằng ô tick (PLAN-116, mặc định bật hết); bỏ tick «Phụ đề» khi video đã có chữ sẵn.
 */
export function UploadBox({ channels, brand = false }: { channels: { id: number; name: string }[]; brand?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [channelId, setChannelId] = useState<number | "" | "manual">("");
  const [name, setName] = useState("");
  const [collected, setCollected] = useState(false);
  const [credit, setCredit] = useState("");
  const [techniques, setTechniques] = useState<Techniques>(DEFAULT_TECHNIQUES);
  useEffect(() => {
    if (channels.length === 1 && channelId === "") setChannelId(channels[0].id);
  }, [channels, channelId]);
  const act = useAction(
    (file: File) =>
      uploadFile(file, {
        channelId: typeof channelId === "number" ? channelId : null,
        brand,
        collected,
        credit,
        techniques: brand ? undefined : techniques,
      }),
    brand
      ? "Đã đưa vào kho nguyên liệu."
      : channelId === "manual"
        ? "Đã nhận — duyệt xong tải video ở cột «Đã duyệt» để đăng tay."
        : "Đã nhận — Studio đang dựng, thẻ sẽ hiện ở «Đang làm».",
    [["studio-projects"], ["studio-assets"]]
  );
  const needChannel = !brand && !channelId;
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-dashed border-slate-300 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={input}
          type="file"
          accept={brand ? "video/*,audio/*,image/*" : "video/*"}
          className="hidden"
          onChange={(e) => setName(e.target.files?.[0]?.name ?? "")}
        />
        <button type="button" className="h-9 max-w-xs truncate rounded-lg border border-slate-200 px-3 text-sm" onClick={() => input.current?.click()}>
          {name || (brand ? "Chọn logo / intro / nhạc…" : "Chọn video…")}
        </button>
        {!brand ? (
          <select
            className={selectClass}
            value={channelId}
            onChange={(e) => setChannelId(e.target.value === "manual" ? "manual" : e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">— chọn kênh —</option>
            <option value="manual">Đăng tay (không qua Buffer)</option>
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
          disabled={!name || needChannel || act.busy}
          onClick={() => {
            const f = input.current?.files?.[0];
            if (f) act.run(f);
          }}
        >
          <Upload className="size-4" /> {act.busy ? "Đang gửi…" : "Đưa vào Studio"}
        </button>
      </div>
      {!brand ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-700">
          <label className="flex items-center gap-1.5">
            <input type="radio" checked={!collected} onChange={() => setCollected(false)} /> Video của tôi
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" checked={collected} onChange={() => setCollected(true)} /> Video sưu tầm
          </label>
          {collected ? (
            <input
              className="h-8 w-44 rounded-lg border border-slate-200 px-2 text-sm"
              placeholder="Nguồn: @kênh gốc"
              value={credit}
              onChange={(e) => setCredit(e.target.value)}
            />
          ) : null}
        </div>
      ) : null}
      {!brand ? <TechniquePicker value={techniques} onChange={setTechniques} collected={collected} /> : null}
      {needChannel && channels.length === 0 ? (
        <p className="text-xs text-amber-700">
          Chưa có kênh Buffer nào — chọn «Đăng tay», hoặc thêm kênh ở{" "}
          <Link to="/app/go/studio-setup" className="underline">Kênh &amp; mẫu</Link>.
        </p>
      ) : null}
      {channelId === "manual" ? (
        <p className="text-xs text-slate-500">Đăng tay: duyệt xong không gửi Buffer — tải video + chép caption ở cột «Đã duyệt», đăng xong bấm «Đã đăng».</p>
      ) : null}
      {act.msg ? <span className={`text-xs ${act.msg.startsWith("Lỗi") ? "text-red-700" : "text-emerald-700"}`}>{act.msg}</span> : null}
    </div>
  );
}
