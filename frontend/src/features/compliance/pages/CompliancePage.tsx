import { PageHeader } from "@/shared/ui/PageHeader";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { StatCard } from "@/features/overview/components/StatCard";
import { cn } from "@/shared/lib/cn";
import { ComplianceKeywordFilters } from "../components/ComplianceKeywordFilters";
import { ComplianceKeywordTable } from "../components/ComplianceKeywordTable";
import { ComplianceViolationFilters } from "../components/ComplianceViolationFilters";
import { ComplianceViolationTable } from "../components/ComplianceViolationTable";
import { useComplianceController } from "../hooks/useComplianceController";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";

export function CompliancePage() {
  const ctl = useComplianceController();
  const stats = ctl.analytics.data;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Vi phạm Facebook"
        subtitle="Từ khóa + tester native — allowlist / import CSV vẫn Classic"
        classicHref="/compliance/"
      />
      <ActionMsg text={ctl.msg} />

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Từ khóa active"
          value={ctl.analytics.isLoading || ctl.analytics.isError ? "—" : String(stats?.total_keywords ?? 0)}
        />
        <StatCard
          label="VIOLATION (30 ngày)"
          value={ctl.analytics.isLoading || ctl.analytics.isError ? "—" : String(stats?.total_violations ?? 0)}
        />
        <StatCard
          label="Chặn hôm nay (UTC)"
          value={ctl.analytics.isLoading || ctl.analytics.isError ? "—" : String(stats?.blocked_today ?? 0)}
        />
        <StatCard
          label="Có bản rewrite (30d)"
          value={ctl.analytics.isLoading || ctl.analytics.isError ? "—" : String(stats?.rewritten_count ?? 0)}
        />
      </div>

      {stats && stats.total_keywords === 0 ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Blacklist đang trống. Thêm từ khóa / Import CSV ở Classic.
        </div>
      ) : null}

      <div className="mt-6 inline-flex rounded-xl border border-slate-200 bg-white p-1 text-sm">
        <button
          type="button"
          className={cn(
            "rounded-lg px-3 py-1.5 font-medium",
            ctl.tab === "keywords" ? "bg-indigo-50 text-indigo-800" : "text-slate-600"
          )}
          onClick={() => ctl.setTab("keywords")}
        >
          Từ khóa
        </button>
        <button
          type="button"
          className={cn(
            "rounded-lg px-3 py-1.5 font-medium",
            ctl.tab === "violations" ? "bg-indigo-50 text-indigo-800" : "text-slate-600"
          )}
          onClick={() => ctl.setTab("violations")}
        >
          Lịch sử
        </button>
      </div>

      {ctl.tab === "keywords" ? (
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
      ) : (
        <>
          <Panel className="mt-4">
            <ComplianceViolationFilters
              days={ctl.violDays}
              action={ctl.violAction}
              onDaysChange={ctl.changeViolDays}
              onActionChange={ctl.changeViolAction}
            />
            <QueryBody
              isLoading={ctl.violations.isLoading}
              isError={ctl.violations.isError}
              loadingText="Đang tải…"
              errorText="Lỗi tải lịch sử vi phạm"
            >
              <ComplianceViolationTable rows={ctl.violations.data?.violations ?? []} />
            </QueryBody>
          </Panel>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-slate-400">
              {ctl.violations.data?.total ?? 0} bản ghi
            </span>
            <Pagination
              page={ctl.violPage}
              totalPages={ctl.violations.data?.total_pages ?? 1}
              onPageChange={ctl.setViolPage}
            />
          </div>
        </>
      )}
    </div>
  );
}
