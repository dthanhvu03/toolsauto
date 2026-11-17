import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { fetchLogs } from "../api/logsApi";

export function useLogsController() {
  const [qDraft, setQDraft] = useState("");
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("");
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ["admin-logs", q, level, page],
    queryFn: () => fetchLogs({ q, level, page }),
    placeholderData: keepPreviousData,
  });

  const applySearch = () => {
    setPage(1);
    setQ(qDraft.trim());
  };
  const changeLevel = (value: string) => {
    setPage(1);
    setLevel(value);
  };

  return {
    qDraft,
    setQDraft,
    applySearch,
    level,
    changeLevel,
    page,
    setPage,
    query,
    events: query.data?.events ?? [],
    total: query.data?.total ?? 0,
    totalPages: query.data?.total_pages ?? 1,
  };
}
