import { getJson, sendJson, type OkMessage } from "@/shared/api/http";
import type { ThreadsResponse } from "../types/threads.types";

export function fetchThreads() {
  return getJson<ThreadsResponse>("/api/admin/threads");
}

export function threadsToggleAuto() {
  return sendJson<OkMessage>("/api/admin/threads/toggle-auto", "POST");
}

export function threadsScrape() {
  return sendJson<OkMessage>("/api/admin/threads/trigger-scrape", "POST");
}

export function threadsLink(account_id: number) {
  return sendJson<OkMessage>("/api/admin/threads/link", "POST", { account_id });
}

export function threadsUnlink(account_id: number) {
  return sendJson<OkMessage>("/api/admin/threads/unlink", "POST", { account_id });
}
