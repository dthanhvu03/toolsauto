export type JobsResponse = {
  jobs: {
    id: number;
    status: string;
    platform?: string;
    job_type?: string | null;
    account_name?: string | null;
    target_page?: string | null;
    caption?: string;
    post_url?: string | null;
    schedule_ts?: number | null;
    error_message?: string;
  }[];
  total: number;
  total_pages: number;
  page: number;
};

export type JobRow = JobsResponse["jobs"][number];
export type JobAction = "retry" | "cancel" | "approve" | "reset-draft" | "force-run";
