export type ChannelOps = {
  id: string;
  name: string;
  /** READY nhưng chưa đưa lên Buffer */
  ready_waiting: number;
  /** đã lên Buffer, chưa tới giờ đăng */
  scheduled: number;
  next_at: number | null;
  posted_7d: number;
};

export type FailedJob = {
  id: number;
  status?: string;
  channel?: string | null;
  error?: string;
  finished_at?: number | null;
};

export type OverviewResponse = {
  generated_at: number;
  channels: ChannelOps[];
  jobs_24h: Record<string, number>;
  materials_7d: Record<string, number>;
  failed_jobs: { count: number; latest: FailedJob[] };
  disk: {
    free_gb: number;
    used_gb: number;
    total_gb: number;
    pct: number;
    label: string;
    pause_below_gb: number;
    below_pause: boolean;
  };
};
