import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { dangerBtnClass, ghostBtnClass, primaryBtnClass } from "@/shared/ui/controls";
import * as api from "../api/threadsGrowthApi";
import type { GrowthPost } from "../api/threadsGrowthApi";
import { BOT_LABEL, fmtNum, parseAiRead, scoreTone, when } from "../lib/format";

function AiRead({ raw }: { raw: string | null }) {
  const read = parseAiRead(raw);
  if (!read) return null;
  if (!read.tags.length) return <p className="mt-2 text-xs text-slate-400">{read.raw}</p>;
  return (
    <div className="mt-2 flex flex-wrap gap-1" title={read.model}>
      {read.tags.map((t, i) => (
        <span
          key={i}
          className={cn(
            "rounded-md px-1.5 py-0.5 text-xs",
            t.label ? "bg-amber-50 text-amber-900" : "bg-slate-100 text-slate-600",
          )}
        >
          {t.label && <b className="font-medium">{t.label}: </b>}
          {t.text}
        </span>
      ))}
    </div>
  );
}

export function PostCard({ post }: { post: GrowthPost }) {
  const qc = useQueryClient();
  const [text, setText] = useState(post.actual_reply || post.suggested_reply);
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState("");
  const done = { onSuccess: () => { setErr(""); qc.invalidateQueries({ queryKey: ["growth"] }); }, onError: (e: Error) => setErr(e.message) };
  const approve = useMutation({ mutationFn: () => api.approvePost(post.id, text), ...done });
  const reject = useMutation({ mutationFn: () => api.rejectPost(post.id), ...done });
  const swap = useMutation({
    mutationFn: () => api.switchPost(post.id),
    onSuccess: (r) => { setText(r.post.suggested_reply); done.onSuccess(); },
    onError: done.onError,
  });
  const busy = approve.isPending || reject.isPending || swap.isPending;
  const editable = post.status === "pending" || post.status === "failed";
  const long = post.content.length > 280;

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <header className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className={cn("rounded-md px-1.5 py-0.5 font-semibold", scoreTone(post.relevance_score))}>
          {post.relevance_score} điểm
        </span>
        <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-slate-700">
          {BOT_LABEL[post.target_bot]} · {post.variant}
        </span>
        {post.auto_approved === 1 && <span className="text-emerald-700">tự duyệt</span>}
        <a href={post.post_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 font-medium text-indigo-600">
          @{post.author} <ExternalLink className="h-3 w-3" />
        </a>
        {post.reach > 0 && (
          <span title="Độ phủ = 3×reply + like của bài lúc quét">
            💬 {post.reply_count} · ♥ {post.like_count}
            {post.author_followers > 0 && ` · 👥 ${fmtNum(post.author_followers)}`}
          </span>
        )}
        <span className="ml-auto">#{post.id} · {when(post.posted_at || post.post_created_at || post.created_at)}</span>
      </header>

      <blockquote className="mt-3 border-l-2 border-slate-200 pl-3 text-sm text-slate-800">
        <p className={cn("whitespace-pre-line", !open && long && "line-clamp-4")}>{post.content}</p>
        {long && (
          <button type="button" className="mt-1 text-xs text-indigo-600" onClick={() => setOpen(!open)}>
            {open ? "thu gọn" : "xem hết"}
          </button>
        )}
      </blockquote>
      <AiRead raw={post.ai_analysis} />

      {editable ? (
        <textarea
          className="mt-3 w-full rounded-xl border border-indigo-200 bg-indigo-50/40 p-2 text-sm focus:border-indigo-400 focus:outline-none"
          rows={3}
          maxLength={500}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      ) : (
        <p className="mt-3 rounded-xl bg-indigo-50 px-3 py-2 text-sm text-indigo-950">{post.actual_reply || post.suggested_reply}</p>
      )}
      {post.error_message && post.status === "failed" && <p className="mt-1 text-xs text-red-600">Lỗi: {post.error_message}</p>}

      <footer className="mt-3 flex flex-wrap items-center gap-2">
        {editable && (
          <button type="button" className={primaryBtnClass} disabled={busy || !text.trim()} onClick={() => approve.mutate()}>
            {post.status === "failed" ? "Đăng lại" : "Duyệt đăng"}
          </button>
        )}
        {editable && (
          <button type="button" className={ghostBtnClass} disabled={busy} onClick={() => swap.mutate()}>
            AI viết lại kiểu {post.variant === "A" ? "B" : "A"}
          </button>
        )}
        {(editable || post.status === "approved") && (
          <button type="button" className={dangerBtnClass} disabled={busy} onClick={() => reject.mutate()}>
            Bỏ
          </button>
        )}
        {post.reply_url && (
          <a href={post.reply_url} target="_blank" rel="noreferrer" className={cn(ghostBtnClass, "inline-flex items-center gap-1")}>
            Xem reply trên Threads <ExternalLink className="h-3 w-3" />
          </a>
        )}
        {editable && <span className="ml-auto text-xs text-slate-400">{text.length}/500</span>}
        {err && <span className="text-sm text-red-600">{err}</span>}
      </footer>
    </article>
  );
}
