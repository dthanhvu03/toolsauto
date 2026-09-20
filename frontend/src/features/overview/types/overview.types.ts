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
