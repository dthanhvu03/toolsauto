import { redirectToLoginIfUnauthorized } from "@/shared/api/http";
import type { DocRecordRow, DocTypeDef } from "../types/doctype.types";

/** Lỗi API có thể kèm ``errors`` {trường: lý do} (422) để form tô đỏ từng ô. */
export class DocApiError extends Error {
  constructor(message: string, public errors: Record<string, string> = {}) {
    super(message);
  }
}

async function call<T>(url: string, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) {
    redirectToLoginIfUnauthorized(401);
    throw new DocApiError("Chưa đăng nhập");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new DocApiError(data.detail ?? `${url} → ${r.status}`, data.errors ?? {});
  return data as T;
}

const q = encodeURIComponent;
export const listDoctypes = () => call<{ doctypes: DocTypeDef[]; fieldtypes: string[] }>("/api/doctypes");
export const getDoctype = (name: string) => call<DocTypeDef>(`/api/doctypes/${q(name)}`);
export const saveDoctype = (def: Partial<DocTypeDef>, existing?: string) =>
  existing ? call<DocTypeDef>(`/api/doctypes/${q(existing)}`, "PUT", def) : call<DocTypeDef>("/api/doctypes", "POST", def);
export const deleteDoctype = (name: string) => call<{ ok: boolean }>(`/api/doctypes/${q(name)}`, "DELETE");

export const listRecords = (doctype: string, search = "", offset = 0) =>
  call<{ doctype: DocTypeDef; records: DocRecordRow[]; total: number }>(
    `/api/doc/${q(doctype)}?limit=50&offset=${offset}&q=${q(search)}`
  );
export const getRecord = (doctype: string, name: string) => call<DocRecordRow>(`/api/doc/${q(doctype)}/${q(name)}`);
export const saveRecord = (doctype: string, data: Record<string, unknown>, name?: string) =>
  name
    ? call<DocRecordRow>(`/api/doc/${q(doctype)}/${q(name)}`, "PUT", data)
    : call<DocRecordRow>(`/api/doc/${q(doctype)}`, "POST", data);
export const deleteRecord = (doctype: string, name: string) => call<{ ok: boolean }>(`/api/doc/${q(doctype)}/${q(name)}`, "DELETE");
export const linkOptions = (doctype: string) =>
  call<{ options: { name: string; title: string }[] }>(`/api/doc/${q(doctype)}/options`);
