import { PageHeader } from "@/shared/ui/PageHeader";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { StatCard } from "@/features/overview/components/StatCard";
import { InsightsFilters } from "../components/InsightsFilters";
import { InsightsPageCards } from "../components/InsightsPageCards";
import { InsightsTopPosts } from "../components/InsightsTopPosts";
import { useInsightsController } from "../hooks/useInsightsController";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { primaryBtnClass } from "@/shared/ui/controls";
import { formatK } from "../lib/formatK";

export function InsightsPage() {
  const ctl = useInsightsController();
  const sec = ctl.secondary;
  const classicQs = ctl.platform ? `?platform=${encodeURIComponent(ctl.platform)}` : "";

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Phân tích & tăng trưởng"
        subtitle="Bảng số native — heatmap / boost chi tiết vẫn Classic"
        classicHref={`/insights${classicQs}`}
      />
      <ActionMsg text={ctl.msg} />
      <button type="button" className={`${primaryBtnClass} mt-3`} disabled={ctl.refreshing} onClick={ctl.refresh}>
        Refresh số liệu
      </button>

      <InsightsFilters
        platform={ctl.platform}
        days={ctl.days}
        onPlatformChange={ctl.changePlatform}
        onDaysChange={ctl.changeDays}
      />

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Tổng views" value={ctl.growthPending ? "—" : formatK(ctl.totals.views)} />
        <StatCard label="Likes ghi nhận" value={ctl.growthPending ? "—" : formatK(ctl.totals.likes)} />
        <StatCard label="Bài active" value={sec ? String(sec.posts_count) : "—"} />
        <StatCard
          label="Engagement"
          value={sec ? `${sec.engagement_rate}%` : "—"}
          hint={sec ? `avg ${formatK(sec.avg_views)} views` : undefined}
        />
      </div>

      <Panel className="mt-6">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Top posts</div>
        <QueryBody
          isLoading={ctl.isLoading}
          isError={ctl.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải insights"
        >
          <InsightsTopPosts posts={ctl.posts} />
        </QueryBody>
      </Panel>
      <Pagination page={ctl.page} totalPages={ctl.totalPages} onPageChange={ctl.setPage} />

      <Panel className="mt-6">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
          Phân tích chiến lược
        </div>
        <QueryBody
          isLoading={ctl.analysisQuery.isLoading}
          isError={ctl.analysisQuery.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải phân tích page"
        >
          <InsightsPageCards items={ctl.analysis} />
        </QueryBody>
      </Panel>
    </div>
  );
}
