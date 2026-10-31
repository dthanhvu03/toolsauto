import { getJson, postJsonBlob, sendForm, sendJson } from "@/shared/api/http";
import type {
  Asset,
  Channel,
  ProjectDetail,
  ProjectSpec,
  ProjectsResponse,
  SetupResponse,
  TakeBody,
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
export const recompose = (id: number, body: { template_id: number | null; channel_id?: number | null }) =>
  sendJson<Ok>(`${BASE}/projects/${id}/recompose`, "POST", body);
export const makeVariants = (id: number, n: number) =>
  sendJson<{ ok: boolean; task_ids: number[]; note: string }>(`${BASE}/projects/${id}/variants`, "POST", { n });
export const approveProject = (id: number, body: { caption?: string; hashtags?: string[] } = {}) =>
  sendJson<Ok>(`${BASE}/projects/${id}/approve`, "POST", body);
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
  opts: { channelId?: number | null; brand?: boolean; collected?: boolean; credit?: string; hasText?: boolean }
) {
  const form = new FormData();
  form.append("file", file);
  if (opts.channelId) form.append("channel_id", String(opts.channelId));
  if (opts.brand) form.append("brand", "true");
  if (opts.collected) form.append("collected", "true");
  if (opts.credit) form.append("credit", opts.credit);
  if (opts.hasText) form.append("has_text", "true");
  return sendForm<Ok & { flow: string }>(`${BASE}/upload`, form);
}

export const fetchSetup = () => getJson<SetupResponse>(`${BASE}/setup`);
export const createChannel = (body: Partial<Channel>) => sendJson<Channel>(`${BASE}/channels`, "POST", body);
export const updateChannel = (id: number, body: Partial<Channel>) => sendJson<Channel>(`${BASE}/channels/${id}`, "PATCH", body);
export const fetchVoices = () => getJson<VoicesResponse>(`${BASE}/voices`);
export const fetchVoicePreview = (voice: string) => postJsonBlob(`${BASE}/voices/preview`, { voice });
export const createTemplate = (body: Omit<Template, "id">) => sendJson<Template>(`${BASE}/templates`, "POST", body);
export const updateTemplate = (id: number, body: Omit<Template, "id">) =>
  sendJson<Template>(`${BASE}/templates/${id}`, "PUT", body);
