export type SyspanelResponse = {
  cpu: number;
  mem_pct: number;
  mem_used_gb: number;
  mem_total_gb: number;
  disk_pct: number;
  disk_used_gb: number;
  disk_total_gb: number;
  disk_label: string;
  jobs: Record<string, number>;
};

/** PLAN-115 — một app PM2 trên bảng tiến trình. */
export type ProcessApp = {
  name: string;
  label: string;
  role: string;
  if_stopped: string;
  status: string;
  cpu: number;
  mem_mb: number;
  uptime_s: number | null;
  restarts: number;
  pid: number | null;
  can_start: boolean;
  can_stop: boolean;
  can_restart: boolean;
};

export type ProcessesResponse = {
  machine: {
    cpu_pct: number;
    cpus: number;
    mem_total_mb: number;
    mem_used_mb: number;
    gpu: { name: string; mem_used_mb: number; mem_total_mb: number; util_pct: number } | null;
  };
  apps: ProcessApp[];
  error: string | null;
};

export type ProcessAction = "start" | "stop" | "restart";
