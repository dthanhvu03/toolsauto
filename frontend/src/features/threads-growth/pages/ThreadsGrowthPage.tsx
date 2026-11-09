import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/shared/lib/cn";
import { PageHeader } from "@/shared/ui/PageHeader";
import { ScreenSettingsButton } from "@/features/settings/components/ScreenSettingsButton";
import * as api from "../api/threadsGrowthApi";
import type { GrowthStatus, Overview } from "../api/threadsGrowthApi";
import { BotFunnel } from "../components/BotFunnel";
import { ControlBar } from "../components/ControlBar";
import { PostCard } from "../components/PostCard";
import { AccountsPanel } from "../components/AccountsPanel";
import { Followups, OwnPosts, RecentCustomers } from "../components/SidePanels";
import { BOT_LABEL } from "../lib/format";

const TABS: { key: GrowthStatus; label: string; hint: string }[] = [
  { key: "pending", label: "Cần duyệt", hint: "Điểm dưới ngưỡng tự đăng — duyệt, sửa câu, hoặc bỏ." },
  { key: "approved", label: "Chờ đăng", hint: "Đã duyệt — worker đăng lần lượt trong hạn mức." },
  { key: "posted", label: "Đã đăng", hint: "Reply đã lên Threads." },
  { key: "failed", label: "Lỗi", hint: "Đăng không được — xem lý do, duyệt lại để đăng lại." },
];

type BotFilter = "all" | "cashbot" | "ai_store";

export function ThreadsGrowthPage() {
  const ov = useQuery({ queryKey: ["growth", "overview"], queryFn: api.fetchOverview, refetchInterval: 15_000 });
  const own = useQuery({ queryKey: ["growth", "own-posts"], queryFn: api.fetchOwnPosts, refetchInterval: 30_000 });
  const fu = useQuery({ queryKey: ["growth", "followups"], queryFn: api.fetchFollowups, refetchInterval: 30_000 });
  const [picked, setPicked] = useState<GrowthStatus | null>(null);
  const [bot, setBot] = useState<BotFilter>("all");
  const [account, setAccount] = useState("all");
  const accounts = ov.data?.accounts ?? [];

  const counts = ov.data?.counts;
  // Mặc định: có việc cần duyệt thì mở «Cần duyệt», không thì xem «Đã đăng».
  const tab: GrowthStatus = picked ?? (counts && !counts.pending ? "posted" : "pending");
  const posts = useQuery({ queryKey: ["growth", "posts", tab], queryFn: () => api.fetchPosts(tab), refetchInterval: 15_000 });
  const items = (posts.data?.items ?? []).filter((p) => bot === "all" || p.target_bot === bot);
  const current = TABS.find((t) => t.key === tab)!;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader
        title="Threads — Kéo khách"
        subtitle="Tìm bài trên Threads, AI đọc nhu cầu người viết rồi reply giới thiệu Cashbot / AI Pass Store."
        actions={<ScreenSettingsButton screen="threads-growth" />}
      />

      {ov.isError && <p className="text-sm text-red-600">{(ov.error as Error).message}</p>}
      {ov.isLoading && <p className="text-sm text-slate-500">Đang tải…</p>}
      {ov.data && <ControlBar ov={ov.data} own={own.data?.items ?? []} />}
      {ov.data && accounts.length > 1 && (
        <div className="flex flex-wrap items-center gap-1 text-xs">
          <span className="mr-1 text-slate-500">Hiệu quả theo:</span>
          {[{ key: "all", label: "Tất cả tài khoản" }, ...accounts.map((a) => ({ key: a.key, label: `@${a.handle}` }))].map((o) => (
            <button
              key={o.key}
              type="button"
              onClick={() => setAccount(o.key)}
              className={cn(
                "rounded-full px-2.5 py-1",
                account === o.key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
      {ov.data && <BotFunnel ov={ov.data} account={account} />}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <main className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-end gap-2 border-b border-slate-200">
            {TABS.map((t) => {
              const n = counts?.[t.key as keyof Overview["counts"]];
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setPicked(t.key)}
                  className={cn(
                    "-mb-px border-b-2 px-3 py-2 text-sm",
                    tab === t.key ? "border-indigo-600 font-semibold text-indigo-700" : "border-transparent text-slate-600 hover:text-slate-900",
                  )}
                >
                  {t.label}
                  {n ? (
                    <span className={cn("ml-1 rounded-full px-1.5 text-xs", t.key === "failed" ? "bg-red-100 text-red-700" : "bg-slate-100")}>
                      {n}
                    </span>
                  ) : null}
                </button>
              );
            })}
            <div className="mb-1.5 ml-auto flex gap-1">
              {(["all", "cashbot", "ai_store"] as const).map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => setBot(b)}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-xs",
                    bot === b ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                  )}
                >
                  {b === "all" ? "Tất cả" : BOT_LABEL[b]}
                </button>
              ))}
            </div>
          </div>
          <p className="-mt-1 text-xs text-slate-500">{current.hint}</p>

          {posts.isLoading && <p className="text-sm text-slate-500">Đang tải…</p>}
          {posts.data && items.length === 0 && (
            <p className="rounded-2xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
              Không có bài nào ở mục này.
            </p>
          )}
          {items.map((p) => (
            <PostCard key={`${p.id}-${p.status}-${p.variant}`} post={p} />
          ))}
        </main>

        <aside className="flex flex-col gap-4">
          {ov.data && <RecentCustomers rep={ov.data.customers} />}
          <AccountsPanel accounts={accounts} />
          <Followups items={fu.data?.items ?? []} />
          <OwnPosts items={own.data?.items ?? []} />
        </aside>
      </div>
    </div>
  );
}
