import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFbProTasks, resetFbProWeek, saveFbProTasks } from "../api/fbProTasksApi";

export function useFbProTasksController() {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [notes, setNotes] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  const query = useQuery({
    queryKey: ["admin-fb-pro-tasks", key],
    queryFn: () => fetchFbProTasks({ key }),
    placeholderData: keepPreviousData,
  });

  const dash = query.data;
  const selectedKey = key || dash?.scope_key || "";
  const notesValue = notes ?? dash?.notes ?? "";

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin-fb-pro-tasks"] });
  const saveMut = useMutation({
    mutationFn: () => saveFbProTasks({ scope_key: selectedKey, notes: notesValue }),
    onSuccess: (r) => {
      setMsg(r.message);
      invalidate();
    },
    onError: (e: Error) => setMsg(e.message),
  });
  const resetMut = useMutation({
    mutationFn: () => resetFbProWeek(selectedKey),
    onSuccess: (r) => {
      setMsg(r.message);
      invalidate();
    },
    onError: (e: Error) => setMsg(e.message),
  });

  return {
    selectedKey,
    dash,
    query,
    notes: notesValue,
    setNotes,
    msg,
    setKey,
    save: () => saveMut.mutate(),
    resetWeek: () => {
      if (window.confirm("Reset số tuần này?")) resetMut.mutate();
    },
    saving: saveMut.isPending || resetMut.isPending,
  };
}
