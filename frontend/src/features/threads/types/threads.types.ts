export type ThreadsStats = { pending: number; success: number; failed: number };

export type ThreadsAccount = {
  id: number;
  name: string;
  platform: string;
  login_status?: string | null;
};

export type ThreadsArticle = {
  id: number;
  title: string;
  source_name?: string | null;
  status?: string | null;
};

export type ThreadsJob = {
  id: number;
  status: string;
  job_type?: string | null;
  caption?: string | null;
};

export type ThreadsResponse = {
  stats: ThreadsStats;
  articles: ThreadsArticle[];
  jobs: ThreadsJob[];
  linked_accounts: ThreadsAccount[];
  verifying_accounts: ThreadsAccount[];
  available_accounts: ThreadsAccount[];
  failed_verifications: Record<string, string>;
};
