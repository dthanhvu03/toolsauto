import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { fetchViral } from "@/api/adminApi";

export function ViralPage() {
  const [status, setStatus] = useState("");
  const [platform, setPlatform] = useState("");
  const [page, setPage] = useState(1);
  const [qDraft, setQDraft] = useState("");
  const [q, setQ] = useState("");

  const query = useQuery({
    queryKey: ["admin-viral", status, platform, q, page],
    queryFn: () => fetchViral({ status, platform, q, page }),
  });

  const items = query.data?.items ?? [];
  const totalPages = query.data?.total_pages ?? 1;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Nội dung viral</h1>
          <p className="mt-1 text-sm text-slate-500">
            {query.data
              ? `${query.data.total} materials · NEW ${query.data.new_count ?? 0} · READY ${query.data.ready_count ?? 0} · FAIL ${query.data.failed_count ?? 0}`
              : "—"}
          </p>
        </div>
        <a
          href="/app/viral"
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-400 hover:underline"
        >
          Classic <ExternalLink className="size-3" />
        </a>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <select
          className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm"
          value={status}
          onChange={(e) => {
            setPage(1);
            setStatus(e.target.value);
          }}
        >
          <option value="">All status</option>
          <option value="NEW">NEW</option>
          <option value="READY">READY</option>
          <option value="FAILED">FAILED</option>
          <option value="PROCESSING">PROCESSING</option>
        </select>
        <select
          className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm"
          value={platform}
          onChange={(e) => {
            setPage(1);
            setPlatform(e.target.value);
          }}
        >
          <option value="">All platforms</option>
          <option value="tiktok">tiktok</option>
          <option value="facebook">facebook</option>
        </select>
        <input
          className="h-9 min-w-[12rem] flex-1 rounded-lg border border-slate-200 px-3 text-sm"
          placeholder="Tìm URL…"
          value={qDraft}
          onChange={(e) => setQDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setPage(1);
              setQ(qDraft.trim());
            }
          }}
        />
        <button
          type="button"
          className="h-9 rounded-lg bg-indigo-600 px-3 text-sm font-semibold text-white"
          onClick={() => {
            setPage(1);
            setQ(qDraft.trim());
          }}
        >
          Tìm
        </button>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {query.isLoading ? (
          <p className="p-6 text-sm text-slate-500">Đang tải…</p>
        ) : query.isError ? (
          <p className="p-6 text-sm text-red-600">Lỗi tải viral</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Views</th>
                  <th className="px-3 py-2">Account</th>
                  <th className="px-3 py-2">URL</th>
                  <th className="px-3 py-2">Job</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-8 text-center text-slate-400">
                      Không có material
                    </td>
                  </tr>
                ) : (
                  items.map((it) => (
                    <tr key={it.id} className="hover:bg-slate-50/80">
                      <td className="px-3 py-2 font-mono text-xs">
                        #{it.id}
                        {it.is_mega ? (
                          <span className="ml-1 text-[10px] font-bold text-amber-600">MEGA</span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 text-xs font-semibold">{it.status}</td>
                      <td className="px-3 py-2 tabular-nums">{(it.views ?? 0).toLocaleString()}</td>
                      <td className="px-3 py-2 text-xs">{it.account_name || "—"}</td>
                      <td className="max-w-[18rem] truncate px-3 py-2 text-xs">
                        <a
                          href={it.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-indigo-600 hover:underline"
                        >
                          {it.url}
                        </a>
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-500">
                        {it.job_id ? `#${it.job_id} ${it.job_status || ""}` : "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          disabled={page <= 1}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          Trước
        </button>
        <span className="text-xs text-slate-500">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
          onClick={() => setPage((p) => p + 1)}
        >
          Sau
        </button>
      </div>
    </div>
  );
}
