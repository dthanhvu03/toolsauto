import { PageHeader } from "@/shared/ui/PageHeader";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { StatCard } from "@/features/overview/components/StatCard";
import { ComplianceKeywordFilters } from "../components/ComplianceKeywordFilters";
import { ComplianceKeywordTable } from "../components/ComplianceKeywordTable";
import { useComplianceController } from "../hooks/useComplianceController";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";

export function CompliancePage() {
  const ctl = useComplianceController();
  const stats = ctl.analytics.data;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Từ khoá cấm"
        subtitle="AI được dặn tránh các từ này khi viết caption (cả caption Studio). Allowlist / import CSV ở bản cũ."
        classicHref="/compliance/"
      />
      <ActionMsg text={ctl.msg} />

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Từ khoá đang bật"
          value={ctl.analytics.isLoading || ctl.analytics.isError ? "—" : String(stats?.total_keywords ?? 0)}
        />
      </div>

      {stats && stats.total_keywords === 0 ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Blacklist đang trống. Thêm từ khóa / Import CSV ở Classic.
        </div>
      ) : null}

      <>
          <form
            className="mt-4 flex flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              const kw = String(fd.get("keyword") || "").trim();
              if (!kw) return;
              ctl.addKeyword(kw, String(fd.get("severity") || "WARNING"));
              e.currentTarget.reset();
            }}
          >
            <input name="keyword" className={inputClass} placeholder="Từ khóa mới" />
            <select name="severity" className={selectClass} defaultValue="WARNING">
              <option value="WARNING">WARNING</option>
              <option value="VIOLATION">VIOLATION</option>
            </select>
            <button type="submit" className={primaryBtnClass}>
              Thêm
            </button>
          </form>
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              className={inputClass}
              placeholder="Test caption…"
              value={ctl.testText}
              onChange={(e) => ctl.setTestText(e.target.value)}
            />
            <button type="button" className={primaryBtnClass} onClick={ctl.runTest}>
              Test
            </button>
          </div>
          {ctl.testResult ? (
            <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-900 p-3 text-[11px] text-slate-100">
              {ctl.testResult}
            </pre>
          ) : null}
          <Panel className="mt-4">
            <ComplianceKeywordFilters
              searchDraft={ctl.searchDraft}
              onDraftChange={ctl.setSearchDraft}
              onSearch={ctl.applySearch}
              severity={ctl.severity}
              category={ctl.category}
              categories={ctl.categories}
              onSeverityChange={ctl.changeSeverity}
              onCategoryChange={ctl.changeCategory}
            />
            <QueryBody
              isLoading={ctl.keywords.isLoading}
              isError={ctl.keywords.isError}
              loadingText="Đang tải…"
              errorText="Lỗi tải từ khóa"
            >
              <ComplianceKeywordTable
                rows={ctl.kwSlice}
                onToggle={ctl.toggleKeyword}
                onDelete={ctl.deleteKeyword}
              />
            </QueryBody>
          </Panel>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-slate-400">{ctl.kwTotal} từ khóa</span>
            <Pagination page={ctl.kwPage} totalPages={ctl.kwTotalPages} onPageChange={ctl.setKwPage} />
          </div>
      </>
    </div>
  );
}
