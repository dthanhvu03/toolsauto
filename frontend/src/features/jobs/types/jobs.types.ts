export type JobRow = {
  id: number;
  status: string;
  target_page?: string | null;
  channel?: string | null;
  material_id?: number | null;
  caption?: string;
  schedule_ts?: number | null;
  finished_at?: number | null;
  error_message?: string;
};

export type JobsResponse = {
  jobs: JobRow[];
  total: number;
  total_pages: number;
  page: number;
};
