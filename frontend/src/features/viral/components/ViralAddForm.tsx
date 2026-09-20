import { useState } from "react";
import { inputClass, primaryBtnClass } from "@/shared/ui/controls";

export function ViralAddForm({
  busy,
  onAdd,
  onProcessNew,
}: {
  busy: boolean;
  onAdd: (url: string, processNow: boolean) => void;
  onProcessNew: () => void;
}) {
  const [url, setUrl] = useState("");
  const [processNow, setProcessNow] = useState(false);

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-4">
      <input
        className={inputClass}
        placeholder="Dán link TikTok / YouTube / Facebook…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <label className="flex items-center gap-1 text-xs text-slate-600">
        <input type="checkbox" checked={processNow} onChange={(e) => setProcessNow(e.target.checked)} />
        Xử lý ngay
      </label>
      <button
        type="button"
        className={primaryBtnClass}
        disabled={busy || !url.trim()}
        onClick={() => {
          onAdd(url.trim(), processNow);
          setUrl("");
        }}
      >
        Thêm link
      </button>
      <button type="button" className={primaryBtnClass} disabled={busy} onClick={onProcessNew}>
        Xử lý NEW
      </button>
    </div>
  );
}
