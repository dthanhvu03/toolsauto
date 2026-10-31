export type ComplianceKeyword = {
  id: number;
  keyword: string;
  category: string;
  severity: string;
  source?: string | null;
  is_active: boolean;
  created_at?: number | null;
};

export type ComplianceCategory = {
  category: string;
  total: number;
  violations: number;
  warnings: number;
  active: number;
  label: string;
};

export type ComplianceAnalytics = {
  total_keywords: number;
  total_violations: number;
  blocked_today: number;
  rewritten_count: number;
};
