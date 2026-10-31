import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { primaryBtnClass } from "@/shared/ui/controls";
import { listDoctypes } from "../api/doctypeApi";

/** Mọi DocType, nhóm theo module. Bấm tên → bản ghi; «Sửa định nghĩa» → trình dựng. */
export function DoctypeListPage() {
  const q = useQuery({ queryKey: ["doctypes"], queryFn: listDoctypes });
  const rows = q.data?.doctypes ?? [];
  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <PageHeader title="Dữ liệu (DocType)" subtitle="Tự định nghĩa loại dữ liệu — trường, kiểu, liên kết, bảng con — không cần sửa code" />
        <Link to="/app/go/doctype/new" className={`${primaryBtnClass} inline-flex items-center`}>
          Tạo DocType
        </Link>
      </div>
      <Panel className="mt-4">
        <QueryBody isLoading={q.isLoading} isError={q.isError} loadingText="Đang tải…" errorText="Không tải được DocType">
          {rows.length === 0 ? (
            <p className="p-6 text-center text-sm text-slate-400">Chưa có DocType nào. Bấm «Tạo DocType» — ví dụ «Thư viện hook», «Kiểu caption».</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">DocType</th>
                  <th className="px-3 py-2">Module</th>
                  <th className="px-3 py-2 text-right">Trường</th>
                  <th className="px-3 py-2 text-right">Bản ghi</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((d) => (
                  <tr key={d.name}>
                    <td className="px-3 py-2">
                      {d.is_child ? (
                        <span className="font-medium text-slate-700">{d.label}</span>
                      ) : (
                        <Link to={`/app/go/doc/${d.name}`} className="font-medium text-indigo-700 hover:underline">
                          {d.label}
                        </Link>
                      )}
                      <span className="ml-2 font-mono text-xs text-slate-400">{d.name}</span>
                      {d.is_child ? <span className="ml-2 rounded bg-slate-100 px-1.5 text-[10px] text-slate-500">bảng con</span> : null}
                    </td>
                    <td className="px-3 py-2 text-slate-500">{d.module || "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{d.fields.length}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{d.records ?? 0}</td>
                    <td className="px-3 py-2 text-right">
                      <Link to={`/app/go/doctype/${d.name}`} className="text-xs text-slate-500 hover:underline">
                        Sửa định nghĩa
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </QueryBody>
      </Panel>
    </div>
  );
}
