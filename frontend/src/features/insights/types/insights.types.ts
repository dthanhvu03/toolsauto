export type InsightsQuery = {
  platform?: string;
  days?: number;
  page?: number;
  limit?: number;
};

export type GrowthPoint = { date: string; views: number; likes: number };

export type GrowthResponse = {
  status: string;
  data: GrowthPoint[];
};

export type TopPost = {
  post_url: string;
  page_name?: string | null;
  platform?: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  caption?: string;
  published_date?: string;
  velocity?: number;
  engagement_rate?: number;
};

export type TopPostsResponse = {
  status: string;
  data: TopPost[];
  total: number;
  page: number;
  total_pages: number;
};

export type SecondaryMetrics = {
  avg_views: number;
  total_shares: number;
  engagement_rate: number;
  posts_count: number;
};

export type SecondaryResponse = {
  status: string;
  data: SecondaryMetrics;
};

export type PageAnalysisItem = {
  page_name: string;
  page_url?: string | null;
  status: string;
  color?: string;
  growth_pct: number;
  views: number;
  advice?: string;
  priority?: number;
  is_ai?: boolean;
};

export type PageAnalysisResponse = {
  status: string;
  data: PageAnalysisItem[];
};
