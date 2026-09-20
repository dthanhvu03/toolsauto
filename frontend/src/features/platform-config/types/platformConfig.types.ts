export type PlatformRow = {
  id: number;
  platform: string;
  adapter_class?: string | null;
  display_name?: string | null;
  display_emoji?: string | null;
  is_active: boolean;
};

export type WorkflowRow = {
  id: number;
  name: string;
  platform: string;
  job_type: string;
  is_active: boolean;
  steps?: unknown[];
};
