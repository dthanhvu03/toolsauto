import { getJson, sendJson, type OkMessage } from "@/shared/api/http";
import type { ViralSourcesResponse } from "../types/viralSources.types";

export function fetchViralSources() {
  return getJson<ViralSourcesResponse>("/api/admin/viral-sources");
}

export function addViralSource(body: { url: string; target_page?: string }) {
  return sendJson<OkMessage>("/api/admin/viral-sources", "POST", body);
}

export function toggleViralSource(id: number) {
  return sendJson<OkMessage>(`/api/admin/viral-sources/${id}/toggle`, "POST");
}

export function scanViralSource(id: number) {
  return sendJson<OkMessage>(`/api/admin/viral-sources/${id}/scan`, "POST");
}

export function deleteViralSource(id: number) {
  return sendJson<OkMessage>(`/api/admin/viral-sources/${id}`, "DELETE");
}
