import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/shared/lib/cn";
import * as api from "../api/threadsGrowthApi";
import type { AccountRole, GrowthAccount } from "../api/threadsGrowthApi";
import { BOT_LABEL } from "../lib/format";
import { Box } from "./SidePanels";

const BOTS = ["cashbot", "ai_store"] as const;

function AccountRow({ a }: { a: GrowthAccount }) {
  const qc = useQueryClient();
  const [copied, setCopied] = useState("");
  const [err, setErr] = useState("");
  const save = useMutation({
    mutationFn: (changes: Partial<AccountRole>) => api.updateAccount(a.key, changes),
    onSuccess: () => { setErr(""); qc.invalidateQueries({ queryKey: ["growth"] }); },
    onError: (e: Error) => setErr(e.message),
  });
  const role = a.role;
  const copy = (url: string) => navigator.clipboard?.writeText(url).then(() => setCopied(url), () => setCopied(""));
  const toggleBot = (bot: string) => {
    if (!role) return;
    const next = role.bots.includes(bot) ? role.bots.filter((b) => b !== bot) : [...role.bots, bot];
    if (next.length) save.mutate({ bots: next });
  };
  const status = !a.login?.ready
    ? { text: `chưa đăng nhập (${a.login?.login_status ?? "?"})`, tone: "bg-amber-100 text-amber-800" }
    : role?.enabled
      ? { text: "đang chạy", tone: "bg-emerald-100 text-emerald-800" }
      : { text: "đang tắt", tone: "bg-slate-100 text-slate-500" };

  return (
    <li className="rounded-xl border border-slate-100 p-3">
      <div className="flex items-center gap-2">
        <a href={`https://www.threads.com/@${a.handle}`} target="_blank" rel="noreferrer" className="font-medium text-indigo-600">
          @{a.handle}
        </a>
        <span className={cn("rounded-full px-1.5 text-xs", status.tone)}>{status.text}</span>
        {role && (
          <button
            type="button"
            role="switch"
            aria-checked={role.enabled}
            aria-label={`Bật / tắt @${a.handle}`}
            disabled={save.isPending}
            onClick={() => save.mutate({ enabled: !role.enabled })}
            className={cn(
              "relative ml-auto h-5 w-9 shrink-0 rounded-full transition disabled:opacity-50",
              role.enabled ? "bg-emerald-500" : "bg-slate-300",
            )}
          >
            <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition", role.enabled ? "left-4" : "left-0.5")} />
          </button>
        )}
      </div>

      {role && (
        <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
          <span className="text-slate-500">Mời:</span>
          {BOTS.map((b) => (
            <button
              key={b}
              type="button"
              disabled={save.isPending}
              onClick={() => toggleBot(b)}
              className={cn(
                "rounded-full px-2 py-0.5",
                role.bots.includes(b) ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500 hover:bg-slate-200",
              )}
            >
              {BOT_LABEL[b]}
            </button>
          ))}
        </div>
      )}
      {a.quota && (
        <p className="mt-1 text-xs text-slate-500">
          Reply 24h <b className="text-slate-700">{a.quota.posted_last_day}/{a.quota.max_per_day}</b> · 1h{" "}
          <b className="text-slate-700">{a.quota.posted_last_hour}/{a.quota.max_per_hour}</b>
          {role?.max_per_day == null && " (hạn mức chung)"}
          {role?.own_posts && " · có bài riêng"}
        </p>
      )}

      <div className="mt-2 space-y-1">
        {Object.entries(a.bio_links).map(([bot, url]) => (
          <button
            key={bot}
            type="button"
            onClick={() => copy(url)}
            className="flex w-full items-center gap-2 rounded-lg bg-slate-50 px-2 py-1 text-left text-xs hover:bg-slate-100"
            title={`Chép ${url}`}
          >
            <span className="shrink-0 text-slate-500">bio {BOT_LABEL[bot]}</span>
            <span className="truncate font-mono text-slate-700">{url.split("start=")[1] ?? url}</span>
            <span className="ml-auto shrink-0 text-indigo-600">{copied === url ? "đã chép" : "chép"}</span>
          </button>
        ))}
      </div>
      {err && <p className="mt-1 text-xs text-red-600">{err}</p>}
    </li>
  );
}

/** PLAN-167: vai từng tài khoản (bật/tắt, bot mời), hạn mức riêng, link bio đếm khách theo tài khoản. */
export function AccountsPanel({ accounts }: { accounts: GrowthAccount[] }) {
  if (!accounts.length) return null;
  return (
    <Box title="Tài khoản Threads" hint="Mỗi tài khoản mời bot nào, hạn mức riêng. Dán link bio vào bio để đếm khách theo tài khoản.">
      <ul className="space-y-2 text-sm">
        {accounts.map((a) => (
          <AccountRow key={a.key} a={a} />
        ))}
      </ul>
    </Box>
  );
}
