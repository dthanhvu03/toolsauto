import { Copy, Download } from "lucide-react";
import { ghostBtnClass } from "@/shared/ui/controls";
import { projectDownloadUrl } from "../api/studioApi";

// nút nhỏ một dòng — thẻ hẹp (5 cột) vẫn vừa hai nút cạnh nhau
const tight = "inline-flex flex-1 items-center justify-center gap-1 whitespace-nowrap px-2 text-xs";

/** Caption + hashtag để dán khi đăng tay. */
function postText(caption: string | null, hashtags: string[]): string {
  return [caption ?? "", hashtags.join(" ")].filter(Boolean).join("\n\n");
}

/**
 * Dự án đăng tay đã duyệt (PLAN-113): tải video về, chép caption + hashtag, đăng xong bấm «Đã đăng».
 * Dùng ở thẻ bảng Studio và trình edit.
 */
export function ManualPostActions({
  id,
  caption,
  hashtags,
  busy,
  onPosted,
  onNotice,
}: {
  id: number;
  caption: string | null;
  hashtags: string[];
  busy: boolean;
  onPosted: () => void;
  onNotice: (msg: string) => void;
}) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(postText(caption, hashtags));
      onNotice("Đã chép caption + hashtag.");
    } catch {
      onNotice("Lỗi: trình duyệt không cho chép — bôi đen caption để chép tay.");
    }
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      <a href={projectDownloadUrl(id)} download className={`${ghostBtnClass} ${tight}`}>
        <Download className="size-3.5" /> Tải video
      </a>
      <button type="button" className={`${ghostBtnClass} ${tight}`} onClick={copy}>
        <Copy className="size-3.5" /> Chép caption
      </button>
      <button
        type="button"
        className={`${ghostBtnClass} w-full border-emerald-300 text-emerald-800`}
        disabled={busy}
        onClick={onPosted}
        title="Đăng xong trên TikTok / Facebook thì bấm — dự án sang «Đã đăng»"
      >
        Đã đăng
      </button>
    </div>
  );
}
