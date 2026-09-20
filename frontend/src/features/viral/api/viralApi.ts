import { getJson, sendJson, type OkMessage } from "@/shared/api/http";
import type { ViralResponse } from "../types/viral.types";

export type ViralRowAction = "process" | "posted" | "unposted" | "delete";

export function fetchViral(params: {
  page?: number;
  q?: string;
  status?: string;
  platform?: string;
  min_views?: number;
}) {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.q) sp.set("q", params.q);
  if (params.status) sp.set("status", params.status);
  if (params.platform) sp.set("platform", params.platform);
  if (params.min_views) sp.set("min_views", String(params.min_views));
  sp.set("per_page", "50");
  return getJson<ViralResponse>(`/api/admin/viral?${sp}`);
}

export function addViralLink(body: { url: string; target_page?: string; process_now?: boolean }) {
  return sendJson<OkMessage>("/api/admin/viral/add-link", "POST", body);
}

export function processNewViral(limit = 3) {
  return sendJson<OkMessage>("/api/admin/viral/process-new", "POST", { limit });
}

export function postViralAction(id: number, action: ViralRowAction) {
  return sendJson<OkMessage>(`/api/admin/viral/${id}/${action}`, "POST");
}
