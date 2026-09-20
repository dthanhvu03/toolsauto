import { getJson, sendJson, type OkMessage } from "@/shared/api/http";
import type { FbProTasksResponse } from "../types/fbProTasks.types";

export function fetchFbProTasks(params: { key?: string }) {
  const sp = new URLSearchParams();
  if (params.key) sp.set("key", params.key);
  const q = sp.toString();
  return getJson<FbProTasksResponse>(`/api/admin/fb-pro-tasks${q ? `?${q}` : ""}`);
}

export function saveFbProTasks(body: {
  scope_key?: string;
  notes?: string;
  target_posts?: number | null;
  target_reels?: number | null;
  target_interactions?: number | null;
}) {
  return sendJson<OkMessage>("/api/admin/fb-pro-tasks/save", "POST", body);
}

export function resetFbProWeek(scope_key?: string) {
  return sendJson<OkMessage>("/api/admin/fb-pro-tasks/reset-week", "POST", { scope_key: scope_key || "" });
}
