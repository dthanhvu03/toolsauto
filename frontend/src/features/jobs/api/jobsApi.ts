import { getJson, sendForm, sendJson, type OkMessage } from "@/shared/api/http";
import type { JobAction, JobsResponse } from "../types/jobs.types";

export function fetchJobs(params: {
  status?: string;
  page?: number;
  q?: string;
  platform?: string;
}) {
  const sp = new URLSearchParams();
  if (params.status) sp.set("status", params.status);
  if (params.page) sp.set("page", String(params.page));
  if (params.q) sp.set("q", params.q);
  if (params.platform) sp.set("platform", params.platform);
  return getJson<JobsResponse>(`/api/admin/jobs?${sp}`);
}

export function postJobAction(id: number, action: JobAction) {
  return sendJson<OkMessage>(`/api/admin/jobs/${id}/${action}`, "POST");
}

export function createManualJob(form: FormData) {
  return sendForm<OkMessage>("/api/admin/jobs/manual", form);
}

