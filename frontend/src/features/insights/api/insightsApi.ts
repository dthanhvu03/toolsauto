import { getJson, sendJson } from "@/shared/api/http";
import type {
  GrowthResponse,
  InsightsQuery,
  PageAnalysisResponse,
  SecondaryResponse,
  TopPostsResponse,
} from "../types/insights.types";

function qs(params: InsightsQuery) {
  const sp = new URLSearchParams();
  if (params.platform) sp.set("platform", params.platform);
  if (params.days) sp.set("days", String(params.days));
  if (params.page) sp.set("page", String(params.page));
  if (params.limit) sp.set("limit", String(params.limit));
  return `?${sp}`;
}

export function fetchGrowth(params: InsightsQuery) {
  return getJson<GrowthResponse>(`/insights/api/growth${qs(params)}`);
}

export function fetchTopPosts(params: InsightsQuery) {
  return getJson<TopPostsResponse>(`/insights/api/top-posts${qs(params)}`);
}

export function fetchSecondary(params: InsightsQuery) {
  return getJson<SecondaryResponse>(`/insights/api/secondary-metrics${qs(params)}`);
}

export function fetchPageAnalysis(platform: string) {
  const sp = new URLSearchParams();
  if (platform) sp.set("platform", platform);
  return getJson<PageAnalysisResponse>(`/insights/api/page-analysis?${sp}`);
}

export function triggerInsightsRefresh() {
  return sendJson("/insights/api/trigger-refresh", "POST");
}
