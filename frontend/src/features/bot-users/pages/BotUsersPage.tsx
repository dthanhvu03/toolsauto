import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { cn } from "@/shared/lib/cn";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { SearchField } from "@/shared/ui/SearchField";
import { fetchBotUsers, type BotKey, type BotSummary, type Person } from "../api/botUsersApi";

const BOTS: BotKey[] = ["cashbot_tg", "cashbot_zalo", "ai_store"];
const SHORT: Record<BotKey, string> = { cashbot_tg: "Cashbot TG", cashbot_zalo: "Cashbot Zalo", ai_store: "AI Store" };
const DOT: Record<BotKey, string> = { cashbot_tg: "bg-indigo-500", cashbot_zalo: "bg-sky-400", ai_store: "bg-emerald-500" };

const vnd = (n: number) => `${n.toLocaleString("vi-VN")}đ`;

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", hour12: false, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

/** Mã ?start= → chữ dễ đọc. Mã lạ giữ nguyên. */
function sourceLabel(code: string): string {
  const m = /^threads_(cb|ai)_(.+)$/.exec(code);
  if (m) return `Threads · ${m[2].replace(/_/g, " ")}`;
  return code;
}

function SummaryTable({ bots, total, days }: { bots: BotSummary[]; total: BotSummary; days: number }) {
  const cols: [keyof BotSummary, string][] = [
    ["total", "Tổng"], ["new_24h", "Mới 24h"], ["new_7d", "Mới 7 ngày"], ["active_7d", `Đang dùng ${days} ngày`], ["buyers", "Có đơn"],
  ];
  return (
    <Panel>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs text-slate-500">
          <tr>
            <th className="px-4 py-2 font-medium">Bot</th>
            {cols.map(([, label]) => <th key={label} className="px-3 py-2 text-right font-medium">{label}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {[...bots, total].map((s) => (
            <tr key={s.bot} className={s.bot === "all" ? "bg-slate-50 font-semibold" : undefined}>
              <td className="px-4 py-2">
                {s.bot === "all" ? "Tổng" : (
                  <span className="inline-flex items-center gap-2">
                    <span className={cn("h-2 w-2 rounded-full", DOT[s.bot as BotKey])} />{s.label}
                  </span>
                )}
              </td>
              {cols.map(([key]) => (
                <td key={key} className={cn("px-3 py-2 text-right tabular-nums", key === "total" && "text-slate-900")}>
                  {s[key] as number}
                  {key === "buyers" && s.total ? <span className="ml-1 text-xs font-normal text-slate-400">{Math.round((s.buyers * 100) / s.total)}%</span> : null}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-4 py-2 text-[11px] text-slate-400">
        Đang dùng: Cashbot = có tạo link · AI Store = có đơn hoặc nạp tiền. Có đơn: Cashbot = đơn sàn ghi nhận (không tính huỷ) · AI Store = đơn đã giao.
        Một người dùng nhiều bot được đếm ở mỗi bot.
      </p>
    </Panel>
  );
}

function DailyChart({ days }: { days: ({ day: string } & Record<BotKey, number>)[] }) {
  const rows = [...days].reverse(); // cũ → mới, trái → phải
  const max = Math.max(1, ...rows.map((d) => BOTS.reduce((n, b) => n + d[b], 0)));
  return (
    <Panel className="p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">Khách mới theo ngày · {rows.length} ngày</h2>
        <div className="flex gap-3 text-[11px] text-slate-500">
          {BOTS.map((b) => <span key={b} className="inline-flex items-center gap-1"><span className={cn("h-2 w-2 rounded-sm", DOT[b])} />{SHORT[b]}</span>)}
        </div>
      </div>
      <div className="mt-3 flex h-36 items-end gap-1">
        {rows.map((d) => {
          const sum = BOTS.reduce((n, b) => n + d[b], 0);
          return (
            <div key={d.day} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end"
              title={`${d.day}: ${BOTS.map((b) => `${SHORT[b]} ${d[b]}`).join(" · ")}`}>
              <span className="text-[10px] tabular-nums text-slate-500">{sum || ""}</span>
              <div className="flex w-full flex-col-reverse overflow-hidden rounded-t" style={{ height: `${(sum / max) * 100}%` }}>
                {BOTS.map((b) => d[b] ? <div key={b} className={DOT[b]} style={{ height: `${(d[b] / sum) * 100}%` }} /> : null)}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex gap-1">
        {rows.map((d) => <span key={d.day} className="min-w-0 flex-1 truncate text-center text-[10px] text-slate-400">{d.day}</span>)}
      </div>
    </Panel>
  );
}

function Sources({ sources }: { sources: Record<BotKey, { source: string; count: number }[]> }) {
  return (
    <Panel className="p-4">
      <h2 className="text-sm font-semibold text-slate-800">Theo nguồn</h2>
      <p className="text-xs text-slate-500">Mã link <code>?start=</code> lúc khách vào lần đầu. «tự vào» = không có mã (tìm bot, được giới thiệu, Zalo…).</p>
      <div className="mt-3 grid gap-4 sm:grid-cols-3">
        {BOTS.map((b) => {
          const rows = sources[b] ?? [];
          const all = rows.reduce((n, r) => n + r.count, 0);
          return (
            <div key={b}>
              <div className="mb-1 flex items-center gap-2 text-xs font-medium text-slate-600"><span className={cn("h-2 w-2 rounded-full", DOT[b])} />{SHORT[b]}</div>
              <ul className="space-y-1 text-xs">
                {rows.slice(0, 8).map((r) => (
                  <li key={r.source}>
                    <div className="flex justify-between gap-2"><span className="truncate text-slate-700" title={r.source}>{sourceLabel(r.source)}</span><span className="tabular-nums text-slate-500">{r.count}</span></div>
                    <div className="mt-0.5 h-1 rounded bg-slate-100"><div className={cn("h-1 rounded", DOT[b])} style={{ width: `${(r.count / Math.max(1, all)) * 100}%` }} /></div>
                  </li>
                ))}
                {!rows.length && <li className="text-slate-400">Chưa có khách.</li>}
              </ul>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function PeopleTable({ people, matched }: { people: Person[]; matched: number }) {
  return (
    <Panel>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Khách</th>
              <th className="px-3 py-2 font-medium">Bot</th>
              <th className="px-3 py-2 font-medium">Nguồn</th>
              <th className="px-3 py-2 font-medium">Vào lúc</th>
              <th className="px-3 py-2 font-medium">Dùng gần nhất</th>
              <th className="px-3 py-2 text-right font-medium">Link / đơn</th>
              <th className="px-3 py-2 text-right font-medium">Đã chi · ví</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {people.map((p) => (
              <tr key={`${p.bot}-${p.user_id}`}>
                <td className="px-4 py-1.5">
                  <span className="inline-flex items-center gap-2">
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", p.active ? "bg-emerald-500" : "bg-slate-300")} title={p.active ? "đang dùng" : "chưa dùng gần đây"} />
                    {p.bot === "ai_store" ? (
                      <span className="font-medium text-slate-800">{p.name}</span>
                    ) : (
                      <a href={`/cashback/users/${p.user_id}`} className="font-medium text-indigo-700 hover:underline">{p.name}</a>
                    )}
                  </span>
                  <div className="pl-4 font-mono text-[10px] text-slate-400">{p.user_id}</div>
                </td>
                <td className="px-3 py-1.5 text-xs text-slate-600">{SHORT[p.bot]}</td>
                <td className="px-3 py-1.5 text-xs text-slate-600" title={p.source}>{sourceLabel(p.source)}</td>
                <td className="px-3 py-1.5 text-xs text-slate-500">{when(p.joined_at)}</td>
                <td className="px-3 py-1.5 text-xs text-slate-500">{when(p.last_used_at)}</td>
                <td className="px-3 py-1.5 text-right text-xs tabular-nums">
                  {p.bot === "ai_store" ? `${p.orders} đơn` : `${p.uses} link · ${p.orders} đơn`}
                </td>
                <td className="px-3 py-1.5 text-right text-xs tabular-nums text-slate-600">
                  {p.bot === "ai_store" ? `${vnd(p.spent ?? 0)} · ${vnd(p.balance ?? 0)}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!people.length && <p className="p-6 text-center text-sm text-slate-500">Không có khách khớp.</p>}
      {matched > people.length && <p className="px-4 py-2 text-xs text-slate-400">Hiện {people.length}/{matched} khách — gõ tên hoặc ID để lọc.</p>}
    </Panel>
  );
}

export function BotUsersPage() {
  const [typed, setTyped] = useState("");
  const [q, setQ] = useState("");
  const [bot, setBot] = useState<"" | BotKey>("");
  const rep = useQuery({
    queryKey: ["bot-users", q, bot],
    queryFn: () => fetchBotUsers(q, bot),
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
  });
  const d = rep.data;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader title="Khách các bot" subtitle="Cashbot (Telegram + Zalo) và AI Pass Store — tổng khách, khách mới, nguồn, ai đang dùng." />
      <QueryBody
        isLoading={rep.isLoading}
        isError={rep.isError || (!rep.isLoading && !d?.bots)}
        loadingText="Đang đếm khách…"
        errorText="Không tải được /bot-users/api/report. Web vừa cập nhật thì chạy pm2 restart Web_Dashboard."
      >
        {d?.bots ? (
          <>
            {d.errors.map((e) => <p key={e} className="text-sm text-red-600">{e}</p>)}
            <SummaryTable bots={d.bots} total={d.total} days={d.active_days} />
            <div className="grid gap-4 lg:grid-cols-2">
              <DailyChart days={d.days} />
              <Sources sources={d.sources} />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <h2 className="mr-2 text-sm font-semibold text-slate-800">Danh sách khách</h2>
              {([["", "Tất cả"], ...BOTS.map((b) => [b, SHORT[b]])] as [string, string][]).map(([key, label]) => (
                <button key={key || "all"} type="button" onClick={() => setBot(key as "" | BotKey)}
                  className={cn("rounded-full px-2.5 py-1 text-xs", bot === key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200")}>
                  {label}
                </button>
              ))}
              <div className="ml-auto flex gap-2">
                <SearchField placeholder="Tên, @username, ID hoặc mã nguồn" value={typed} onChange={setTyped} onSubmit={() => setQ(typed)} />
              </div>
            </div>
            <PeopleTable people={d.people} matched={d.matched} />
          </>
        ) : null}
      </QueryBody>
    </div>
  );
}
