import { PageHeader } from "@/shared/ui/PageHeader";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { JobsFilters } from "../components/JobsFilters";
import { JobsTable } from "../components/JobsTable";
import { useJobsController } from "../hooks/useJobsController";

export function JobsPage() {
  const ctl = useJobsController();

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Lịch đăng" subtitle={ctl.subtitle || "—"} />
      <p className="mt-2 text-xs text-slate-500">
        Mỗi dòng là một lần đưa video lên Buffer. Xếp lại giờ / huỷ lịch: dùng Telegram (gọi Buffer tốn suất nên web chỉ xem).
      </p>
      <JobsFilters
        status={ctl.status}
        qDraft={ctl.qDraft}
        onStatusChange={ctl.changeStatus}
        onDraftChange={ctl.setQDraft}
        onSearch={ctl.applySearch}
      />
      <Panel className="mt-4">
        <QueryBody isLoading={ctl.query.isLoading} isError={ctl.query.isError} loadingText="Đang tải…" errorText="Lỗi tải lịch đăng">
          <JobsTable rows={ctl.rows} />
        </QueryBody>
      </Panel>
      <Pagination page={ctl.page} totalPages={ctl.totalPages} onPageChange={ctl.setPage} />
    </div>
  );
}
