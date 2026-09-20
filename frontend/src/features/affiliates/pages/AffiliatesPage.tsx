import { useEffect, useState } from "react";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Pagination } from "@/shared/ui/Pagination";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { inputClass, primaryBtnClass } from "@/shared/ui/controls";
import { AffiliatesFilters } from "../components/AffiliatesFilters";
import { AffiliatesGrid } from "../components/AffiliatesGrid";
import { useAffiliatesController } from "../hooks/useAffiliatesController";

export function AffiliatesPage() {
  const ctl = useAffiliatesController();
  const [keyword, setKeyword] = useState("");
  const [url, setUrl] = useState("");
  const [comment, setComment] = useState("");
  const [rate, setRate] = useState("");

  useEffect(() => {
    if (!ctl.editing) return;
    setKeyword(ctl.editing.keyword);
    setUrl(ctl.editing.url);
    setComment(ctl.editing.comment_template || "");
    setRate(ctl.editing.commission_rate != null ? String(ctl.editing.commission_rate) : "");
  }, [ctl.editing]);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Kho affiliate"
        subtitle={ctl.query.data ? `${ctl.query.data.total} links` : "—"}
        classicHref="/affiliates"
      />
      <ActionMsg text={ctl.msg} />
      <form
        className="mt-4 grid gap-2 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          ctl.save({
            id: ctl.editing?.id || 0,
            keyword,
            url,
            comment_template: comment,
            commission_rate: rate ? Number(rate) : null,
          });
          setKeyword("");
          setUrl("");
          setComment("");
          setRate("");
        }}
      >
        <div className="text-sm font-semibold sm:col-span-2">
          {ctl.editing ? `Sửa #${ctl.editing.id}` : "Thêm link"}
        </div>
        <input className={inputClass} placeholder="Keyword" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        <input className={inputClass} placeholder="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        <textarea
          className="min-h-[4rem] rounded-lg border border-slate-200 px-3 py-2 text-sm sm:col-span-2"
          placeholder="Câu bình luận"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <input
          className={inputClass}
          placeholder="% hoa hồng"
          value={rate}
          onChange={(e) => setRate(e.target.value)}
        />
        <div className="flex gap-2">
          <button type="submit" className={primaryBtnClass} disabled={ctl.saving}>
            Lưu
          </button>
          {ctl.editing ? (
            <button type="button" className={primaryBtnClass} onClick={() => ctl.setEditing(null)}>
              Hủy sửa
            </button>
          ) : null}
        </div>
      </form>

      <AffiliatesFilters qDraft={ctl.qDraft} onDraftChange={ctl.setQDraft} onSearch={ctl.applySearch} />

      <Panel className="mt-4">
        <QueryBody
          isLoading={ctl.query.isLoading}
          isError={ctl.query.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải affiliates"
        >
          <AffiliatesGrid links={ctl.links} onEdit={ctl.setEditing} onDelete={ctl.remove} />
        </QueryBody>
      </Panel>

      <Pagination page={ctl.page} totalPages={ctl.totalPages} onPageChange={ctl.setPage} />
    </div>
  );
}
