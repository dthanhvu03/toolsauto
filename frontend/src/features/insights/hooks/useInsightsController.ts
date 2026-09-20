import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  fetchGrowth,
  fetchPageAnalysis,
  fetchSecondary,
  fetchTopPosts,
  triggerInsightsRefresh,
} from "../api/insightsApi";

export function useInsightsController() {
  const [platform, setPlatform] = useState("facebook");
  const [days, setDays] = useState(7);
  const [page, setPage] = useState(1);
  const [msg, setMsg] = useState("");
  const refreshMut = useMutation({
    mutationFn: triggerInsightsRefresh,
    onSuccess: () => setMsg("Đã kích hoạt refresh insights"),
    onError: (e: Error) => setMsg(e.message),
  });

  const filters = { platform, days };

  const growth = useQuery({
    queryKey: ["insights-growth", platform, days],
    queryFn: () => fetchGrowth(filters),
  });
  const secondary = useQuery({
    queryKey: ["insights-secondary", platform, days],
    queryFn: () => fetchSecondary(filters),
  });
  const topPosts = useQuery({
    queryKey: ["insights-top-posts", platform, days, page],
    queryFn: () => fetchTopPosts({ ...filters, page, limit: 6 }),
  });
  const analysis = useQuery({
    queryKey: ["insights-analysis", platform],
    queryFn: () => fetchPageAnalysis(platform),
  });

  const totals = useMemo(() => {
    const series = growth.data?.data ?? [];
    return {
      views: series.reduce((s, d) => s + (d.views || 0), 0),
      likes: series.reduce((s, d) => s + (d.likes || 0), 0),
    };
  }, [growth.data]);

  const changePlatform = (value: string) => {
    setPage(1);
    setPlatform(value);
  };
  const changeDays = (value: number) => {
    setPage(1);
    setDays(value);
  };

  const isLoading = growth.isLoading || secondary.isLoading || topPosts.isLoading;
  const isError = growth.isError || secondary.isError || topPosts.isError;

  return {
    platform,
    days,
    page,
    totals,
    secondary: secondary.data?.data,
    posts: topPosts.data?.data ?? [],
    totalPages: topPosts.data?.total_pages ?? 1,
    analysis: analysis.data?.data ?? [],
    analysisQuery: analysis,
    growthPending: growth.isLoading,
    isLoading,
    isError,
    setPage,
    changePlatform,
    changeDays,
    msg,
    refresh: () => refreshMut.mutate(),
    refreshing: refreshMut.isPending,
  };
}
