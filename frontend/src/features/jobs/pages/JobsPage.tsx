import { PageHeader } from "@/shared/ui/PageHeader";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { JobsFilters } from "../components/JobsFilters";
import { JobsTable } from "../components/JobsTable";
import { ManualJobForm } from "../components/ManualJobForm";
import { useJobsController } from "../hooks/useJobsController";

export function JobsPage({
  title = "Hàng đợi job",
  defaultPlatform = "",
  classicHref = "/app/jobs",
}: {
  title?: string;
  defaultPlatform?: string;
  classicHref?: string;
}) {
  const ctl = useJobsController({ defaultPlatform });

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title={title} subtitle={ctl.subtitle || "—"} classicHref={classicHref} />
      <ActionMsg text={ctl.msg} />

      <ManualJobForm accounts={ctl.accounts} busy={ctl.creating} onSubmit={ctl.createJob} />

      <JobsFilters
        status={ctl.status}
        platform={ctl.platform}
        qDraft={ctl.qDraft}
        onStatusChange={ctl.changeStatus}
        onPlatformChange={ctl.changePlatform}
        onDraftChange={ctl.setQDraft}
        onSearch={ctl.applySearch}
      />

      <Panel className="mt-4">
        <QueryBody
          isLoading={ctl.query.isLoading}
          isError={ctl.query.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải jobs"
        >
          <JobsTable rows={ctl.rows} busyId={ctl.busyId} onAction={ctl.runAction} />
        </QueryBody>
      </Panel>

      <Pagination page={ctl.page} totalPages={ctl.totalPages} onPageChange={ctl.setPage} />
    </div>
  );
}
