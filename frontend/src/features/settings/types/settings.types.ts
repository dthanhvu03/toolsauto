/** Section ids come from API (`section` slug). Labels from `sectionLabel`. */
export type SectionId = string;

export type FieldValueSource = "default" | "database" | "environment";

export type SettingsFieldType =
  | "string"
  | "integer"
  | "float"
  | "boolean"
  | "url"
  | "secret"
  | "duration_s"
  | "duration_ms"
  | "minutes";

export type DangerLevel = "low" | "medium" | "high";

export interface ValidationRules {
  min?: number;
  max?: number;
  warnAbove?: number;
  warnBelow?: number;
  pattern?: string;
  required?: boolean;
}

export interface TestActionMeta {
  id: string;
  label: string;
  dependsOnKeys: string[];
}

export interface SettingsFieldMeta {
  key: string;
  label: string;
  description?: string;
  section: SectionId;
  /** Human section title from backend (Vietnamese OK) */
  sectionLabel?: string;
  subsection?: string | null;
  type: SettingsFieldType;
  unit?: string | null;
  placeholder?: string;
  defaultValue: unknown;
  required?: boolean;
  secret?: boolean;
  envLocked?: boolean;
  restartRequired?: boolean;
  validationRules?: ValidationRules;
  testAction?: TestActionMeta | null;
  dangerLevel?: DangerLevel;
  groupId?: string;
  pairedRole?: "min" | "max";
  groupLabel?: string;
}

export interface SettingsSchemaResponse {
  fields: SettingsFieldMeta[];
}

export interface SecretKeyInfo {
  hasValue: boolean;
}

export interface SettingsValuesResponse {
  values: Record<string, unknown>;
  sources?: Record<string, FieldValueSource>;
  secrets?: Record<string, SecretKeyInfo>;
}

export interface ValidationErrors {
  byKey: Record<string, string | undefined>;
  byGroup: Record<string, string | undefined>;
}

export interface ValidationWarnings {
  byKey: Record<string, string | undefined>;
}

export interface TestConnectionState {
  status: "idle" | "loading" | "success" | "error";
  message?: string;
  latencyMs?: number;
}

export type SavingState = "idle" | "saving" | "success" | "error";

export type UserRole = "operator" | "admin" | "readonly";

export interface SettingsAccess {
  role: UserRole;
  canEditKey: (key: string, meta: SettingsFieldMeta) => boolean;
  canEditSection: (section: SectionId) => boolean;
}

export interface SettingsState {
  schema: SettingsFieldMeta[];
  snapshot: Record<string, unknown>;
  draft: Record<string, unknown>;
  sources: Record<string, FieldValueSource>;
  secretsInfo: Record<string, SecretKeyInfo>;
  secretOverrides: Record<string, string>;
  validationErrors: ValidationErrors;
  validationWarnings: ValidationWarnings;
  savingBySection: Record<SectionId, SavingState>;
  testById: Record<string, TestConnectionState>;
  loaded: boolean;
  loadError: string | null;
}

export function createDefaultSettingsAccess(role: UserRole): SettingsAccess {
  return {
    role,
    canEditSection: () => role !== "readonly",
    canEditKey: (_key, meta) => {
      if (role === "readonly") return false;
      if (role === "operator" && meta.secret) return false;
      return true;
    },
  };
}

/** Ordered unique section ids from schema (first-seen order). */
export function sectionOrderFromSchema(fields: SettingsFieldMeta[]): SectionId[] {
  const seen = new Set<string>();
  const out: SectionId[] = [];
  for (const f of fields) {
    if (seen.has(f.section)) continue;
    seen.add(f.section);
    out.push(f.section);
  }
  return out;
}

export function sectionLabelFromSchema(
  fields: SettingsFieldMeta[],
  section: SectionId
): string {
  const hit = fields.find((f) => f.section === section);
  return hit?.sectionLabel || section;
}
