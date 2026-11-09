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

/** Mỗi bot một thẻ: reply đã đăng → khách mới (mã ?start=threads_…) → đã dùng bot; so A/B bên dưới. */
export function BotFunnel({ ov }: { ov: Overview }) {
  const bots = Object.keys(ov.stats);
  const rep = ov.customers;
  return (
    <section className="grid gap-3 md:grid-cols-2">
      {bots.map((bot) => {
        const st = ov.stats[bot];
        const cust = rep?.by_variant?.[bot] ?? {};
        const row = (v: "A" | "B") => ({
          posted: st[v]?.posted ?? 0,
          customers: cust[v]?.customers ?? 0,
          active: cust[v]?.active ?? 0,
        });
        const a = row("A");
        const b = row("B");
        const posted = a.posted + b.posted;
        const customers = a.customers + b.customers;
        const active = a.active + b.active;
        return (
          <article key={bot} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <header className="flex items-start justify-between gap-2">
              <div>
                <h2 className="font-semibold text-slate-900">{BOT_LABEL[bot] ?? bot}</h2>
                <p className="text-xs text-slate-500">{BOT_HINT[bot]}</p>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-emerald-700">{pct(customers, posted)}</div>
                <div className="text-xs text-slate-500">reply → khách</div>
              </div>
            </header>

            <div className="mt-4 flex items-center justify-around rounded-xl bg-slate-50 py-3">
              <Step value={posted} label="reply đã đăng" />
              <ArrowRight className="h-4 w-4 text-slate-300" />
              <Step value={customers} label="khách vào bot" strong />
              <ArrowRight className="h-4 w-4 text-slate-300" />
              <Step value={active} label="đã dùng bot" />
            </div>

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
            <p className="mt-2 text-xs text-slate-400">
              Chờ duyệt / đăng: {(st.A?.pending ?? 0) + (st.B?.pending ?? 0) + (st.A?.approved ?? 0) + (st.B?.approved ?? 0)} · lỗi:{" "}
              {(st.A?.failed ?? 0) + (st.B?.failed ?? 0)} · AI đã loại: {(st.A?.rejected ?? 0) + (st.B?.rejected ?? 0)}
            </p>
          </article>
        );
      })}
    </section>
  );
}
