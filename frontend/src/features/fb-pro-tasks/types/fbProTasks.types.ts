export type FbProScopeOption = {
  key: string;
  label: string;
  account_id?: number | null;
  target_page?: string;
};

export type FbProTask = {
  key: string;
  label: string;
  current: number;
  target: number;
  source: string;
  auto?: number | null;
  pct: number;
  remaining: number;
};

export type FbProQueueHint = {
  id: number;
  status: string;
  target_page: string;
  caption: string;
  media_name: string;
  is_video: boolean;
};

export type FbProTasksResponse = {
  scope_key: string;
  scope_label: string;
  account_id?: number | null;
  account_name: string;
  target_page: string;
  page_slug: string;
  scope_options: FbProScopeOption[];
  week_start: string;
  week_end: string;
  week_label: string;
  days_left: number;
  overall_pct: number;
  tasks: FbProTask[];
  auto: { posts?: number; reels?: number };
  meta_url: string;
  queue_hints: FbProQueueHint[];
  notes: string;
  updated_at: number;
};
