import { getJson } from "@/shared/api/http";
import type { JobsResponse } from "../types/jobs.types";

/** Job Buffer — mỗi dòng là một lần đưa video lên Buffer (DONE = Buffer đã nhận và hẹn giờ). */
export function fetchJobs(params: { status?: string; page?: number; q?: string }) {
  const sp = new URLSearchParams({ platform: "buffer" });
  if (params.status) sp.set("status", params.status);
  if (params.page) sp.set("page", String(params.page));
  if (params.q) sp.set("q", params.q);
  return getJson<JobsResponse>(`/api/admin/jobs?${sp}`);
}
