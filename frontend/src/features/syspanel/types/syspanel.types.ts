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
