import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSyspanel, syspanelCancelStuck, syspanelRetryFailed, syspanelWorker } from "../api/syspanelApi";

export function useSyspanelController() {
  const qc = useQueryClient();
  const [msg, setMsg] = useState("");
  const query = useQuery({
    queryKey: ["admin-syspanel"],
    queryFn: fetchSyspanel,
    refetchInterval: 15_000,
  });
  const onOk = (r: { message: string }) => {
    setMsg(r.message);
    qc.invalidateQueries({ queryKey: ["admin-syspanel"] });
  };
  const onErr = (e: Error) => setMsg(e.message);
  const retryMut = useMutation({ mutationFn: syspanelRetryFailed, onSuccess: onOk, onError: onErr });
  const stuckMut = useMutation({ mutationFn: syspanelCancelStuck, onSuccess: onOk, onError: onErr });
  const workerMut = useMutation({ mutationFn: syspanelWorker, onSuccess: onOk, onError: onErr });

  return {
    query,
    data: query.data,
    msg,
    busy: retryMut.isPending || stuckMut.isPending || workerMut.isPending,
    retryFailed: () => retryMut.mutate(),
    cancelStuck: () => stuckMut.mutate(),
    worker: (a: "pause" | "resume" | "safe-mode") => workerMut.mutate(a),
  };
}
