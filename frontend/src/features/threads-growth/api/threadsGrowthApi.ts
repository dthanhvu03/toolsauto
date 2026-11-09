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
  like_count: number;
  reply_count: number;
  author_followers: number;
  reach: number;
};

export type Quota = {
  allowed: boolean;
  reason: string;
  wait_sec: number;
  posted_last_hour: number;
  posted_last_day: number;
};

export type Customer = {
  bot: "cashbot" | "ai_store";
  variant: "A" | "B" | null;
  code: string;
  channel: string;
  user_id: number;
  username: string | null;
  joined_at: string | null;
  activity: string;
  active: boolean;
};

export type CustomerReport = {
  total: number;
  active: number;
  last_24h: number;
  by_variant: Record<string, Record<"A" | "B", { customers: number; active: number }>>;
  by_channel: Record<string, { customers: number; active: number }>;
  customers: Customer[];
  errors: string[];
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
    own_posts_enabled?: boolean;
    own_post_times?: string;
    followup_enabled?: boolean;
    followup_max_per_day?: number;
  };
  limits: {
    max_replies_per_hour: number;
    max_replies_per_day: number;
    min_delay_sec: number;
    max_delay_sec: number;
    min_relevance: number;
  };
  login: {
    login_status: string;
    login_error: string | null;
    logging_in: boolean;
    ready: boolean;
    profile_path?: string | null;
  };
  quota: Quota;
  stats: Record<string, Record<"A" | "B", Partial<Record<GrowthStatus, number>>>>;
  counts: Record<"pending" | "approved" | "posted" | "failed", number>;
  customers: CustomerReport;
  settings_url: string;
};

export type OwnPost = {
  id: number;
  slot: string;
  kind: "deal" | "sale";
  text: string;
  status: "posted" | "failed" | "skipped";
  post_url: string | null;
  error_message: string | null;
  created_at: string;
};

export type Followup = {
  id: number;
  author: string;
  comment: string;
  post_url: string;
  reply_text: string | null;
  reply_url: string | null;
  status: "answered" | "skipped" | "failed";
  error_message: string | null;
  created_at: string;
};

export const fetchOwnPosts = () => getJson<{ items: OwnPost[] }>(`${BASE}/own-posts?limit=10`);
export const fetchFollowups = () => getJson<{ items: Followup[] }>(`${BASE}/followups?limit=10`);
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
