import { useQuery } from "@tanstack/react-query";
import { fetchPlatforms, fetchWorkflows } from "../api/platformConfigApi";

export function usePlatformConfigController() {
  const platforms = useQuery({ queryKey: ["platform-configs"], queryFn: fetchPlatforms });
  const workflows = useQuery({ queryKey: ["platform-workflows"], queryFn: fetchWorkflows });
  return { platforms, workflows };
}
