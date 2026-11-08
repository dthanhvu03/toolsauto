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
  /** Chỉ có ở bot systemd: nhóm bot + lệnh restart chủ bot tự chạy. */
  group?: string;
  manage?: string;
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
  /** Bot chạy bằng systemd (cashback, AI Pass Store) — chỉ xem. */
  services?: ProcessApp[];
  services_error?: string | null;
};

export type ProcessAction = "start" | "stop" | "restart";

/** Máy Windows chứa WSL — chỉ xem, server giữ số liệu 8 giây. */
export type WindowsProcess = {
  name: string;
  label: string;
  count: number;
  mem_mb: number;
  /** % trên cả máy (100% = mọi nhân); null ở lần đọc đầu. */
  cpu_pct: number | null;
};

export type WindowsDisk = { drive: string; label: string; total_gb: number; used_gb: number; free_gb: number };

export type WindowsHostResponse = {
  available: boolean;
  error: string | null;
  age_s: number;
  cpu_pct?: number;
  cpu_name?: string;
  cpus?: number;
  mem_total_mb?: number;
  mem_used_mb?: number;
  uptime_s?: number | null;
  disks?: WindowsDisk[];
  wsl_mem_mb?: number | null;
  top?: WindowsProcess[];
  process_count?: number;
};
