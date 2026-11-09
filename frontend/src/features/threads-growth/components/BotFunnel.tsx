import { ArrowRight } from "lucide-react";
import type { Overview } from "../api/threadsGrowthApi";
import { BOT_HINT, BOT_LABEL, pct } from "../lib/format";

function Step({ value, label, strong }: { value: number; label: string; strong?: boolean }) {
  return (
    <div className="text-center">
      <div className={strong ? "text-2xl font-semibold text-emerald-700" : "text-2xl font-semibold text-slate-800"}>{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

type Row = { posted: number; customers: number; active: number };

/** Mỗi bot một thẻ: reply đã đăng → khách mới → đã dùng bot. ``account`` = "all" hoặc key tài khoản (PLAN-167). */
export function BotFunnel({ ov, account }: { ov: Overview; account: string }) {
  const rep = ov.customers;
  const all = account === "all";
  return (
    <section className="grid gap-3 md:grid-cols-2">
      {Object.keys(ov.stats).map((bot) => {
        const st = ov.stats[bot];
        const cust = rep?.by_variant?.[bot] ?? {};
        const variant = (v: "A" | "B"): Row => ({
          posted: st[v]?.posted ?? 0,
          customers: cust[v]?.customers ?? 0,
          active: cust[v]?.active ?? 0,
        });
        const a = variant("A");
        const b = variant("B");
        // Tổng của bot: «tất cả» = mọi reply + mọi khách có mã (cả kênh bài riêng / bio);
        // một tài khoản = reply tài khoản đó đăng + khách vào qua mã của tài khoản đó.
        const accStats = ov.account_stats?.[account]?.[bot] ?? {};
        const accCust = rep?.by_account?.[account]?.[bot] ?? { customers: 0, active: 0 };
        // Cộng theo tài khoản (không đếm danh sách khách — danh sách bị cắt 100 dòng).
        const sum = Object.values(rep?.by_account ?? {}).reduce(
          (s, perBot) => ({ customers: s.customers + (perBot[bot]?.customers ?? 0), active: s.active + (perBot[bot]?.active ?? 0) }),
          { customers: 0, active: 0 },
        );
        const total: Row = all
          ? { posted: a.posted + b.posted, ...sum }
          : { posted: accStats.posted ?? 0, customers: accCust.customers, active: accCust.active };
        return (
          <article key={bot} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <header className="flex items-start justify-between gap-2">
              <div>
                <h2 className="font-semibold text-slate-900">{BOT_LABEL[bot] ?? bot}</h2>
                <p className="text-xs text-slate-500">{BOT_HINT[bot]}</p>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-emerald-700">{pct(total.customers, total.posted)}</div>
                <div className="text-xs text-slate-500">reply → khách</div>
              </div>
            </header>

            <div className="mt-4 flex items-center justify-around rounded-xl bg-slate-50 py-3">
              <Step value={total.posted} label="reply đã đăng" />
              <ArrowRight className="h-4 w-4 text-slate-300" />
              <Step value={total.customers} label="khách vào bot" strong />
              <ArrowRight className="h-4 w-4 text-slate-300" />
              <Step value={total.active} label="đã dùng bot" />
            </div>

            {all ? (
              <table className="mt-3 w-full text-xs text-slate-600">
                <thead className="text-left text-slate-400">
                  <tr>
                    <th className="py-1 font-normal">Biến thể</th>
                    <th className="py-1 font-normal">Reply</th>
                    <th className="py-1 font-normal">Khách</th>
                    <th className="py-1 font-normal">Tỉ lệ</th>
                    <th className="py-1 font-normal">Dùng bot</th>
                  </tr>
                </thead>
                <tbody>
                  {([["A", a], ["B", b]] as const).map(([v, r]) => (
                    <tr key={v} className="border-t border-slate-100">
                      <td className="py-1">Câu {v}</td>
                      <td className="py-1">{r.posted}</td>
                      <td className="py-1 font-semibold text-emerald-700">{r.customers}</td>
                      <td className="py-1">{pct(r.customers, r.posted)}</td>
                      <td className="py-1">{r.active}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="mt-3 text-xs text-slate-500">
                Khách tính theo mã link của tài khoản này (link bio riêng; mã reply cũ tính cho @us28qt). Lỗi đăng:{" "}
                {accStats.failed ?? 0}.
              </p>
            )}
            {all && (
              <p className="mt-2 text-xs text-slate-400">
                Chờ duyệt / đăng: {(st.A?.pending ?? 0) + (st.B?.pending ?? 0) + (st.A?.approved ?? 0) + (st.B?.approved ?? 0)} · lỗi:{" "}
                {(st.A?.failed ?? 0) + (st.B?.failed ?? 0)} · AI đã loại: {(st.A?.rejected ?? 0) + (st.B?.rejected ?? 0)}
                {total.customers > a.customers + b.customers &&
                  ` · ${total.customers - a.customers - b.customers} khách qua bài riêng / bio`}
              </p>
            )}
          </article>
        );
      })}
    </section>
  );
}
