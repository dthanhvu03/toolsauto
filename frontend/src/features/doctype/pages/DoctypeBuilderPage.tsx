import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { dangerBtnClass, ghostBtnClass, inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { Panel } from "@/shared/ui/Panel";
import { Toast } from "@/shared/ui/Toast";
import { deleteDoctype, getDoctype, listDoctypes, saveDoctype } from "../api/doctypeApi";
import type { DocField, DocTypeDef, FieldType } from "../types/doctype.types";

const TYPE_LABEL: Record<FieldType, string> = {
  data: "Chữ ngắn", text: "Văn bản", int: "Số nguyên", float: "Số thực", check: "Có / không", select: "Chọn 1",
  date: "Ngày", datetime: "Ngày giờ", link: "Liên kết", table: "Bảng con", json: "JSON",
};
const blankField = (): DocField => ({ fieldname: "", label: "", fieldtype: "data" });
const cell = "h-8 w-full rounded border border-slate-200 px-2 text-sm";

/** Trình dựng DocType: thông tin chung + bảng trường (thêm, sửa, đổi thứ tự, bỏ). */
export function DoctypeBuilderPage() {
  const param = useParams().name;
  const isNew = !param || param === "new";
  const nav = useNavigate();
  const qc = useQueryClient();
  const all = useQuery({ queryKey: ["doctypes"], queryFn: listDoctypes });
  const existing = useQuery({ queryKey: ["doctype", param], queryFn: () => getDoctype(param!), enabled: !isNew });
  const [def, setDef] = useState<DocTypeDef>({
    name: "", label: "", module: "", description: "", fields: [blankField()], is_child: false, title_field: null, naming: "autoincrement",
  });
  const [msg, setMsg] = useState({ text: "", seq: 0 });
  useEffect(() => {
    if (existing.data) setDef({ ...existing.data, fields: existing.data.fields.map((f) => ({ ...f })) });
  }, [existing.data]);
  const say = (text: string) => setMsg((m) => ({ text, seq: m.seq + 1 }));

  const save = useMutation({
    mutationFn: () =>
      saveDoctype(
        { ...def, fields: def.fields.filter((f) => f.fieldname.trim()).map((f) => ({ ...f, label: f.label || f.fieldname })) },
        isNew ? undefined : param
      ),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["doctypes"] });
      qc.invalidateQueries({ queryKey: ["doctype", d.name] });
      say(`Đã lưu DocType «${d.label}».`);
      if (isNew) nav(`/app/go/doctype/${d.name}`, { replace: true });
    },
    onError: (e: Error) => say(`Lỗi: ${e.message}`),
  });
  const remove = useMutation({
    mutationFn: () => deleteDoctype(param!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["doctypes"] });
      nav("/app/go/doctype");
    },
    onError: (e: Error) => say(`Lỗi: ${e.message}`),
  });

  const setField = (i: number, patch: Partial<DocField>) => setDef({ ...def, fields: def.fields.map((f, k) => (k === i ? { ...f, ...patch } : f)) });
  const move = (i: number, d: number) => {
    const f = [...def.fields];
    const j = i + d;
    if (j < 0 || j >= f.length) return;
    [f[i], f[j]] = [f[j], f[i]];
    setDef({ ...def, fields: f });
  };
  const targets = all.data?.doctypes ?? [];
  const named = def.fields.filter((f) => f.fieldname.trim());

  return (
    <div className="mx-auto max-w-6xl">
      <Link to="/app/go/doctype" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
        <ArrowLeft className="size-4" /> Dữ liệu
      </Link>
      <h1 className="mt-2 text-2xl font-semibold">{isNew ? "Tạo DocType" : `DocType: ${def.label}`}</h1>
      <Toast text={msg.text} seq={msg.seq} />

      <Panel className="mt-4 grid gap-3 p-4 sm:grid-cols-2">
        <label className="text-xs text-slate-500">
          Tên (mã) — chữ thường / số / _
          <input className={`${inputClass} mt-1 w-full`} value={def.name} disabled={!isNew} placeholder="hook_library" onChange={(e) => setDef({ ...def, name: e.target.value.trim() })} />
        </label>
        <label className="text-xs text-slate-500">
          Tên hiển thị
          <input className={`${inputClass} mt-1 w-full`} value={def.label} placeholder="Thư viện hook" onChange={(e) => setDef({ ...def, label: e.target.value })} />
        </label>
        <label className="text-xs text-slate-500">
          Module (nhóm)
          <input className={`${inputClass} mt-1 w-full`} value={def.module ?? ""} placeholder="Studio" onChange={(e) => setDef({ ...def, module: e.target.value })} />
        </label>
        <label className="text-xs text-slate-500">
          Đặt tên bản ghi
          <select className={`${selectClass} mt-1 w-full`} value={def.naming} onChange={(e) => setDef({ ...def, naming: e.target.value })}>
            <option value="autoincrement">Số tự tăng (1, 2, 3…)</option>
            {named
              .filter((f) => ["data", "int", "select", "date"].includes(f.fieldtype))
              .map((f) => (
                <option key={f.fieldname} value={`field:${f.fieldname}`}>
                  Theo trường «{f.label || f.fieldname}»
                </option>
              ))}
          </select>
        </label>
        <label className="text-xs text-slate-500">
          Trường làm tiêu đề
          <select className={`${selectClass} mt-1 w-full`} value={def.title_field ?? ""} onChange={(e) => setDef({ ...def, title_field: e.target.value || null })}>
            <option value="">— tên bản ghi —</option>
            {named.map((f) => (
              <option key={f.fieldname} value={f.fieldname}>
                {f.label || f.fieldname}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 self-end text-sm">
          <input type="checkbox" checked={def.is_child} onChange={(e) => setDef({ ...def, is_child: e.target.checked })} />
          DocType con (chỉ dùng làm dòng của «Bảng con»)
        </label>
        <label className="text-xs text-slate-500 sm:col-span-2">
          Mô tả
          <input className={`${inputClass} mt-1 w-full`} value={def.description ?? ""} onChange={(e) => setDef({ ...def, description: e.target.value })} />
        </label>
      </Panel>

      <Panel className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[960px] text-left text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500">
            <tr>
              <th className="px-2 py-2">Mã trường</th>
              <th className="px-2 py-2">Tên hiển thị</th>
              <th className="min-w-[8.5rem] px-2 py-2">Kiểu</th>
              <th className="px-2 py-2">Lựa chọn / đích</th>
              <th className="px-2 py-2">Mặc định</th>
              <th className="px-2 py-2 text-center">Bắt buộc</th>
              <th className="px-2 py-2 text-center">Không trùng</th>
              <th className="px-2 py-2 text-center">Hiện ở danh sách</th>
              <th className="w-24" />
            </tr>
          </thead>
          <tbody>
            {def.fields.map((f, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="px-1 py-1">
                  <input className={`${cell} font-mono`} value={f.fieldname} placeholder="ten" onChange={(e) => setField(i, { fieldname: e.target.value.trim() })} />
                </td>
                <td className="px-1 py-1">
                  <input className={cell} value={f.label} placeholder={f.fieldname} onChange={(e) => setField(i, { label: e.target.value })} />
                </td>
                <td className="px-1 py-1">
                  <select className={`${cell} bg-white`} value={f.fieldtype} onChange={(e) => setField(i, { fieldtype: e.target.value as FieldType, options: undefined })}>
                    {(Object.keys(TYPE_LABEL) as FieldType[]).map((t) => (
                      <option key={t} value={t}>
                        {TYPE_LABEL[t]}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-1 py-1">
                  {f.fieldtype === "select" ? (
                    <input
                      className={cell}
                      placeholder="A, B, C"
                      value={Array.isArray(f.options) ? f.options.join(", ") : String(f.options ?? "")}
                      onChange={(e) => setField(i, { options: e.target.value.split(",").map((x) => x.trim()) })}
                    />
                  ) : f.fieldtype === "link" || f.fieldtype === "table" ? (
                    <select className={`${cell} bg-white`} value={String(f.options ?? "")} onChange={(e) => setField(i, { options: e.target.value })}>
                      <option value="">— chọn DocType —</option>
                      {targets
                        .filter((d) => (f.fieldtype === "table" ? d.is_child : !d.is_child))
                        .map((d) => (
                          <option key={d.name} value={d.name}>
                            {d.label}
                          </option>
                        ))}
                    </select>
                  ) : (
                    <span className="text-xs text-slate-300">—</span>
                  )}
                </td>
                <td className="px-1 py-1">
                  {f.fieldtype === "table" ? null : (
                    <input className={cell} value={f.default == null ? "" : String(f.default)} onChange={(e) => setField(i, { default: e.target.value || undefined })} />
                  )}
                </td>
                {(["required", "unique", "in_list_view"] as const).map((k) => (
                  <td key={k} className="px-1 py-1 text-center">
                    <input type="checkbox" checked={!!f[k]} disabled={k === "unique" && f.fieldtype === "table"} onChange={(e) => setField(i, { [k]: e.target.checked })} />
                  </td>
                ))}
                <td className="px-1 py-1">
                  <div className="flex justify-end gap-0.5 text-slate-400">
                    <button type="button" className="p-1 hover:text-slate-700" onClick={() => move(i, -1)} aria-label="Lên">
                      <ArrowUp className="size-4" />
                    </button>
                    <button type="button" className="p-1 hover:text-slate-700" onClick={() => move(i, 1)} aria-label="Xuống">
                      <ArrowDown className="size-4" />
                    </button>
                    <button type="button" className="p-1 hover:text-red-600" onClick={() => setDef({ ...def, fields: def.fields.filter((_, k) => k !== i) })} aria-label="Bỏ trường">
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" className="flex w-full items-center justify-center gap-1 border-t border-slate-100 py-2 text-sm text-slate-600 hover:bg-slate-50" onClick={() => setDef({ ...def, fields: [...def.fields, blankField()] })}>
          <Plus className="size-4" /> Thêm trường
        </button>
      </Panel>
      <p className="mt-2 text-xs text-slate-500">
        Bỏ một trường không xoá dữ liệu cũ (chỉ ẩn). Liên kết / Bảng con: tạo DocType đích trước (bảng con phải là «DocType con»).
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className={primaryBtnClass} disabled={save.isPending || !def.name || !named.length} onClick={() => save.mutate()}>
          {save.isPending ? "Đang lưu…" : "Lưu DocType"}
        </button>
        {!isNew && !def.is_child ? (
          <Link to={`/app/go/doc/${param}`} className={`${ghostBtnClass} inline-flex h-9 items-center px-3 text-sm`}>
            Xem bản ghi ({existing.data?.records ?? (all.data?.doctypes.find((d) => d.name === param)?.records ?? 0)})
          </Link>
        ) : null}
        {!isNew ? (
          <button type="button" className={`${dangerBtnClass} h-9 px-3 text-sm`} disabled={remove.isPending} onClick={() => window.confirm(`Xoá DocType «${def.label}»? Chỉ xoá được khi không còn bản ghi.`) && remove.mutate()}>
            Xoá DocType
          </button>
        ) : null}
      </div>
    </div>
  );
}
