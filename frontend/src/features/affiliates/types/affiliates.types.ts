export type AffiliateRow = {
  id: number;
  keyword: string;
  url: string;
  comment_template?: string | null;
  commission_rate?: number | null;
  ai_status?: string | null;
};

export type AffiliatesResponse = {
  links: AffiliateRow[];
  total: number;
  page: number;
  total_pages: number;
  q?: string;
};
