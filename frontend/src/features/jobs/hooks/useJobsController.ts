import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJobs } from "../api/jobsApi";

export function useJobsController() {
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [qDraft, setQDraft] = useState("");

  const query = useQuery({
    queryKey: ["admin-jobs", status, q, page],
    queryFn: () => fetchJobs({ status, q, page }),
  });

  const subtitle = useMemo(() => {
    if (!query.data) return "";
    return `${query.data.total} lượt đưa lên Buffer · trang ${query.data.page}/${query.data.total_pages}`;
  }, [query.data]);

  return {
    status,
    qDraft,
    page,
    totalPages: query.data?.total_pages ?? 1,
    rows: query.data?.jobs ?? [],
    subtitle,
    query,
    setQDraft,
    setPage,
    applySearch: () => {
      setPage(1);
      setQ(qDraft.trim());
    },
    changeStatus: (value: string) => {
      setPage(1);
      setStatus(value);
    },
  };
}
