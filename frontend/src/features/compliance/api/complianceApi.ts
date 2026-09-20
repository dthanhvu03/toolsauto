import { getJson, sendJson } from "@/shared/api/http";
import type {
  ComplianceAnalytics,
  ComplianceCategory,
  ComplianceKeyword,
  ViolationsResponse,
} from "../types/compliance.types";

function qs(params: Record<string, string | number | undefined>) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === "") continue;
    sp.set(k, String(v));
  }
  const q = sp.toString();
  return q ? `?${q}` : "";
}

export function fetchAnalytics(days = 30) {
  return getJson<ComplianceAnalytics>(`/compliance/analytics${qs({ days })}`);
}

export function fetchKeywords(params: { category?: string; severity?: string; search?: string }) {
  return getJson<ComplianceKeyword[]>(`/compliance/keywords${qs(params)}`);
}

export function fetchCategories() {
  return getJson<ComplianceCategory[]>("/compliance/categories");
}

export function fetchViolations(params: { days?: number; action?: string; page?: number; limit?: number }) {
  return getJson<ViolationsResponse>(`/compliance/violations${qs(params)}`);
}

export function addKeyword(body: { keyword: string; category?: string; severity?: string }) {
  return sendJson("/compliance/keywords", "POST", body);
}

export function toggleKeyword(id: number) {
  return sendJson(`/compliance/keywords/${id}/toggle`, "PATCH");
}

export function deleteKeyword(id: number) {
  return sendJson(`/compliance/keywords/${id}`, "DELETE");
}

export function testCheck(content: string) {
  return sendJson("/compliance/test-check", "POST", { content });
}
