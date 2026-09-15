import type { FieldValueSource, SettingsFieldMeta } from "../types/settings.types";

export function isNumericFieldType(meta: SettingsFieldMeta): boolean {
  return (
    meta.type === "integer" ||
    meta.type === "float" ||
    meta.type === "duration_s" ||
    meta.type === "duration_ms" ||
    meta.type === "minutes"
  );
}

export function resolveEnvLocked(
  meta: SettingsFieldMeta,
  sources: Record<string, string | undefined>
): boolean {
  if (meta.envLocked) return true;
  return (sources[meta.key] as FieldValueSource | undefined) === "environment";
}
