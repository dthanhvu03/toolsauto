import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchThreads, threadsLink, threadsScrape, threadsToggleAuto, threadsUnlink } from "../api/threadsApi";

export function useThreadsController() {
  const qc = useQueryClient();
  const [msg, setMsg] = useState("");
  const query = useQuery({ queryKey: ["admin-threads"], queryFn: fetchThreads });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-threads"] });
  const onOk = (r: { message: string }) => {
    setMsg(r.message);
    invalidate();
  };
  const onErr = (e: Error) => setMsg(e.message);

  const autoMut = useMutation({ mutationFn: threadsToggleAuto, onSuccess: onOk, onError: onErr });
  const scrapeMut = useMutation({ mutationFn: threadsScrape, onSuccess: onOk, onError: onErr });
  const linkMut = useMutation({ mutationFn: threadsLink, onSuccess: onOk, onError: onErr });
  const unlinkMut = useMutation({ mutationFn: threadsUnlink, onSuccess: onOk, onError: onErr });

  return {
    query,
    data: query.data,
    msg,
    busy: autoMut.isPending || scrapeMut.isPending || linkMut.isPending || unlinkMut.isPending,
    toggleAuto: () => autoMut.mutate(),
    scrape: () => scrapeMut.mutate(),
    link: (id: number) => linkMut.mutate(id),
    unlink: (id: number) => unlinkMut.mutate(id),
  };
}
