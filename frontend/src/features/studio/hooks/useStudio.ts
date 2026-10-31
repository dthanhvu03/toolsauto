import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import * as api from "../api/studioApi";

export function useProjects() {
  return useQuery({
    queryKey: ["studio-projects"],
    queryFn: () => api.fetchProjects(),
    // Có việc đang chạy thì hỏi lại mỗi 8 giây để thẻ tự chuyển cột.
    refetchInterval: (q) => ((q.state.data?.tasks_pending ?? 0) > 0 ? 8_000 : 60_000),
  });
}

export function useSetup() {
  return useQuery({ queryKey: ["studio-setup"], queryFn: api.fetchSetup, staleTime: 60_000 });
}

/** Tiến trình (PLAN-114). Còn việc chạy thì hỏi lại mỗi 3 giây; không thì 30 giây (bảng) / thôi (lô đã xong). */
export function useJobs(ids?: number[]) {
  const watching = ids !== undefined;
  return useQuery({
    queryKey: ["studio-jobs", ids ?? "all"],
    queryFn: () => api.fetchJobs(ids ?? []),
    enabled: !watching || ids.length > 0,
    refetchInterval: (q) => ((q.state.data?.active ?? 0) > 0 ? 3_000 : watching ? false : 30_000),
  });
}

export function useVoices() {
  return useQuery({ queryKey: ["studio-voices"], queryFn: api.fetchVoices, staleTime: 5 * 60_000 });
}

export function useAssets(kind = "") {
  return useQuery({ queryKey: ["studio-assets", kind], queryFn: () => api.fetchAssets(kind) });
}

/**
 * Mutation + một câu thông báo + làm mới các danh sách liên quan. ``done`` có thể là hàm để ghi kết quả
 * (vd số biến thể). ``seq`` tăng mỗi lần báo — đưa vào ``<Toast>`` để bấm lại vẫn hiện.
 */
export function useAction<A, R = unknown>(
  fn: (arg: A) => Promise<R>,
  done: string | ((r: R) => string),
  keys: string[][] = [["studio-projects"]]
) {
  const qc = useQueryClient();
  const [msg, setMsgText] = useState("");
  const [seq, setSeq] = useState(0);
  const setMsg = (text: string) => {
    setMsgText(text);
    setSeq((n) => n + 1);
  };
  const m = useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      setMsg(typeof done === "function" ? done(r) : done);
      keys.forEach((k) => qc.invalidateQueries({ queryKey: k }));
    },
    onError: (e: Error) => setMsg(`Lỗi: ${e.message}`),
  });
  return { run: m.mutate, busy: m.isPending, msg, seq, setMsg };
}
