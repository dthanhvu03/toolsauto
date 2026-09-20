import { getJson, sendJson } from "@/shared/api/http";
import type { DatabaseResponse } from "../types/database.types";

export type TablePreview = {
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
};

export type SqlResult = {
  status: string;
  message?: string;
  columns?: string[];
  rows?: Record<string, unknown>[];
  affected_rows?: number;
};

export function fetchDatabase() {
  return getJson<DatabaseResponse>("/api/admin/database");
}

export function fetchTable(name: string, q = "") {
  const sp = new URLSearchParams({ limit: "50" });
  if (q) sp.set("q", q);
  return getJson<TablePreview>(`/api/admin/database/tables/${encodeURIComponent(name)}?${sp}`);
}

export function runSql(sql: string, confirmed: boolean) {
  return sendJson<SqlResult>("/api/admin/database/sql", "POST", { sql, confirmed });
}
