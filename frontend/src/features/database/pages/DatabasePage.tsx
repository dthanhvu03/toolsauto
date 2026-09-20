import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { SearchField } from "@/shared/ui/SearchField";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { primaryBtnClass } from "@/shared/ui/controls";
import { useDatabaseController } from "../hooks/useDatabaseController";

export function DatabasePage() {
  const ctl = useDatabaseController();
  const sqlRes = ctl.sqlMut.data;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Database"
        subtitle={ctl.query.data ? `${ctl.total} bảng` : "—"}
        classicHref="/database"
      />
      <ActionMsg text={ctl.sqlMut.error instanceof Error ? ctl.sqlMut.error.message : ""} />
      <div className="mt-4 flex flex-wrap gap-2">
        <SearchField
          placeholder="Lọc tên bảng…"
          value={ctl.qDraft}
          onChange={ctl.setQDraft}
          onSubmit={ctl.applySearch}
        />
      </div>
      <Panel className="mt-4">
        <QueryBody
          isLoading={ctl.query.isLoading}
          isError={ctl.query.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải danh sách bảng"
        >
          {ctl.tables.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-400">Không có bảng khớp</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[400px] text-left text-sm">
                <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Bảng</th>
                    <th className="px-3 py-2 text-right">Số dòng</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ctl.tables.map((t) => (
                    <tr
                      key={t.name}
                      className={`cursor-pointer hover:bg-slate-50/80 ${ctl.table === t.name ? "bg-indigo-50" : ""}`}
                      onClick={() => ctl.setTable(t.name)}
                    >
                      <td className="px-3 py-2 font-mono text-xs">{t.name}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{t.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryBody>
      </Panel>

      {ctl.table ? (
        <Panel className="mt-4">
          <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
            Preview {ctl.table}
          </div>
          <QueryBody
            isLoading={ctl.preview.isLoading}
            isError={ctl.preview.isError}
            loadingText="Đang tải…"
            errorText="Lỗi preview"
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[400px] text-left text-xs">
                <thead className="border-b border-slate-100 bg-slate-50 uppercase text-slate-500">
                  <tr>
                    {(ctl.preview.data?.columns ?? []).map((c) => (
                      <th key={c} className="px-2 py-2">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(ctl.preview.data?.rows ?? []).slice(0, 30).map((row, i) => (
                    <tr key={i}>
                      {(ctl.preview.data?.columns ?? []).map((c) => (
                        <td key={c} className="max-w-[12rem] truncate px-2 py-1">
                          {String(row[c] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </QueryBody>
        </Panel>
      ) : null}

      <Panel className="mt-4">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">SQL console</div>
        <div className="space-y-2 p-4">
          <textarea
            className="min-h-[6rem] w-full rounded-lg border border-slate-200 p-2 font-mono text-xs"
            value={ctl.sql}
            onChange={(e) => ctl.setSql(e.target.value)}
          />
          <label className="flex items-center gap-2 text-xs text-amber-800">
            <input
              type="checkbox"
              checked={ctl.confirmed}
              onChange={(e) => ctl.setConfirmed(e.target.checked)}
            />
            Xác nhận câu lệnh ghi (UPDATE/INSERT)
          </label>
          <button type="button" className={primaryBtnClass} disabled={ctl.sqlMut.isPending} onClick={ctl.run}>
            Chạy SQL
          </button>
          {sqlRes ? (
            <pre className="max-h-48 overflow-auto rounded-lg bg-slate-900 p-3 text-[11px] text-slate-100">
              {JSON.stringify(sqlRes, null, 2)}
            </pre>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}
