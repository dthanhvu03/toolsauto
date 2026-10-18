import { useState } from "react";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { ViralSourcesTable } from "../components/ViralSourcesTable";
import { useViralSources } from "../hooks/useViralSources";

export function ViralSourcesPage() {
  const q = useViralSources();
  const [url, setUrl] = useState("");
  const [page, setPage] = useState("");

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Nguồn video" subtitle={q.data ? `${q.data.total} kênh` : "—"} classicHref="/app/viral/sources" />
      <ActionMsg text={q.msg} />
      <form
        className="mt-4 flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!url.trim()) return;
          q.add(url.trim(), page.trim() || undefined);
          setUrl("");
        }}
      >
        <input
          className={inputClass}
          placeholder="Link kênh TikTok / YouTube…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <select className={selectClass} value={page} onChange={(e) => setPage(e.target.value)} required>
          <option value="">Chọn page</option>
          {q.pages.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.slots ? ` · ${p.slots}` : ""}
            </option>
          ))}
        </select>
        <button type="submit" className={primaryBtnClass} disabled={q.adding || !page}>
          Thêm nguồn
        </button>
      </form>

      <Panel className="mt-4">
        <QueryBody
          isLoading={q.isLoading}
          isError={q.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải nguồn video"
        >
          <ViralSourcesTable
            items={q.data?.items ?? []}
            pages={q.pages}
            busyId={q.busyId}
            onToggle={q.toggle}
            onScan={q.scan}
            onDelete={q.remove}
            onSetPage={q.setPage}
          />
        </QueryBody>
      </Panel>
    </div>
  );
}
