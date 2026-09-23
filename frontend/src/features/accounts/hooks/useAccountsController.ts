import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  confirmAccountLogin,
  createAccount,
  deleteAccount,
  fetchAccounts,
  renameAccount,
  startAccountLogin,
  toggleAccount,
} from "../api/accountsApi";

export function useAccountsController() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [platform, setPlatform] = useState("");
  const [qDraft, setQDraft] = useState("");
  const [msg, setMsg] = useState("");

  const query = useQuery({
    queryKey: ["admin-accounts", q, platform],
    queryFn: () => fetchAccounts({ q, platform }),
    refetchInterval: (query) => {
      const rows = query.state.data?.accounts ?? [];
      return rows.some((a) => (a.login_status || "").toUpperCase() === "LOGGING_IN") ? 3000 : false;
    },
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-accounts"] });
  const onOk = (r: { message: string }) => {
    setMsg(r.message);
    invalidate();
  };
  const onErr = (e: Error) => setMsg(e.message);

  const createMut = useMutation({ mutationFn: createAccount, onSuccess: onOk, onError: onErr });
  const toggleMut = useMutation({ mutationFn: toggleAccount, onSuccess: onOk, onError: onErr });
  const renameMut = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => renameAccount(id, name),
    onSuccess: onOk,
    onError: onErr,
  });
  const deleteMut = useMutation({ mutationFn: deleteAccount, onSuccess: onOk, onError: onErr });
  const startLoginMut = useMutation({ mutationFn: startAccountLogin, onSuccess: onOk, onError: onErr });
  const confirmLoginMut = useMutation({
    mutationFn: confirmAccountLogin,
    onSuccess: onOk,
    onError: onErr,
  });

  const busyId =
    (toggleMut.variables as number | undefined) ??
    renameMut.variables?.id ??
    (deleteMut.variables as number | undefined) ??
    (startLoginMut.variables as number | undefined) ??
    (confirmLoginMut.variables as number | undefined) ??
    null;

  return {
    platform,
    qDraft,
    rows: query.data?.accounts ?? [],
    query,
    msg,
    creating: createMut.isPending,
    busyId,
    setPlatform,
    setQDraft,
    applySearch: () => setQ(qDraft.trim()),
    create: (name: string, plat: string) => createMut.mutate({ name, platform: plat }),
    toggle: (id: number) => toggleMut.mutate(id),
    rename: (id: number, name: string) => renameMut.mutate({ id, name }),
    remove: (id: number) => deleteMut.mutate(id),
    startLogin: (id: number) => startLoginMut.mutate(id),
    confirmLogin: (id: number) => confirmLoginMut.mutate(id),
  };
}
