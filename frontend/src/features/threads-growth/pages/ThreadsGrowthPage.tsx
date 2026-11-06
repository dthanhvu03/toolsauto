import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, LogIn, Settings } from "lucide-react";
import { Link } from "react-router-dom";
import { dangerBtnClass, ghostBtnClass, primaryBtnClass } from "@/shared/ui/controls";
import * as api from "../api/threadsGrowthApi";
import type { GrowthPost, GrowthStatus, Overview } from "../api/threadsGrowthApi";

const BOT_LABEL: Record<string, string> = { cashbot: "Cashbot", ai_store: "AI Store" };

const TABS: { key: GrowthStatus; label: string; hint: string }[] = [
  { key: "pending", label: "Chờ duyệt", hint: "Điểm dưới ngưỡng tự đăng — anh duyệt, sửa câu, hoặc bỏ." },
  { key: "approved", label: "Chờ đăng", hint: "Đã duyệt (tay hoặc tự động) — worker đăng lần lượt trong hạn mức." },
  { key: "posted", label: "Đã đăng", hint: "Reply đã lên Threads." },
  { key: "failed", label: "Lỗi", hint: "Đăng không được — xem lý do, duyệt lại để đăng lại." },
];

function when(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

function StatusBar({ ov }: { ov: Overview }) {
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["growth"] });
  const toggle = useMutation({
    mutationFn: () => api.toggleGrowth(!ov.enabled),
    onSuccess: () => { setErr(""); refresh(); },
    onError: (e: Error) => setErr(e.message),
  });
  const login = useMutation({
    mutationFn: api.startLogin,
    onSuccess: () => { setErr(""); refresh(); },
    onError: (e: Error) => setErr(e.message),
  });
  const q = ov.quota;
  const loginLabel = ov.login.logging_in
    ? "Đang mở cửa sổ đăng nhập…"
    : ov.login.ready
      ? "Đã đăng nhập Threads"
      : `Chưa đăng nhập (${ov.login.login_status})`;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={ov.enabled ? dangerBtnClass : primaryBtnClass}
          disabled={toggle.isPending || (!ov.enabled && !ov.login.ready)}
          onClick={() => toggle.mutate()}
        >
          {ov.enabled ? "Tắt kéo khách" : "Bật kéo khách"}
        </button>
        <span className={`text-sm font-medium ${ov.enabled ? "text-emerald-700" : "text-slate-500"}`}>
          {ov.enabled ? "● Đang chạy" : "○ Đang tắt"}
        </span>
        <span className={`text-sm ${ov.login.ready ? "text-slate-600" : "text-amber-700"}`}>{loginLabel}</span>
        <button
          type="button"
          className={`${ghostBtnClass} inline-flex items-center gap-1`}
          disabled={login.isPending || ov.login.logging_in || ov.enabled}
          title={ov.enabled ? "Tắt kéo khách trước khi đăng nhập lại" : "Mở Chromium trên màn hình Windows"}
          onClick={() => login.mutate()}
        >
          <LogIn className="h-3.5 w-3.5" /> Đăng nhập Threads
        </button>
        <Link to={ov.settings_url} className={`${ghostBtnClass} ml-auto inline-flex items-center gap-1`}>
          <Settings className="h-3.5 w-3.5" /> Từ khóa, câu A/B, hạn mức
        </Link>
      </div>
      <div className="mt-3 grid gap-2 text-sm text-slate-600 sm:grid-cols-3">
        <div>
          Hạn mức: <b>{q.posted_last_hour}/{ov.limits.max_replies_per_hour}</b> giờ ·{" "}
          <b>{q.posted_last_day}/{ov.limits.max_replies_per_day}</b> 24h
          {!q.allowed && <div className="text-amber-700">Chờ: {q.reason}</div>}
        </div>
        <div>
          Tự đăng khi điểm ≥ <b>{ov.worker.auto_post_min_relevance}</b> · bỏ dưới <b>{ov.limits.min_relevance}</b>
        </div>
        <div>
          Quét mỗi <b>{ov.worker.scan_interval_min}</b> phút · bài ≤ {ov.worker.max_post_age_hours}h
          {ov.worker.vietnamese_only && " · chỉ tiếng Việt"}
        </div>
      </div>
      {ov.login.login_error && !ov.login.ready && (
        <p className="mt-2 text-xs text-amber-700">{ov.login.login_error.slice(0, 200)}</p>
      )}
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
    </section>
  );
}

function AbStats({ ov }: { ov: Overview }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-800">Thử nghiệm A/B</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-3">Bot · biến thể</th>
              <th className="py-1 pr-3">Chờ duyệt</th>
              <th className="py-1 pr-3">Chờ đăng</th>
              <th className="py-1 pr-3">Đã đăng</th>
              <th className="py-1 pr-3">Bỏ</th>
              <th className="py-1">Lỗi</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(ov.stats).flatMap(([bot, variants]) =>
              (["A", "B"] as const).map((v) => {
                const c = variants[v] ?? {};
                return (
                  <tr key={`${bot}-${v}`} className="border-t border-slate-100">
                    <td className="py-1 pr-3">{BOT_LABEL[bot] ?? bot} · {v}</td>
                    <td className="py-1 pr-3">{c.pending ?? 0}</td>
                    <td className="py-1 pr-3">{c.approved ?? 0}</td>
                    <td className="py-1 pr-3 font-semibold">{c.posted ?? 0}</td>
                    <td className="py-1 pr-3">{c.rejected ?? 0}</td>
                    <td className="py-1">{c.failed ?? 0}</td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Khách bấm link reply sẽ vào bot với mã <code>?start=threads_…</code> — so số khách mới theo mã ở thống kê của bot.
      </p>
    </section>
  );
}

function PostCard({ post }: { post: GrowthPost }) {
  const qc = useQueryClient();
  const [text, setText] = useState(post.actual_reply || post.suggested_reply);
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

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <header className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold text-slate-700">#{post.id}</span>
        <span>{BOT_LABEL[post.target_bot]} · biến thể {post.variant}</span>
        <span>điểm {post.relevance_score}</span>
        {post.auto_approved === 1 && <span className="text-emerald-700">tự duyệt</span>}
        <a href={post.post_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-indigo-600">
          @{post.author} <ExternalLink className="h-3 w-3" />
        </a>
        <span className="ml-auto">{when(post.posted_at || post.post_created_at || post.created_at)}</span>
      </header>
      <p className="mt-2 whitespace-pre-line text-sm text-slate-800">
        {post.content.length > 500 ? `${post.content.slice(0, 500)}…` : post.content}
      </p>

      {editable ? (
        <textarea
          className="mt-3 w-full rounded-lg border border-slate-200 p-2 text-sm"
          rows={3}
          maxLength={500}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      ) : (
        <p className="mt-3 rounded-lg bg-indigo-50 p-2 text-sm text-indigo-900">💬 {post.actual_reply || post.suggested_reply}</p>
      )}
      {post.error_message && post.status === "failed" && (
        <p className="mt-1 text-xs text-red-600">Lỗi: {post.error_message}</p>
      )}
      {post.ai_analysis && <p className="mt-1 text-xs text-slate-400">{post.ai_analysis}</p>}

      <footer className="mt-3 flex flex-wrap items-center gap-2">
        {editable && (
          <button type="button" className={primaryBtnClass} disabled={busy || !text.trim()} onClick={() => approve.mutate()}>
            {post.status === "failed" ? "Đăng lại" : "Duyệt đăng"}
          </button>
        )}
        {editable && (
          <button type="button" className={ghostBtnClass} disabled={busy} onClick={() => swap.mutate()}>
            AI viết lại theo {post.variant === "A" ? "B" : "A"}
          </button>
        )}
        {(editable || post.status === "approved") && (
          <button type="button" className={dangerBtnClass} disabled={busy} onClick={() => reject.mutate()}>
            Bỏ
          </button>
        )}
        {post.reply_url && (
          <a href={post.reply_url} target="_blank" rel="noreferrer" className={`${ghostBtnClass} inline-flex items-center gap-1`}>
            Xem reply <ExternalLink className="h-3 w-3" />
          </a>
        )}
        {err && <span className="text-sm text-red-600">{err}</span>}
      </footer>
    </article>
  );
}

export function ThreadsGrowthPage() {
  const [tab, setTab] = useState<GrowthStatus>("pending");
  const ov = useQuery({ queryKey: ["growth", "overview"], queryFn: api.fetchOverview, refetchInterval: 15_000 });
  const posts = useQuery({ queryKey: ["growth", "posts", tab], queryFn: () => api.fetchPosts(tab), refetchInterval: 15_000 });
  const current = TABS.find((t) => t.key === tab)!;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Threads — Kéo khách</h1>
        <p className="text-sm text-slate-500">
          Tìm bài trên Threads theo từ khóa, AI viết reply giới thiệu Cashbot / AI Pass Store, bài đủ điểm tự đăng.
        </p>
      </div>

      {ov.isError && <p className="text-sm text-red-600">{(ov.error as Error).message}</p>}
      {ov.data && <StatusBar ov={ov.data} />}

      <nav className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => {
          const n = ov.data?.counts[t.key as keyof Overview["counts"]];
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${
                tab === t.key ? "border-indigo-600 font-semibold text-indigo-700" : "border-transparent text-slate-600"
              }`}
            >
              {t.label}
              {n ? <span className="ml-1 rounded-full bg-slate-100 px-1.5 text-xs">{n}</span> : null}
            </button>
          );
        })}
      </nav>
      <p className="-mt-2 text-xs text-slate-500">{current.hint}</p>

      {posts.isLoading && <p className="text-sm text-slate-500">Đang tải…</p>}
      {posts.data && posts.data.items.length === 0 && (
        <p className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
          Chưa có bài nào ở mục này.
        </p>
      )}
      <div className="flex flex-col gap-3">
        {posts.data?.items.map((p) => <PostCard key={`${p.id}-${p.status}-${p.variant}`} post={p} />)}
      </div>

      {ov.data && <AbStats ov={ov.data} />}
    </div>
  );
}
