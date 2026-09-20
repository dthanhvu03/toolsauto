import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTiktokLinks } from "../api/tiktokLinksApi";

export function useTiktokLinksController() {
  const [q, setQ] = useState("");
  const [qDraft, setQDraft] = useState("");

  const query = useQuery({
    queryKey: ["admin-tiktok-links", q],
    queryFn: () => fetchTiktokLinks({ q }),
  });

  const applySearch = () => setQ(qDraft.trim());

  return {
    qDraft,
    items: query.data?.items ?? [],
    query,
    setQDraft,
    applySearch,
  };
}
