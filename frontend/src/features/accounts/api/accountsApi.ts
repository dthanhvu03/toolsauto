import { getJson, sendJson, type OkMessage } from "@/shared/api/http";
import type { AccountsResponse } from "../types/accounts.types";

export function fetchAccounts(params: { q?: string; platform?: string }) {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.platform) sp.set("platform", params.platform);
  return getJson<AccountsResponse>(`/api/admin/accounts?${sp}`);
}

export function createAccount(body: {
  name: string;
  platform: string;
  daily_limit?: number;
}) {
  return sendJson<OkMessage>("/api/admin/accounts", "POST", body);
}

export function toggleAccount(id: number) {
  return sendJson<OkMessage>(`/api/admin/accounts/${id}/toggle`, "POST");
}

export function renameAccount(id: number, name: string) {
  return sendJson<OkMessage>(`/api/admin/accounts/${id}/rename`, "POST", { name });
}

export function deleteAccount(id: number) {
  return sendJson<OkMessage>(`/api/admin/accounts/${id}/delete`, "POST");
}

export function startAccountLogin(id: number) {
  return sendJson<OkMessage>(`/api/admin/accounts/${id}/start-login`, "POST");
}

export function confirmAccountLogin(id: number) {
  return sendJson<OkMessage>(`/api/admin/accounts/${id}/confirm-login`, "POST");
}
