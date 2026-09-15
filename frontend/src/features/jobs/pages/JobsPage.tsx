import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { fetchJobs } from "@/shared/api/adminApi";

const STATUS_OPTS = [
  { value: "active", label: "Active" },
  { value: "PENDING", label: "PENDING" },
  { value: "RUNNING", label: "RUNNING" },
  { value: "DRAFT", label: "DRAFT" },
  { value: "DONE", label: "DONE" },
  { value: "FAILED", label: "FAILED" },
];

export function JobsPage() {
  const [status, setStatus] = useState("active");
  const [platform, setPlatform] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [qDraft, setQDraft] = useState("");

  const query = useQuery({
    queryKey: ["admin-jobs", status, platform, q, page],
    queryFn: () => fetchJobs({ status, platform, q, page }),
  });

  const rows = query.data?.jobs ?? [];
  const totalPages = query.data?.total_pages ?? 1;

  const subtitle = useMemo(() => {
    if (!query.data) return "";
    return `${query.data.total} jobs · trang ${query.data.page}/${query.data.total_pages}`;
  }, [query.data]);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Hàng đợi job</h1>
          <p className="mt-1 text-sm text-slate-500">{subtitle || "—"}</p>
        </div>
        <a
          href="/app/jobs"
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-400 hover:underline"
        >
          Classic <ExternalLink className="size-3" />
        </a>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <select
          className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm"
          value={status}
          onChange={(e) => {
            setPage(1);
            setStatus(e.target.value);
          }}
        >
          {STATUS_OPTS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
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
          <option value="facebook">facebook</option>
          <option value="threads">threads</option>
        </select>
        <input
          className="h-9 min-w-[12rem] flex-1 rounded-lg border border-slate-200 px-3 text-sm"
          placeholder="Tìm id / account / caption…"
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
          <p className="p-6 text-sm text-red-600">Lỗi tải jobs</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Account</th>
                  <th className="px-3 py-2">Target</th>
                  <th className="px-3 py-2">Caption</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-8 text-center text-slate-400">
                      Không có job
                    </td>
                  </tr>
                ) : (
                  rows.map((j) => (
                    <tr key={j.id} className="hover:bg-slate-50/80">
                      <td className="px-3 py-2 font-mono text-xs">#{j.id}</td>
                      <td className="px-3 py-2">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold">
                          {j.status}
                        </span>
                      </td>
                      <td className="px-3 py-2">{j.account_name || "—"}</td>
                      <td className="max-w-[10rem] truncate px-3 py-2 text-xs text-slate-500">
                        {j.target_page || "—"}
                      </td>
                      <td className="max-w-[16rem] truncate px-3 py-2 text-xs text-slate-600">
                        {j.caption || "—"}
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
