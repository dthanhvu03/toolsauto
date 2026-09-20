export type CockpitJob = {
  id: number;
  status?: string;
  account_name?: string | null;
  error?: string;
  finished_at?: number | null;
};

export type CockpitCheckpointItem = {
  id: number;
  kind: string;
  account_name?: string | null;
  detail?: string;
  at?: number | null;
};

export type OverviewOps = {
  worker: {
    status: string;
    raw_status?: string | null;
    safe_mode: boolean;
    heartbeat_at?: number | null;
    heartbeat_age_seconds?: number | null;
    current_job_id?: number | null;
  };
  disk: {
    free_gb: number;
    used_gb: number;
    total_gb: number;
    pct: number;
    label: string;
    pause_below_gb: number;
    below_pause: boolean;
  };
  gemini_circuit: {
    open: boolean;
    reset_at?: number | null;
  };
  checkpoint: {
    count: number;
    jobs?: number;
    accounts?: number;
    sessions?: number;
    latest: CockpitCheckpointItem[];
  };
  failed_jobs: {
    count: number;
    latest: CockpitJob[];
  };
};

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
  ops?: OverviewOps;
};
