import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addViralLink, fetchViral, postViralAction, processNewViral, type ViralRowAction } from "../api/viralApi";

export function useViralController() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [platform, setPlatform] = useState("");
  const [page, setPage] = useState(1);
  const [qDraft, setQDraft] = useState("");
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");

  const query = useQuery({
    queryKey: ["admin-viral", status, platform, q, page],
    queryFn: () => fetchViral({ status, platform, q, page }),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-viral"] });

  const actionMut = useMutation({
    mutationFn: ({ id, action }: { id: number; action: ViralRowAction }) => postViralAction(id, action),
    onSuccess: (r) => {
      setMsg(r.message);
      invalidate();
    },
    onError: (e: Error) => setMsg(e.message),
  });
  const addMut = useMutation({
    mutationFn: ({ url, process_now }: { url: string; process_now: boolean }) =>
      addViralLink({ url, process_now }),
    onSuccess: (r) => {
      setMsg(r.message);
      invalidate();
    },
    onError: (e: Error) => setMsg(e.message),
  });
  const processNewMut = useMutation({
    mutationFn: () => processNewViral(3),
    onSuccess: (r) => {
      setMsg(r.message);
      invalidate();
    },
    onError: (e: Error) => setMsg(e.message),
  });

  const items = query.data?.items ?? [];
  const totalPages = query.data?.total_pages ?? 1;
  const busy = addMut.isPending || processNewMut.isPending;

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
    items,
    query,
    msg,
    busy,
    busyId: actionMut.isPending ? (actionMut.variables?.id ?? null) : null,
    setQDraft,
    setPage,
    applySearch,
    changeStatus,
    changePlatform,
    runAction: (id: number, action: ViralRowAction) => actionMut.mutate({ id, action }),
    addLink: (url: string, processNow: boolean) => addMut.mutate({ url, process_now: processNow }),
    processNew: () => processNewMut.mutate(),
  };
}
