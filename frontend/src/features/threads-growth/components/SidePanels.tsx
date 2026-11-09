import { useState, type ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import type { Followup, Overview, OwnPost } from "../api/threadsGrowthApi";
import { BOT_LABEL, when } from "../lib/format";

function Box({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      <div className="mt-2">{children}</div>
    </section>
  );
}

const Empty = ({ children }: { children: ReactNode }) => <p className="text-sm text-slate-400">{children}</p>;

export function RecentCustomers({ rep }: { rep: Overview["customers"] }) {
  const [all, setAll] = useState(false);
  if (!rep) return null;
  const list = all ? rep.customers : rep.customers.slice(0, 8);
  return (
    <Box title={`Khách mới từ Threads · ${rep.total}`} hint={`${rep.last_24h} trong 24 giờ · ${rep.active} đã dùng bot`}>
      {list.length ? (
        <ul className="divide-y divide-slate-100 text-sm">
          {list.map((c) => (
            <li key={`${c.bot}-${c.user_id}`} className="py-1.5">
              <div className="flex items-center gap-2">
                <span className={cn("h-2 w-2 shrink-0 rounded-full", c.active ? "bg-emerald-500" : "bg-slate-300")} />
                <span className="truncate font-medium text-slate-800">{c.username ? `@${c.username}` : `id ${c.user_id}`}</span>
                <span className="ml-auto shrink-0 text-xs text-slate-400">{when(c.joined_at)}</span>
              </div>
              <div className="pl-4 text-xs text-slate-500">
                {BOT_LABEL[c.bot]} · {c.channel} · <span className={c.active ? "text-emerald-700" : undefined}>{c.activity}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>Chưa có khách nào vào bot qua link Threads.</Empty>
      )}
      {rep.customers.length > 8 && (
        <button type="button" className="mt-2 text-xs text-indigo-600" onClick={() => setAll(!all)}>
          {all ? "thu gọn" : `xem cả ${rep.customers.length} khách`}
        </button>
      )}
    </Box>
  );
}

const FU_STATUS: Record<string, string> = { answered: "đã trả lời", skipped: "bỏ qua", failed: "lỗi" };

export function Followups({ items }: { items: Followup[] }) {
  return (
    <Box title="Người trả lời reply của mình" hint="AI trả lời câu hỏi, bỏ qua cảm ơn / spam.">
      {items.length ? (
        <ul className="space-y-2 text-sm">
          {items.map((f) => (
            <li key={f.id} className="rounded-xl bg-slate-50 p-2">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <a href={f.post_url} target="_blank" rel="noreferrer" className="font-medium text-indigo-600">@{f.author}</a>
                <span className={f.status === "answered" ? "text-emerald-700" : f.status === "failed" ? "text-red-600" : undefined}>
                  {FU_STATUS[f.status] ?? f.status}
                </span>
                <span className="ml-auto">{when(f.created_at)}</span>
              </div>
              <p className="mt-1 text-slate-700">«{f.comment}»</p>
              {f.reply_text && <p className="mt-1 text-slate-500">→ {f.reply_text}</p>}
            </li>
          ))}
        </ul>
      ) : (
        <Empty>Chưa ghi nhận ai trả lời.</Empty>
      )}
    </Box>
  );
}

const OWN_STATUS: Record<string, string> = { posted: "đã đăng", failed: "lỗi", skipped: "bỏ" };

export function OwnPosts({ items }: { items: OwnPost[] }) {
  return (
    <Box title="Bài riêng trên tài khoản" hint="Deal từ kho Cashbot / nhắc dịp sale — theo khung giờ trong ⚙️.">
      {items.length ? (
        <ul className="space-y-2 text-sm">
          {items.slice(0, 5).map((p) => (
            <li key={p.id} className="rounded-xl bg-slate-50 p-2">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span>{p.kind === "sale" ? "nhắc sale" : "deal"} · {p.slot}</span>
                <span className={p.status === "posted" ? "text-emerald-700" : "text-amber-700"}>{OWN_STATUS[p.status] ?? p.status}</span>
                {p.post_url && (
                  <a href={p.post_url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-0.5 text-indigo-600">
                    xem <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              <p className="mt-1 line-clamp-2 whitespace-pre-line text-slate-700">{p.text}</p>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>Chưa có bài nào.</Empty>
      )}
    </Box>
  );
}
