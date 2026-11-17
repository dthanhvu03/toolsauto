import { getJson } from "@/shared/api/http";
import type { LogsResponse } from "../types/logs.types";

export function fetchLogs(params: { q?: string; level?: string; page?: number }) {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.level) sp.set("level", params.level);
  if (params.page) sp.set("page", String(params.page));
  return getJson<LogsResponse>(`/api/admin/logs?${sp}`);
}
