import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { TiktokLinksFilters } from "../components/TiktokLinksFilters";
import { TiktokLinksTable } from "../components/TiktokLinksTable";
import { useTiktokLinksController } from "../hooks/useTiktokLinksController";

export function TiktokLinksPage() {
  const ctl = useTiktokLinksController();

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Kho kênh cũ"
        subtitle={ctl.query.data ? `${ctl.query.data.total} kênh` : "—"}
        classicHref="/app/tiktok-links"
      />

      <TiktokLinksFilters
        qDraft={ctl.qDraft}
        onDraftChange={ctl.setQDraft}
        onSearch={ctl.applySearch}
      />

      <Panel className="mt-4">
        <QueryBody
          isLoading={ctl.query.isLoading}
          isError={ctl.query.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải kho kênh cũ"
        >
          <TiktokLinksTable items={ctl.items} />
        </QueryBody>
      </Panel>
    </div>
  );
}
