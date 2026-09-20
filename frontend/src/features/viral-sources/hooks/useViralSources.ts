import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addViralSource,
  deleteViralSource,
  fetchViralSources,
  scanViralSource,
  toggleViralSource,
} from "../api/viralSourcesApi";

export function useViralSources() {
  const qc = useQueryClient();
  const [msg, setMsg] = useState("");
  const query = useQuery({ queryKey: ["admin-viral-sources"], queryFn: fetchViralSources });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-viral-sources"] });
  const onOk = (r: { message: string }) => {
    setMsg(r.message);
    invalidate();
  };
  const onErr = (e: Error) => setMsg(e.message);

  const addMut = useMutation({ mutationFn: addViralSource, onSuccess: onOk, onError: onErr });
  const toggleMut = useMutation({ mutationFn: toggleViralSource, onSuccess: onOk, onError: onErr });
  const scanMut = useMutation({ mutationFn: scanViralSource, onSuccess: onOk, onError: onErr });
  const delMut = useMutation({ mutationFn: deleteViralSource, onSuccess: onOk, onError: onErr });

  return {
    ...query,
    msg,
    adding: addMut.isPending,
    busyId: (toggleMut.variables as number | undefined) ??
      (scanMut.variables as number | undefined) ??
      (delMut.variables as number | undefined) ??
      null,
    add: (url: string, target_page?: string) => addMut.mutate({ url, target_page }),
    toggle: (id: number) => toggleMut.mutate(id),
    scan: (id: number) => scanMut.mutate(id),
    remove: (id: number) => delMut.mutate(id),
  };
}
