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

export type ViralRow = ViralResponse["items"][number];
