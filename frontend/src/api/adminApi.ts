export type OverviewResponse = {
  accounts_count: number;
  accounts_active: number;
  state: {
    worker_status?: string;
    heartbeat_at?: number | null;
    current_job_id?: number | null;
    safe_mode?: boolean;
    engagement_status?: string | null;
  };
  queue: {
    counts: Record<string, number>;
    viral_new: number;
    viral_failed: number;
  };
  chart?: { categories: string[]; series: { name: string; data: number[] }[] };
  accounts: {
    id: number;
    name: string;
    platform: string;
    is_active: boolean;
    login_status?: string;
  }[];
};

export type JobsResponse = {
  jobs: {
    id: number;
    status: string;
    platform?: string;
    account_name?: string | null;
    target_page?: string | null;
    caption?: string;
    post_url?: string | null;
    schedule_ts?: number | null;
    error_message?: string;
  }[];
  total: number;
  total_pages: number;
  page: number;
};

export type AccountsResponse = {
  accounts: {
    id: number;
    name: string;
    platform: string;
    is_active: boolean;
    login_status?: string;
    daily_limit?: number;
    target_page?: string | null;
    consecutive_failures?: number;
  }[];
  total: number;
};

export type ViralResponse = {
  items: {
    id: number;
    url: string;
    platform?: string;
    status: string;
    views?: number;
    account_name?: string;
    has_reup?: boolean;
    is_mega?: boolean;
    job_id?: number;
    job_status?: string;
  }[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
  status_counts?: Record<string, number>;
  new_count?: number;
  failed_count?: number;
  ready_count?: number;
};

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { credentials: "same-origin" });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json() as Promise<T>;
}

export function fetchOverview() {
  return getJson<OverviewResponse>("/api/admin/overview");
}

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

export function fetchAccounts(params: { q?: string; platform?: string }) {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.platform) sp.set("platform", params.platform);
  return getJson<AccountsResponse>(`/api/admin/accounts?${sp}`);
}

export function fetchViral(params: {
  page?: number;
  q?: string;
  status?: string;
  platform?: string;
  min_views?: number;
}) {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.q) sp.set("q", params.q);
  if (params.status) sp.set("status", params.status);
  if (params.platform) sp.set("platform", params.platform);
  if (params.min_views) sp.set("min_views", String(params.min_views));
  sp.set("per_page", "50");
  return getJson<ViralResponse>(`/api/admin/viral?${sp}`);
}
