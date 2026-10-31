import { Clock, Copy, Download, Film } from "lucide-react";
import { Link } from "react-router-dom";
import { dangerBtnClass, ghostBtnClass } from "@/shared/ui/controls";
import { projectDownloadUrl, projectPosterUrl } from "../api/studioApi";
import { mmss, STATUS_LABEL, STATUS_STYLE } from "../lib/status";
import { TechTags } from "./TechTags";
import type { ProjectRow } from "../types/studio.types";

// nút nhỏ một dòng — thẻ hẹp (5 cột) vẫn vừa hai nút cạnh nhau
const tight = "inline-flex flex-1 items-center justify-center gap-1 whitespace-nowrap px-2 text-xs";

/** Caption + hashtag để dán khi đăng tay. */
function postText(p: ProjectRow): string {
  return [p.caption ?? "", (p.hashtags ?? []).join(" ")].filter(Boolean).join("\n\n");
}

export function ProjectCard({
  p,
  busy,
  onApprove,
  onReject,
  onPosted,
  onNotice,
}: {
  p: ProjectRow;
  busy: boolean;
  onApprove: (p: ProjectRow) => void;
  onReject: (id: number) => void;
  onPosted: (id: number) => void;
  onNotice: (msg: string) => void;
}) {
  const manual = p.channel_id == null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(postText(p));
      onNotice("Đã chép caption + hashtag.");
    } catch {
      onNotice("Lỗi: trình duyệt không cho chép — mở «Sửa» để chép tay.");
    }
  };
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <Link to={`/app/go/studio/${p.id}`} className="relative block aspect-[9/16] max-h-80 bg-slate-900">
        {p.has_video ? (
          <img
            src={projectPosterUrl(p.id, p.rendered_at)}
            alt=""
            loading="lazy"
            className="size-full object-cover"
          />
        ) : (
          <span className="flex size-full items-center justify-center text-slate-500">
            <Film className="size-8" />
          </span>
        )}
        <span className={`absolute left-2 top-2 rounded px-1.5 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[p.status]}`}>
          {STATUS_LABEL[p.status]}
        </span>
        {p.duration ? (
          <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[11px] text-white">
            <Clock className="size-3" /> {mmss(p.duration)}
          </span>
        ) : null}
      </Link>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <div className="flex items-center justify-between text-xs">
          {manual ? (
            <span className="rounded bg-amber-50 px-1.5 py-0.5 font-semibold text-amber-800">Đăng tay</span>
          ) : (
            <span className="font-semibold text-slate-800">{p.channel}</span>
          )}
          <span className="font-mono text-slate-400">#{p.id}</span>
        </div>
        {p.parent_project_id ? (
          <span className="w-fit rounded bg-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-700">Biến thể của #{p.parent_project_id}</span>
        ) : null}
        <TechTags tags={p.tags ?? []} />
        <p className="line-clamp-3 text-xs text-slate-600">
          {p.status === "FAILED" ? <span className="text-red-700">{p.error}</span> : p.caption || <i className="text-slate-400">Chưa có caption</i>}
        </p>
        {p.status === "REVIEW" ? (
          <div className="mt-auto flex gap-1.5 pt-1">
            <button type="button" className={`${ghostBtnClass} flex-1 border-emerald-300 text-emerald-800`} disabled={busy} onClick={() => onApprove(p)}>
              Duyệt
            </button>
            <Link to={`/app/go/studio/${p.id}`} className={`${ghostBtnClass} flex flex-1 items-center justify-center`}>
              Sửa
            </Link>
            <button type="button" className={dangerBtnClass} disabled={busy} onClick={() => onReject(p.id)}>
              Bỏ
            </button>
          </div>
        ) : null}
        {manual && p.status === "APPROVED" ? (
          <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
            <a href={projectDownloadUrl(p.id)} download className={`${ghostBtnClass} ${tight}`}>
              <Download className="size-3.5" /> Tải video
            </a>
            <button type="button" className={`${ghostBtnClass} ${tight}`} onClick={copy}>
              <Copy className="size-3.5" /> Chép caption
            </button>
            <button
              type="button"
              className={`${ghostBtnClass} w-full border-emerald-300 text-emerald-800`}
              disabled={busy}
              onClick={() => onPosted(p.id)}
              title="Đăng xong trên TikTok / Facebook thì bấm — thẻ sang cột «Đã đăng»"
            >
              Đã đăng
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
