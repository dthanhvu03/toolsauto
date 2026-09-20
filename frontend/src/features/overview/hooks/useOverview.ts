import { useQuery } from "@tanstack/react-query";
import { fetchOverview } from "../api/overviewApi";

export function useOverview() {
  return useQuery({ queryKey: ["admin-overview"], queryFn: fetchOverview });
}
