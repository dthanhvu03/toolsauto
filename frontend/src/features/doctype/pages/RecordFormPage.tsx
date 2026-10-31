import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { dangerBtnClass, primaryBtnClass } from "@/shared/ui/controls";
import { Panel } from "@/shared/ui/Panel";
import { Toast } from "@/shared/ui/Toast";
import { DocApiError, deleteRecord, getDoctype, getRecord, saveRecord } from "../api/doctypeApi";
import { ChildTable } from "../components/ChildTable";
import { FieldInput } from "../components/FieldInput";

type Data = Record<string, unknown>;

/** Form chung của một bản ghi — dựng từ định nghĩa DocType; lỗi 422 tô đỏ đúng ô (kể cả ô trong bảng con). */
export function RecordFormPage() {
  const { doctype = "", name: param } = useParams();
  const isNew = !param || param === "new";
  const nav = useNavigate();
  const qc = useQueryClient();
  const dt = useQuery({ queryKey: ["doctype", doctype], queryFn: () => getDoctype(doctype) });
  const rec = useQuery({ queryKey: ["doc", doctype, param], queryFn: () => getRecord(doctype, param!), enabled: !isNew });
  const [data, setData] = useState<Data>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState({ text: "", seq: 0 });
  const say = (text: string) => setMsg((m) => ({ text, seq: m.seq + 1 }));

  useEffect(() => {
    if (rec.data) setData({ ...rec.data.data });
    else if (isNew && dt.data) setData(Object.fromEntries(dt.data.fields.map((f) => [f.fieldname, f.fieldtype === "table" ? [] : f.default ?? null])));
  }, [rec.data, dt.data, isNew]);

  const save = useMutation({
    mutationFn: () => {
      const known = new Set((dt.data?.fields ?? []).map((f) => f.fieldname));
      // Trường đã bỏ khỏi định nghĩa vẫn còn trong dữ liệu cũ — không gửi lại (server từ chối trường lạ).
      return saveRecord(doctype, Object.fromEntries(Object.entries(data).filter(([k]) => known.has(k))), isNew ? undefined : param);
    },
    onSuccess: (r) => {
      setErrors({});
      qc.invalidateQueries({ queryKey: ["doc-list", doctype] });
      qc.invalidateQueries({ queryKey: ["doctypes"] });
      say(`Đã lưu «${r.name}».`);
      if (isNew) nav(`/app/go/doc/${doctype}/${encodeURIComponent(r.name)}`, { replace: true });
      else qc.invalidateQueries({ queryKey: ["doc", doctype, param] });
    },
    onError: (e: Error) => {
      setErrors(e instanceof DocApiError ? e.errors : {});
      say(`Lỗi: ${e instanceof DocApiError && Object.keys(e.errors).length ? "kiểm tra các ô tô đỏ" : e.message}`);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteRecord(doctype, param!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["doc-list", doctype] });
      nav(`/app/go/doc/${doctype}`);
    },
    onError: (e: Error) => say(`Lỗi: ${e.message}`),
  });

  const fields = dt.data?.fields ?? [];
  return (
    <div className="mx-auto max-w-4xl">
      <Link to={`/app/go/doc/${doctype}`} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
        <ArrowLeft className="size-4" /> {dt.data?.label ?? doctype}
      </Link>
      <h1 className="mt-2 text-2xl font-semibold">{isNew ? `Thêm ${dt.data?.label ?? ""}` : `${dt.data?.label ?? doctype}: ${param}`}</h1>
      <Toast text={msg.text} seq={msg.seq} />
      <Panel className="mt-4 flex flex-col gap-4 p-4">
        {fields.map((f) => {
          const err = errors[f.fieldname];
          return (
            <div key={f.fieldname}>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                {f.label}
                {f.required ? <span className="text-red-500"> *</span> : null}
                {f.unique ? <span className="ml-1 text-[10px] text-slate-400">(không trùng)</span> : null}
              </label>
              {f.fieldtype === "table" ? (
                <ChildTable field={f} rows={(data[f.fieldname] as Data[]) ?? []} errors={errors} disabled={false} onChange={(rows) => setData({ ...data, [f.fieldname]: rows })} />
              ) : (
                <FieldInput field={f} value={data[f.fieldname]} error={err} onChange={(v) => setData({ ...data, [f.fieldname]: v })} />
              )}
              {err ? <p className="mt-1 text-xs text-red-600">{err}</p> : null}
              {f.description ? <p className="mt-1 text-[11px] text-slate-400">{f.description}</p> : null}
            </div>
          );
        })}
        {fields.length === 0 && !dt.isLoading ? <p className="text-sm text-slate-400">DocType chưa có trường nào.</p> : null}
      </Panel>
      <div className="mt-4 flex gap-2">
        <button type="button" className={primaryBtnClass} disabled={save.isPending || !fields.length} onClick={() => save.mutate()}>
          {save.isPending ? "Đang lưu…" : "Lưu"}
        </button>
        {!isNew ? (
          <button type="button" className={`${dangerBtnClass} h-9 px-3 text-sm`} disabled={remove.isPending} onClick={() => window.confirm(`Xoá bản ghi «${param}»?`) && remove.mutate()}>
            Xoá
          </button>
        ) : null}
      </div>
    </div>
  );
}
