import { getJson, sendJson, type OkMessage } from "@/shared/api/http";
import type { AffiliatesResponse, AffiliateRow } from "../types/affiliates.types";

export function fetchAffiliates(params: { q?: string; page?: number }) {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.page) sp.set("page", String(params.page));
  return getJson<AffiliatesResponse>(`/api/admin/affiliates?${sp}`);
}

export function saveAffiliate(body: {
  id?: number;
  keyword: string;
  url: string;
  comment_template: string;
  commission_rate?: number | null;
}) {
  return sendJson<OkMessage>("/api/admin/affiliates", "POST", body);
}

export function deleteAffiliate(id: number) {
  return sendJson<OkMessage>(`/api/admin/affiliates/${id}`, "DELETE");
}

export type { AffiliateRow };
