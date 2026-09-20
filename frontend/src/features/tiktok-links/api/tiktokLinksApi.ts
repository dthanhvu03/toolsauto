import { getJson } from "@/shared/api/http";
import type { TiktokLinksResponse } from "../types/tiktokLinks.types";

export function fetchTiktokLinks(params: { q?: string }) {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  return getJson<TiktokLinksResponse>(`/api/admin/tiktok-links?${sp}`);
}
