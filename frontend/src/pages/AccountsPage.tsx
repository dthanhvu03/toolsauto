import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { fetchAccounts } from "@/api/adminApi";

export function AccountsPage() {
  const [q, setQ] = useState("");
  const [platform, setPlatform] = useState("");
  const [qDraft, setQDraft] = useState("");

  const query = useQuery({
    queryKey: ["admin-accounts", q, platform],
    queryFn: () => fetchAccounts({ q, platform }),
  });

  const rows = query.data?.accounts ?? [];

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Tài khoản</h1>
          <p className="mt-1 text-sm text-slate-500">{query.data ? `${query.data.total} accounts` : "—"}</p>
        </div>
        <a
          href="/app/accounts"
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-400 hover:underline"
        >
          Classic <ExternalLink className="size-3" />
        </a>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <select
          className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
        >
          <option value="">All platforms</option>
          <option value="facebook">facebook</option>
          <option value="threads">threads</option>
          <option value="tiktok">tiktok</option>
        </select>
        <input
          className="h-9 min-w-[12rem] flex-1 rounded-lg border border-slate-200 px-3 text-sm"
          placeholder="Tìm tên…"
          value={qDraft}
          onChange={(e) => setQDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") setQ(qDraft.trim());
          }}
        />
        <button
          type="button"
          className="h-9 rounded-lg bg-indigo-600 px-3 text-sm font-semibold text-white"
          onClick={() => setQ(qDraft.trim())}
        >
          Tìm
        </button>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {query.isLoading ? (
          <p className="p-6 text-sm text-slate-500">Đang tải…</p>
        ) : query.isError ? (
          <p className="p-6 text-sm text-red-600">Lỗi tải accounts</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <li className="px-4 py-8 text-center text-sm text-slate-400">Không có tài khoản</li>
            ) : (
              rows.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                  <div>
                    <div className="font-semibold text-slate-900">
                      {a.name}{" "}
                      <span className="text-xs font-normal text-slate-400">#{a.id}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {a.platform} · login {a.login_status || "—"} · limit {a.daily_limit ?? "—"}/ngày
                    </div>
                    {a.target_page ? (
                      <div className="mt-0.5 max-w-md truncate text-[11px] text-slate-400">
                        {a.target_page}
                      </div>
                    ) : null}
                  </div>
                  <span
                    className={
                      a.is_active
                        ? "rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700"
                        : "rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-500"
                    }
                  >
                    {a.is_active ? "ACTIVE" : "OFF"}
                  </span>
                </li>
              ))
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
