import { getJson, sendJson, type OkMessage } from "@/shared/api/http";
import type { SyspanelResponse } from "../types/syspanel.types";

export function fetchSyspanel() {
  return getJson<SyspanelResponse>("/api/admin/syspanel");
}

export function syspanelRetryFailed() {
  return sendJson<OkMessage>("/api/admin/syspanel/retry-failed", "POST");
}

export function syspanelCancelStuck() {
  return sendJson<OkMessage>("/api/admin/syspanel/cancel-stuck", "POST");
}

export function syspanelWorker(action: "pause" | "resume" | "safe-mode") {
  return sendJson<OkMessage>(`/api/admin/syspanel/worker/${action}`, "POST");
}
