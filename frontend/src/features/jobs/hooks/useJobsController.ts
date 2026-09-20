import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchAccounts } from "@/features/accounts/api/accountsApi";
import { createManualJob, fetchJobs, postJobAction } from "../api/jobsApi";
import type { JobAction } from "../types/jobs.types";

export function useJobsController(options?: { defaultPlatform?: string }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState("active");
  const [platform, setPlatform] = useState(options?.defaultPlatform ?? "");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [qDraft, setQDraft] = useState("");
  const [msg, setMsg] = useState("");

  const query = useQuery({
    queryKey: ["admin-jobs", status, platform, q, page],
    queryFn: () => fetchJobs({ status, platform, q, page }),
  });
  const accountsQ = useQuery({
    queryKey: ["admin-accounts", "", ""],
    queryFn: () => fetchAccounts({ q: "", platform: "" }),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-jobs"] });

  const actionMut = useMutation({
    mutationFn: ({ id, action }: { id: number; action: JobAction }) => postJobAction(id, action),
    onSuccess: (r) => {
      setMsg(r.message);
      invalidate();
    },
    onError: (e: Error) => setMsg(e.message),
  });
  const createMut = useMutation({
    mutationFn: createManualJob,
    onSuccess: (r) => {
      setMsg(r.message);
      invalidate();
    },
    onError: (e: Error) => setMsg(e.message),
  });

  const rows = query.data?.jobs ?? [];
  const totalPages = query.data?.total_pages ?? 1;
  const subtitle = useMemo(() => {
    if (!query.data) return "";
    return `${query.data.total} jobs · trang ${query.data.page}/${query.data.total_pages}`;
  }, [query.data]);

  const applySearch = () => {
    setPage(1);
    setQ(qDraft.trim());
  };
  const changeStatus = (value: string) => {
    setPage(1);
    setStatus(value);
  };
  const changePlatform = (value: string) => {
    setPage(1);
    setPlatform(value);
  };

  return {
    status,
    platform,
    qDraft,
    page,
    totalPages,
    rows,
    subtitle,
    query,
    msg,
    accounts: accountsQ.data?.accounts ?? [],
    busyId: actionMut.isPending ? (actionMut.variables?.id ?? null) : null,
    creating: createMut.isPending,
    setQDraft,
    setPage,
    applySearch,
    changeStatus,
    changePlatform,
    runAction: (id: number, action: JobAction) => actionMut.mutate({ id, action }),
    createJob: (form: FormData) => createMut.mutate(form),
  };
}
