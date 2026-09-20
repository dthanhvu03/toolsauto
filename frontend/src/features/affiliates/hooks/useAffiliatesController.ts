import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteAffiliate, fetchAffiliates, saveAffiliate } from "../api/affiliatesApi";
import type { AffiliateRow } from "../types/affiliates.types";

export function useAffiliatesController() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [qDraft, setQDraft] = useState("");
  const [msg, setMsg] = useState("");
  const [editing, setEditing] = useState<AffiliateRow | null>(null);

  const query = useQuery({
    queryKey: ["admin-affiliates", q, page],
    queryFn: () => fetchAffiliates({ q, page }),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-affiliates"] });
  const onOk = (r: { message: string }) => {
    setMsg(r.message);
    setEditing(null);
    invalidate();
  };

  const saveMut = useMutation({ mutationFn: saveAffiliate, onSuccess: onOk, onError: (e: Error) => setMsg(e.message) });
  const delMut = useMutation({
    mutationFn: deleteAffiliate,
    onSuccess: onOk,
    onError: (e: Error) => setMsg(e.message),
  });

  return {
    qDraft,
    page,
    totalPages: query.data?.total_pages ?? 1,
    links: query.data?.links ?? [],
    query,
    msg,
    editing,
    saving: saveMut.isPending,
    setQDraft,
    setPage,
    setEditing,
    applySearch: () => {
      setPage(1);
      setQ(qDraft.trim());
    },
    save: (body: {
      id?: number;
      keyword: string;
      url: string;
      comment_template: string;
      commission_rate?: number | null;
    }) => saveMut.mutate(body),
    remove: (id: number) => delMut.mutate(id),
  };
}
