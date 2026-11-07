import { useQuery } from "@tanstack/react-query";
import { fetchProcesses, fetchWindowsHost } from "../api/syspanelApi";

/** Cùng queryKey ở mọi nơi trên trang → React Query chỉ hỏi server 1 lần cho ô tóm tắt + bảng. */
export const PROCESSES_KEY = ["admin-processes"] as const;
export const WINDOWS_KEY = ["admin-windows-host"] as const;

export function useProcesses(fast = false) {
  return useQuery({ queryKey: PROCESSES_KEY, queryFn: fetchProcesses, refetchInterval: fast ? 2_000 : 5_000 });
}

/** Server đọc powershell (~2,5 giây) và giữ 8 giây → hỏi lại 10 giây. */
export function useWindowsHost() {
  return useQuery({ queryKey: WINDOWS_KEY, queryFn: fetchWindowsHost, refetchInterval: 10_000 });
}
