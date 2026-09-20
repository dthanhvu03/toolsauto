import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchAiStudio, saveAiStudio } from "../api/aiStudioApi";
import type { StudioItem } from "../types/aiStudio.types";

export function useAiStudioController() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["admin-ai-studio"], queryFn: fetchAiStudio });
  const [selected, setSelected] = useState<StudioItem | null>(null);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState("");

  const saveMut = useMutation({
    mutationFn: () => saveAiStudio(selected?.key || "", draft),
    onSuccess: (r) => {
      setMsg(r.message);
      qc.invalidateQueries({ queryKey: ["admin-ai-studio"] });
    },
    onError: (e: Error) => setMsg(e.message),
  });

  const pick = (item: StudioItem) => {
    setSelected(item);
    setDraft(item.value || item.preview || "");
  };

  return {
    query,
    data: query.data,
    selected,
    draft,
    setDraft,
    msg,
    saving: saveMut.isPending,
    pick,
    save: () => {
      if (selected) saveMut.mutate();
    },
  };
}
