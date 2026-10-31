import { useQuery } from "@tanstack/react-query";
import { linkOptions } from "../api/doctypeApi";
import type { DocField } from "../types/doctype.types";

const box = "h-9 w-full rounded-lg border px-2 text-sm";

function LinkSelect({ field, value, onChange, disabled }: { field: DocField; value: unknown; onChange: (v: unknown) => void; disabled: boolean }) {
  const q = useQuery({ queryKey: ["doc-options", field.options], queryFn: () => linkOptions(String(field.options)) });
  return (
    <select className={`${box} bg-white`} value={String(value ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">—</option>
      {(q.data?.options ?? []).map((o) => (
        <option key={o.name} value={o.name}>
          {o.title === o.name ? o.name : `${o.title} (${o.name})`}
        </option>
      ))}
    </select>
  );
}

/** Một ô nhập theo kiểu trường (trừ ``table`` — xem ``ChildTable``). */
export function FieldInput({
  field,
  value,
  onChange,
  error,
  disabled = false,
}: {
  field: DocField;
  value: unknown;
  onChange: (v: unknown) => void;
  error?: string;
  disabled?: boolean;
}) {
  const ro = disabled || !!field.read_only;
  const cls = `${box} ${error ? "border-red-400 bg-red-50" : "border-slate-200"}`;
  switch (field.fieldtype) {
    case "check":
      return <input type="checkbox" className="size-4" checked={!!value} disabled={ro} onChange={(e) => onChange(e.target.checked)} />;
    case "text":
      return (
        <textarea className={`${cls} h-24 py-1.5`} value={String(value ?? "")} disabled={ro} onChange={(e) => onChange(e.target.value)} />
      );
    case "json":
      return (
        <textarea
          className={`${cls} h-24 py-1.5 font-mono text-xs`}
          defaultValue={value == null ? "" : typeof value === "string" ? value : JSON.stringify(value, null, 2)}
          disabled={ro}
          onBlur={(e) => onChange(e.target.value)}
        />
      );
    case "select":
      return (
        <select className={`${cls} bg-white`} value={String(value ?? "")} disabled={ro} onChange={(e) => onChange(e.target.value || null)}>
          <option value="">—</option>
          {(Array.isArray(field.options) ? field.options : []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      );
    case "link":
      return <LinkSelect field={field} value={value} onChange={onChange} disabled={ro} />;
    case "int":
    case "float":
      return (
        <input
          type="number"
          step={field.fieldtype === "int" ? 1 : "any"}
          className={cls}
          value={value == null ? "" : String(value)}
          disabled={ro}
          onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        />
      );
    case "date":
      return <input type="date" className={cls} value={String(value ?? "")} disabled={ro} onChange={(e) => onChange(e.target.value || null)} />;
    case "datetime":
      return (
        <input
          type="datetime-local"
          className={cls}
          value={String(value ?? "").slice(0, 16)}
          disabled={ro}
          onChange={(e) => onChange(e.target.value || null)}
        />
      );
    default:
      return <input className={cls} value={String(value ?? "")} disabled={ro} onChange={(e) => onChange(e.target.value)} />;
  }
}

/** Hiện giá trị trong bảng danh sách. */
export function formatValue(field: DocField | undefined, value: unknown): string {
  if (value == null || value === "") return "—";
  if (field?.fieldtype === "check") return value ? "✓" : "✗";
  if (field?.fieldtype === "table") return `${(value as unknown[]).length} dòng`;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
