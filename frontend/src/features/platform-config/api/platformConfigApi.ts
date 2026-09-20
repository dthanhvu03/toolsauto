import { getJson } from "@/shared/api/http";
import type { PlatformRow, WorkflowRow } from "../types/platformConfig.types";

export function fetchPlatforms() {
  return getJson<PlatformRow[]>("/platform-config/platforms");
}

export function fetchWorkflows() {
  return getJson<WorkflowRow[]>("/platform-config/workflows");
}
