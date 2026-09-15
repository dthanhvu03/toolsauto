import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Settings, ListTodo, Zap, Users } from "lucide-react";

async function pingHealth(): Promise<{ ok: boolean }> {
  const r = await fetch("/health/json", { credentials: "same-origin" });
  if (!r.ok) return { ok: false };
  return r.json().catch(() => ({ ok: true }));
}

const cards = [
  { to: "/app/settings", title: "Cài đặt vận hành", desc: "Đã React · metadata-driven", icon: Settings, ready: true },
  { to: "/app/go/jobs", title: "Hàng đợi job", desc: "Bridge → classic", icon: ListTodo },
  { to: "/app/go/viral", title: "Nội dung viral", desc: "Bridge → classic", icon: Zap },
  { to: "/app/go/accounts", title: "Tài khoản", desc: "Bridge → classic", icon: Users },
];

export function OverviewPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: pingHealth, retry: false });

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold text-slate-900">Tổng quan</h1>
      <p className="mt-1 text-sm text-slate-500">
        Dashboard React — Settings đã native; các module khác mở classic cho đến khi port xong.
      </p>

      <div className="mt-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
        API:{" "}
        {health.isLoading ? (
          <span className="text-slate-400">đang kiểm tra…</span>
        ) : health.isError || !health.data?.ok ? (
          <span className="font-medium text-amber-700">không tới được /health (cần đăng nhập hoặc server)</span>
        ) : (
          <span className="font-medium text-emerald-700">OK</span>
        )}
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <Link
              key={c.to}
              to={c.to}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-200 hover:shadow"
            >
              <div className="flex items-start gap-3">
                <span className="rounded-lg bg-indigo-50 p-2 text-indigo-700">
                  <Icon className="size-5" />
                </span>
                <div>
                  <div className="font-semibold text-slate-900">{c.title}</div>
                  <div className="mt-1 text-xs text-slate-500">{c.desc}</div>
                  {c.ready ? (
                    <span className="mt-2 inline-block rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold uppercase text-emerald-700">
                      React ready
                    </span>
                  ) : null}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
