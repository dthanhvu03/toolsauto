import { getJson, sendJson, type OkMessage } from "@/shared/api/http";
import type { AiStudioResponse } from "../types/aiStudio.types";

export function fetchAiStudio() {
  return getJson<AiStudioResponse>("/api/admin/ai-studio");
}

export function saveAiStudio(key: string, value: string) {
  return sendJson<OkMessage>("/api/admin/ai-studio/save", "POST", { key, value });
}
