import { PageHeader } from "@/shared/ui/PageHeader";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { ViralAddForm } from "../components/ViralAddForm";
import { ViralFilters } from "../components/ViralFilters";
import { ViralTable } from "../components/ViralTable";
import { useViralController } from "../hooks/useViralController";

export function ViralPage() {
  const ctl = useViralController();
  const d = ctl.query.data;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Nội dung viral"
        subtitle={
          d
            ? `${d.total} materials · NEW ${d.new_count ?? 0} · READY ${d.ready_count ?? 0} · FAIL ${d.failed_count ?? 0}`
            : "—"
        }
        classicHref="/app/viral"
      />
      <ActionMsg text={ctl.msg} />
      <ViralAddForm busy={ctl.busy} onAdd={ctl.addLink} onProcessNew={ctl.processNew} />

      <ViralFilters
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
          errorText="Lỗi tải viral"
        >
          <ViralTable items={ctl.items} busyId={ctl.busyId} onAction={ctl.runAction} />
        </QueryBody>
      </Panel>

      <Pagination page={ctl.page} totalPages={ctl.totalPages} onPageChange={ctl.setPage} />
    </div>
  );
}
