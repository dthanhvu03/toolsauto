import { Image as ImageIcon, Music, Video } from "lucide-react";
import { useState } from "react";
import { cn } from "@/shared/lib/cn";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { assetFileUrl } from "../api/studioApi";
import { UploadBox } from "../components/UploadBox";
import { useAssets } from "../hooks/useStudio";
import { mmss } from "../lib/status";
import type { Asset } from "../types/studio.types";

const KINDS = [
  { key: "", label: "Tất cả" },
  { key: "video", label: "Video" },
  { key: "image", label: "Ảnh / logo" },
  { key: "audio", label: "Âm thanh" },
];
const ORIGIN: Record<string, string> = { reup: "reup", upload: "tự quay", brand: "nguyên liệu", dub: "lồng tiếng", ai: "AI" };

function Preview({ a }: { a: Asset }) {
  if (a.kind === "image") return <img src={assetFileUrl(a.id)} alt="" loading="lazy" className="size-full object-contain" />;
  if (a.kind === "audio")
    return (
      <div className="flex size-full flex-col items-center justify-center gap-2 p-2">
        <Music className="size-6 text-slate-400" />
        <audio src={assetFileUrl(a.id)} controls preload="none" className="w-full" />
      </div>
    );
  return <video src={assetFileUrl(a.id)} preload="metadata" muted controls className="size-full object-contain" />;
}

export function StudioAssetsPage() {
  const [kind, setKind] = useState("");
  const q = useAssets(kind);
  const items = q.data?.assets ?? [];
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Nguyên liệu" subtitle="Video nguồn, logo, intro / outro, nhạc, tiếng lồng — dùng lại cho mọi dự án" />
      <div className="mt-4">
        <UploadBox channels={[]} brand />
      </div>
      <div className="mt-4 flex gap-1.5">
        {KINDS.map((k) => (
          <button
            key={k.key}
            type="button"
            onClick={() => setKind(k.key)}
            className={cn("rounded-full border px-3 py-1.5 text-sm", kind === k.key ? "border-indigo-300 bg-indigo-50 text-indigo-800" : "border-slate-200 bg-white text-slate-600")}
          >
            {k.label}
          </button>
        ))}
      </div>
      <QueryBody isLoading={q.isLoading} isError={q.isError} loadingText="Đang tải…" errorText="Không tải được nguyên liệu">
        {items.length === 0 ? (
          <p className="mt-8 text-center text-sm text-slate-400">Chưa có nguyên liệu.</p>
        ) : (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {items.map((a) => (
              <Panel key={a.id}>
                <div className="aspect-video bg-slate-100">
                  <Preview a={a} />
                </div>
                <div className="p-2.5 text-xs">
                  <div className="flex items-center justify-between gap-1">
                    <span className="truncate font-medium text-slate-800" title={a.title ?? ""}>
                      {a.kind === "video" ? <Video className="mr-1 inline size-3.5" /> : a.kind === "image" ? <ImageIcon className="mr-1 inline size-3.5" /> : null}
                      {a.title || `#${a.id}`}
                    </span>
                    <span className="font-mono text-slate-400">#{a.id}</span>
                  </div>
                  <div className="mt-0.5 text-slate-500">
                    {ORIGIN[a.origin] ?? a.origin}
                    {a.duration ? ` · ${mmss(a.duration)}` : ""}
                    {a.width ? ` · ${a.width}×${a.height}` : ""}
                    {a.credit ? ` · ${a.credit}` : ""}
                  </div>
                </div>
              </Panel>
            ))}
          </div>
        )}
      </QueryBody>
    </div>
  );
}
