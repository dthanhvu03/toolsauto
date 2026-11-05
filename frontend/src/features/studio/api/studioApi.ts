import { getJson, postJsonBlob, sendForm, sendJson } from "@/shared/api/http";
import type {
  Asset,
  Channel,
  JobsResponse,
  ProjectDetail,
  ProjectSpec,
  ProjectsResponse,
  SetupResponse,
  TakeBody,
  Techniques,
  Template,
  TikTokItem,
  VoicesResponse,
} from "../types/studio.types";

const BASE = "/studio/api";
type Ok = { ok: boolean; task_id?: number };

export const projectVideoUrl = (id: number, v?: number | null) => `${BASE}/projects/${id}/video?v=${v ?? 0}`;
/** Tải bản render về máy (đăng tay). */
export const projectDownloadUrl = (id: number) => `${BASE}/projects/${id}/video?download=1`;
export const projectPosterUrl = (id: number, v?: number | null) => `${BASE}/projects/${id}/poster.jpg?v=${v ?? 0}`;
export const assetFileUrl = (id: number) => `${BASE}/assets/${id}/file`;
export const assetStripUrl = (id: number) => `${BASE}/assets/${id}/strip.jpg`;

export const fetchProjects = (status = "") =>
  getJson<ProjectsResponse>(`${BASE}/projects?limit=200${status ? `&status=${status}` : ""}`);
export const fetchProject = (id: number) => getJson<ProjectDetail>(`${BASE}/projects/${id}`);
export const saveSpec = (id: number, spec: ProjectSpec) => sendJson<Ok>(`${BASE}/projects/${id}/spec`, "PUT", { spec });
export const updateMeta = (id: number, body: { caption?: string; hashtags?: string[]; channel_id?: number }) =>
  sendJson<Ok>(`${BASE}/projects/${id}`, "PATCH", body);
export const redubProject = (id: number) => sendJson<Ok>(`${BASE}/projects/${id}/redub`, "POST", {});
export const recompose = (id: number, body: { template_id: number | null; channel_id?: number | null }) =>
  sendJson<Ok>(`${BASE}/projects/${id}/recompose`, "POST", body);
export const makeVariants = (id: number, n: number) =>
  sendJson<{ ok: boolean; task_ids: number[]; note: string }>(`${BASE}/projects/${id}/variants`, "POST", { n });
export const approveProject = (id: number, body: { caption?: string; hashtags?: string[] } = {}) =>
  sendJson<Ok>(`${BASE}/projects/${id}/approve`, "POST", body);
export const fetchJobs = (ids: number[] = []) => getJson<JobsResponse>(`${BASE}/jobs${ids.length ? `?ids=${ids.join(",")}` : ""}`);
export const markPosted = (id: number) => sendJson<Ok>(`${BASE}/projects/${id}/posted`, "POST", {});
export const scanTiktok = (url: string, limit: number) =>
  sendJson<{ items: TikTokItem[] }>(`${BASE}/tiktok/scan`, "POST", { url, limit });
export const takeTiktok = (body: TakeBody) =>
  sendJson<{ ok: boolean; count: number; task_ids: number[] }>(`${BASE}/tiktok/take`, "POST", body);
export const rejectProject = (id: number, reason = "") =>
  sendJson<Ok>(`${BASE}/projects/${id}/reject`, "POST", { reason });

export const fetchAssets = (kind = "") => getJson<{ assets: Asset[] }>(`${BASE}/assets${kind ? `?kind=${kind}` : ""}`);
export function uploadFile(
  file: File,
  opts: {
    channelId?: number | null;
    brand?: boolean;
    collected?: boolean;
    credit?: string;
    hasText?: boolean;
    techniques?: Techniques;
  }
) {
  const form = new FormData();
  form.append("file", file);
  if (opts.channelId) form.append("channel_id", String(opts.channelId));
  if (opts.brand) form.append("brand", "true");
  if (opts.collected) form.append("collected", "true");
  if (opts.credit) form.append("credit", opts.credit);
  if (opts.hasText) form.append("has_text", "true");
  if (opts.techniques) form.append("techniques", JSON.stringify(opts.techniques));
  return sendForm<Ok & { flow: string }>(`${BASE}/upload`, form);
}

/** ADR-064 Audio → Documentary POC */
export type DocConfig = {
  default_language: string;
  preview_sec: number;
  canvas: string;
  sources: string[];
  ai_keywords: boolean;
  rights_ok: string;
  rights_need_proof: boolean;
  languages: { code: string; label: string }[];
  settings_url: string;
};
export const fetchDocConfig = () => getJson<DocConfig>(`${BASE}/doc/config`);
export const uploadDocAudio = (
  file: File,
  opts: { channelId?: number | null; title?: string; language?: string } = {}
) => {
  const form = new FormData();
  form.append("file", file);
  if (opts.channelId) form.append("channel_id", String(opts.channelId));
  if (opts.title) form.append("title", opts.title);
  if (opts.language) form.append("language", opts.language);
  return sendForm<{ ok: boolean; task_id: number; flow: string }>(`${BASE}/doc/upload`, form);
};
export const fetchDocProject = (id: number) => getJson<Record<string, unknown>>(`${BASE}/doc/projects/${id}`);
export const saveDocTranscript = (id: number, segments: object[]) =>
  sendJson<Record<string, unknown>>(`${BASE}/doc/projects/${id}/transcript`, "PUT", { segments });
export const attachDocImage = (
  projectId: number,
  shotId: string,
  file: File,
  meta: {
    source_page?: string;
    credit?: string;
    license?: string;
    rights_status?: string;
    illustration?: boolean;
    proof_note?: string;
  }
) => {
  const form = new FormData();
  form.append("file", file);
  form.append("source_page", meta.source_page || "");
  form.append("credit", meta.credit || "");
  form.append("license", meta.license || "");
  form.append("rights_status", meta.rights_status || "RIGHTS_UNKNOWN");
  form.append("illustration", meta.illustration ? "true" : "false");
  form.append("proof_note", meta.proof_note || "");
  return sendForm<Record<string, unknown>>(`${BASE}/doc/projects/${projectId}/shots/${encodeURIComponent(shotId)}/image`, form);
};
export const searchDocImages = (projectId: number, shotId: string, keywords: string[]) =>
  sendJson<Record<string, unknown>>(
    `${BASE}/doc/projects/${projectId}/shots/${encodeURIComponent(shotId)}/search`,
    "POST",
    { keywords }
  );
export const pickDocImage = (projectId: number, shotId: string, index: number) =>
  sendJson<Record<string, unknown>>(
    `${BASE}/doc/projects/${projectId}/shots/${encodeURIComponent(shotId)}/pick`,
    "POST",
    { index }
  );
export const requestDocPreview = (id: number, requireRights = true) =>
  sendJson<{ ok: boolean; task_id: number; blockers: string[] }>(`${BASE}/doc/projects/${id}/preview`, "POST", {
    require_rights: requireRights,
  });

export const fetchSetup = () => getJson<SetupResponse>(`${BASE}/setup`);
export const createChannel = (body: Partial<Channel>) => sendJson<Channel>(`${BASE}/channels`, "POST", body);
export const updateChannel = (id: number, body: Partial<Channel>) => sendJson<Channel>(`${BASE}/channels/${id}`, "PATCH", body);
export const fetchVoices = () => getJson<VoicesResponse>(`${BASE}/voices`);
export const fetchVoicePreview = (voice: string) => postJsonBlob(`${BASE}/voices/preview`, { voice });
export const createTemplate = (body: Omit<Template, "id">) => sendJson<Template>(`${BASE}/templates`, "POST", body);
export const updateTemplate = (id: number, body: Omit<Template, "id">) =>
  sendJson<Template>(`${BASE}/templates/${id}`, "PUT", body);
