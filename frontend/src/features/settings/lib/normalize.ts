import type { SettingsFieldMeta } from "../types/settings.types";

export function normalizeInbound(meta: SettingsFieldMeta, raw: unknown): unknown {
  if (meta.type === "boolean") return Boolean(raw);
  if (
    meta.type === "integer" ||
    meta.type === "duration_s" ||
    meta.type === "duration_ms" ||
    meta.type === "minutes"
  ) {
    const n = typeof raw === "number" ? raw : parseInt(String(raw), 10);
    return Number.isFinite(n) ? n : raw;
  }
  if (meta.type === "float") {
    const n = typeof raw === "number" ? raw : parseFloat(String(raw));
    return Number.isFinite(n) ? n : raw;
  }
  if (meta.type === "url" || meta.type === "string") {
    return typeof raw === "string" ? raw.trim() : String(raw ?? "").trim();
  }
  return raw;
}

/** undefined = omit from PATCH */
export function normalizeOutbound(
  meta: SettingsFieldMeta,
  value: unknown,
  snapshot: Record<string, unknown>
): unknown | undefined {
  if (meta.envLocked || meta.secret) return undefined;
  const a = normalizeForCompare(meta, value);
  const b = normalizeForCompare(meta, snapshot[meta.key]);
  if (JSON.stringify(a) === JSON.stringify(b)) return undefined;
  return a;
}

export function normalizeForCompare(meta: SettingsFieldMeta, value: unknown): unknown {
  const v = normalizeInbound(meta, value);
  if (meta.type === "url" || meta.type === "string") return String(v ?? "");
  return v;
}
