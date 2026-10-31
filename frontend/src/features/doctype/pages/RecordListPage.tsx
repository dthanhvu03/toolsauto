import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { formatTs } from "@/shared/lib/time";
import { primaryBtnClass } from "@/shared/ui/controls";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { SearchField } from "@/shared/ui/SearchField";
import { listRecords } from "../api/doctypeApi";
import { formatValue } from "../components/FieldInput";

/** Danh sách bản ghi của một DocType — cột = trường «hiện ở danh sách» (không có thì 3 trường đầu). */
export function RecordListPage() {
  const doctype = useParams().doctype!;
  const nav = useNavigate();
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["doc-list", doctype, search, page], queryFn: () => listRecords(doctype, search, (page - 1) * 50) });
  const dt = q.data?.doctype;
  // Cột: trường «hiện ở danh sách» (không có thì 3 trường đầu), bỏ trường tiêu đề vì đã ở cột Tên.
  const shown = dt ? (dt.fields.some((f) => f.in_list_view) ? dt.fields.filter((f) => f.in_list_view) : dt.fields.slice(0, 3)) : [];
  const cols = shown.filter((f) => f.fieldname !== dt?.title_field);
  return (
    <div className="mx-auto max-w-6xl">
      <Link to="/app/go/doctype" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
        <ArrowLeft className="size-4" /> Dữ liệu
      </Link>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{dt?.label ?? doctype}</h1>
          <p className="text-sm text-slate-500">
            {q.data ? `${q.data.total} bản ghi` : "—"}
            {dt?.description ? ` · ${dt.description}` : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to={`/app/go/doctype/${doctype}`} className="inline-flex h-9 items-center rounded-lg border border-slate-200 px-3 text-sm text-slate-600">
            Sửa định nghĩa
          </Link>
          <Link to={`/app/go/doc/${doctype}/new`} className={`${primaryBtnClass} inline-flex items-center`}>
            Thêm bản ghi
          </Link>
        </div>
      </div>
      <div className="mt-4">
        <SearchField placeholder="Tìm…" value={draft} onChange={setDraft} onSubmit={() => { setPage(1); setSearch(draft.trim()); }} />
      </div>
      <Panel className="mt-3 overflow-x-auto">
        <QueryBody isLoading={q.isLoading} isError={q.isError} loadingText="Đang tải…" errorText="Không tải được bản ghi">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">Tên</th>
                {cols.map((c) => (
                  <th key={c.fieldname} className="px-3 py-2">
                    {c.label}
                  </th>
                ))}
                <th className="px-3 py-2">Sửa lúc</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(q.data?.records ?? []).length === 0 ? (
                <tr>
                  <td colSpan={cols.length + 2} className="px-3 py-8 text-center text-slate-400">
                    Chưa có bản ghi
                  </td>
                </tr>
              ) : (
                q.data!.records.map((r) => (
                  <tr key={r.name} className="cursor-pointer hover:bg-slate-50" onClick={() => nav(`/app/go/doc/${doctype}/${encodeURIComponent(r.name)}`)}>
                    <td className="px-3 py-2 font-medium text-indigo-700">{r.title ?? r.name}</td>
                    {cols.map((c) => (
                      <td key={c.fieldname} className="max-w-[16rem] truncate px-3 py-2 text-slate-600">
                        {formatValue(c, r.data[c.fieldname])}
                      </td>
                    ))}
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-400">{formatTs(r.modified_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </QueryBody>
      </Panel>
      <Pagination page={page} totalPages={Math.max(1, Math.ceil((q.data?.total ?? 0) / 50))} onPageChange={setPage} />
    </div>
  );
}
