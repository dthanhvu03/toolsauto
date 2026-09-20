import { getJson } from "@/shared/api/http";
import type { OverviewResponse } from "../types/overview.types";

export function fetchOverview() {
  return getJson<OverviewResponse>("/api/admin/overview");
}
