import { useQuery } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { getDoctype } from "../api/doctypeApi";
import type { DocField } from "../types/doctype.types";
import { FieldInput } from "./FieldInput";

type Row = Record<string, unknown>;

/** Lưới dòng của trường ``table`` — cột lấy từ DocType con. Lỗi dạng ``trường[2].cột`` tô đúng ô. */
export function ChildTable({
  field,
  rows,
  onChange,
  errors,
  disabled,
}: {
  field: DocField;
  rows: Row[];
  onChange: (rows: Row[]) => void;
  errors: Record<string, string>;
  disabled: boolean;
}) {
  const child = useQuery({ queryKey: ["doctype", field.options], queryFn: () => getDoctype(String(field.options)) });
  const cols = child.data?.fields ?? [];
  const blank = () => Object.fromEntries(cols.map((c) => [c.fieldname, c.default ?? null]));
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full min-w-[480px] text-left text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500">
          <tr>
            <th className="w-8 px-2 py-1.5">#</th>
            {cols.map((c) => (
              <th key={c.fieldname} className="px-2 py-1.5">
                {c.label}
                {c.required ? <span className="text-red-500"> *</span> : null}
              </th>
            ))}
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-slate-100 align-top">
              <td className="px-2 py-1.5 text-xs text-slate-400">{i + 1}</td>
              {cols.map((c) => {
                const err = errors[`${field.fieldname}[${i + 1}].${c.fieldname}`];
                return (
                  <td key={c.fieldname} className="px-1 py-1">
                    <FieldInput
                      field={c}
                      value={row[c.fieldname]}
                      error={err}
                      disabled={disabled}
                      onChange={(v) => onChange(rows.map((r, k) => (k === i ? { ...r, [c.fieldname]: v } : r)))}
                    />
                    {err ? <p className="mt-0.5 text-[11px] text-red-600">{err}</p> : null}
                  </td>
                );
              })}
              <td className="px-1 py-1">
                <button type="button" disabled={disabled} className="p-1 text-slate-400 hover:text-red-600" onClick={() => onChange(rows.filter((_, k) => k !== i))} aria-label="Bỏ dòng">
                  <Trash2 className="size-4" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        disabled={disabled || !cols.length}
        className="flex w-full items-center justify-center gap-1 border-t border-slate-100 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        onClick={() => onChange([...rows, blank()])}
      >
        <Plus className="size-3.5" /> Thêm dòng
      </button>
    </div>
  );
}
