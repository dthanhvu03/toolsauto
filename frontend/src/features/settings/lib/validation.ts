import type {
  SettingsFieldMeta,
  ValidationErrors,
  ValidationWarnings,
} from "../types/settings.types";
import { normalizeInbound } from "./normalize";
import { groupFieldsByGroupId } from "./fieldGroups";

export function validateField(
  meta: SettingsFieldMeta,
  value: unknown,
  _draft: Record<string, unknown>
): string | undefined {
  if (meta.envLocked) return undefined;
  if (meta.type === "boolean") return undefined;
  const rules = meta.validationRules;
  const req = rules?.required ?? meta.required;
  if (req && (value === "" || value === undefined || value === null)) {
    return "Required";
  }
  if ((meta.type === "string" || meta.type === "url") && rules?.pattern && value) {
    try {
      if (!new RegExp(rules.pattern).test(String(value))) return "Invalid format";
    } catch {
      /* ignore bad pattern */
    }
  }
  if (meta.type === "url" && value) {
    try {
      const u = new URL(String(value));
      if (!["http:", "https:"].includes(u.protocol)) return "URL must be http(s)";
    } catch {
      return "Invalid URL";
    }
  }
  if (
    meta.type === "integer" ||
    meta.type === "float" ||
    meta.type === "duration_s" ||
    meta.type === "duration_ms" ||
    meta.type === "minutes"
  ) {
    const n = normalizeInbound(meta, value) as number;
    if (!Number.isFinite(n)) return "Must be a number";
    if (rules?.min !== undefined && n < rules.min) return `Must be ≥ ${rules.min}`;
    if (rules?.max !== undefined && n > rules.max) return `Must be ≤ ${rules.max}`;
  }
  return undefined;
}

export function warnField(meta: SettingsFieldMeta, value: unknown): string | undefined {
  if (meta.envLocked) return undefined;
  const rules = meta.validationRules;
  if (!rules?.warnAbove && !rules?.warnBelow) return undefined;
  if (
    meta.type === "integer" ||
    meta.type === "float" ||
    meta.type === "duration_s" ||
    meta.type === "duration_ms" ||
    meta.type === "minutes"
  ) {
    const n = normalizeInbound(meta, value) as number;
    if (!Number.isFinite(n)) return undefined;
    if (rules.warnAbove !== undefined && n > rules.warnAbove) {
      return `Unusually high (>${rules.warnAbove}) — confirm before save`;
    }
    if (rules.warnBelow !== undefined && n < rules.warnBelow) {
      return `Unusually low (<${rules.warnBelow})`;
    }
  }
  return undefined;
}

export function validateGroup(
  _groupId: string,
  metas: SettingsFieldMeta[],
  draft: Record<string, unknown>
): string | undefined {
  const minM = metas.find((m) => m.pairedRole === "min");
  const maxM = metas.find((m) => m.pairedRole === "max");
  if (!minM || !maxM) return undefined;
  const minV = normalizeInbound(minM, draft[minM.key]) as number;
  const maxV = normalizeInbound(maxM, draft[maxM.key]) as number;
  if (!Number.isFinite(minV) || !Number.isFinite(maxV)) return undefined;
  if (maxV < minV) return "Max must be greater than or equal to min";
  return undefined;
}

export function runGroupValidators(
  schema: SettingsFieldMeta[],
  draft: Record<string, unknown>
): Record<string, string | undefined> {
  const byGroup = groupFieldsByGroupId(schema);
  const out: Record<string, string | undefined> = {};
  for (const [gid, metas] of byGroup) {
    out[gid] = validateGroup(gid, metas, draft);
  }
  return out;
}

export function validateAllFields(
  schema: SettingsFieldMeta[],
  draft: Record<string, unknown>
): ValidationErrors {
  const byKey: Record<string, string | undefined> = {};
  for (const meta of schema) {
    if (meta.envLocked) continue;
    byKey[meta.key] = validateField(meta, draft[meta.key], draft);
  }
  return { byKey, byGroup: runGroupValidators(schema, draft) };
}

export function collectWarnings(
  schema: SettingsFieldMeta[],
  draft: Record<string, unknown>
): ValidationWarnings {
  const byKey: Record<string, string | undefined> = {};
  for (const meta of schema) {
    if (meta.envLocked) continue;
    byKey[meta.key] = warnField(meta, draft[meta.key]);
  }
  return { byKey };
}

export function hasBlockingErrors(errors: ValidationErrors): boolean {
  return (
    Object.values(errors.byKey).some(Boolean) || Object.values(errors.byGroup).some(Boolean)
  );
}

export function validateForSection(
  schema: SettingsFieldMeta[],
  draft: Record<string, unknown>,
  section: string
): ValidationErrors {
  return validateAllFields(
    schema.filter((f) => f.section === section),
    draft
  );
}
