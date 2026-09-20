import { redirectToLoginIfUnauthorized } from "@/shared/api/http";
import type {
  SectionId,
  SettingsSchemaResponse,
  SettingsValuesResponse,
} from "../types/settings.types";
import { mockSchema } from "../mocks/mockSchema";
import { mockValues } from "../mocks/mockValues";

/**
 * true = local mock; false = call FastAPI via Vite proxy.
 * Override: VITE_SETTINGS_USE_MOCK=true|false
 */
const USE_MOCK =
  (import.meta.env.VITE_SETTINGS_USE_MOCK as string | undefined)?.toLowerCase() === "true"
    ? true
    : (import.meta.env.VITE_SETTINGS_USE_MOCK as string | undefined)?.toLowerCase() === "false"
      ? false
      : false; // default: real API when backend is running

export async function getSettingsSchema(): Promise<SettingsSchemaResponse> {
  if (USE_MOCK) {
    await delay(200);
    return { fields: mockSchema };
  }
  const r = await fetch("/api/settings/metadata", { credentials: "same-origin" });
  if (r.status === 401) {
    redirectToLoginIfUnauthorized(401);
    throw new Error("schema 401");
  }
  if (!r.ok) throw new Error(`schema ${r.status}`);
  return r.json() as Promise<SettingsSchemaResponse>;
}

export async function getSettingsValues(): Promise<SettingsValuesResponse> {
  if (USE_MOCK) {
    await delay(200);
    return structuredClone(mockValues);
  }
  const r = await fetch("/api/settings/values", { credentials: "same-origin" });
  if (r.status === 401) {
    redirectToLoginIfUnauthorized(401);
    throw new Error("values 401");
  }
  if (!r.ok) throw new Error(`values ${r.status}`);
  return r.json() as Promise<SettingsValuesResponse>;
}

export async function patchSettingsSection(
  section: SectionId,
  payload: Record<string, unknown>
): Promise<{ updated: string[]; values?: Record<string, unknown> }> {
  if (USE_MOCK) {
    await delay(400);
    return { updated: Object.keys(payload) };
  }
  const r = await fetch(`/api/settings/sections/${encodeURIComponent(section)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw Object.assign(new Error("save failed"), { status: r.status, body: err });
  }
  return r.json() as Promise<{ updated: string[]; values?: Record<string, unknown> }>;
}

export async function testSettingsConnection(
  testId: string,
  body?: { overrides?: Record<string, unknown> }
): Promise<{ ok: boolean; latencyMs?: number; message?: string }> {
  if (USE_MOCK) {
    await delay(800);
    return { ok: true, latencyMs: 42, message: "OK (mock)" };
  }
  const r = await fetch(`/api/settings/test/${encodeURIComponent(testId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body ?? {}),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, message: (j as { message?: string }).message ?? r.statusText };
  return j as { ok: boolean; latencyMs?: number; message?: string };
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
