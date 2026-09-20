export type ViralSourceRow = {
  id: number;
  platform: string;
  url: string;
  handle?: string | null;
  min_views?: number | null;
  max_videos?: number | null;
  target_pages: string[];
  enabled: boolean;
  last_scanned_at?: number | null;
  last_found?: number | null;
  last_error?: string | null;
};

export type ViralSourcesResponse = {
  items: ViralSourceRow[];
  total: number;
};
