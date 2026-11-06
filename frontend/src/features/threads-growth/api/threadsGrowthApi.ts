import { getJson, sendJson } from "@/shared/api/http";

const BASE = "/threads-growth/api";

export type GrowthStatus = "pending" | "approved" | "rejected" | "posted" | "failed";

export type GrowthPost = {
  id: number;
  thread_id: string;
  post_url: string;
  author: string;
  content: string;
  target_bot: "cashbot" | "ai_store";
  variant: "A" | "B";
  relevance_score: number;
  ai_analysis: string | null;
  suggested_reply: string;
  actual_reply: string | null;
  status: GrowthStatus;
  error_message: string | null;
  created_at: string;
  posted_at: string | null;
  reply_url: string | null;
  auto_approved: number;
  post_created_at: string | null;
};

export type Quota = {
  allowed: boolean;
  reason: string;
  wait_sec: number;
  posted_last_hour: number;
  posted_last_day: number;
};

export type Overview = {
  enabled: boolean;
  worker: {
    scan_interval_min: number;
    auto_post_min_relevance: number;
    max_post_age_hours: number;
    author_cooldown_days: number;
    posts_per_keyword: number;
    vietnamese_only: boolean;
    top_level_only: boolean;
  };
  limits: {
    max_replies_per_hour: number;
    max_replies_per_day: number;
    min_delay_sec: number;
    max_delay_sec: number;
    min_relevance: number;
  };
  login: { login_status: string; login_error: string | null; logging_in: boolean; ready: boolean };
  quota: Quota;
  stats: Record<string, Record<"A" | "B", Partial<Record<GrowthStatus, number>>>>;
  counts: Record<"pending" | "approved" | "posted" | "failed", number>;
  settings_url: string;
};

export const fetchOverview = () => getJson<Overview>(`${BASE}/overview`);
export const fetchPosts = (status: GrowthStatus) =>
  getJson<{ items: GrowthPost[] }>(`${BASE}/posts?status=${status}&limit=100`);
export const approvePost = (id: number, reply?: string) =>
  sendJson<{ post: GrowthPost }>(`${BASE}/posts/${id}/approve`, "POST", { reply: reply ?? null });
export const rejectPost = (id: number) => sendJson<{ post: GrowthPost }>(`${BASE}/posts/${id}/reject`, "POST");
export const switchPost = (id: number) => sendJson<{ post: GrowthPost }>(`${BASE}/posts/${id}/switch`, "POST", {});
export const toggleGrowth = (enabled: boolean) =>
  sendJson<{ enabled: boolean }>(`${BASE}/toggle`, "POST", { enabled });
export const startLogin = () => sendJson<{ login: Overview["login"] }>(`${BASE}/login`, "POST");
