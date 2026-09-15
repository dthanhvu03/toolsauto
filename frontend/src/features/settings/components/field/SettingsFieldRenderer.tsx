import type {
  FieldValueSource,
  SettingsAccess,
  SettingsFieldMeta,
  ValidationErrors,
  ValidationWarnings,
} from "../../types/settings.types";
import { isNumericFieldType, resolveEnvLocked } from "../../lib/fieldMeta";
import { FieldError } from "./FieldError";
import { FieldHelper } from "./FieldHelper";
import { FieldLabel } from "./FieldLabel";
import { FieldWarning } from "./FieldWarning";
import { SettingsBadgeGroup } from "./SettingsBadgeGroup";
import { SettingsEnvOverrideBanner } from "./SettingsEnvOverrideBanner";
import { SettingsFieldMetaLine } from "./SettingsFieldMetaLine";
import { NumberFieldRow } from "./rows/NumberFieldRow";
import { SecretFieldRow } from "./rows/SecretFieldRow";
import { TextFieldRow } from "./rows/TextFieldRow";
import { ToggleFieldRow } from "./rows/ToggleFieldRow";
import { UrlFieldRow } from "./rows/UrlFieldRow";

/** Metadata-only renderer — no key-specific branches. */
export function SettingsFieldRenderer({
  meta,
  draft,
  sources,
  secretsInfo,
  secretOverrides,
  errors,
  warnings,
  onFieldChange,
  onSecretChange,
  access,
}: {
  meta: SettingsFieldMeta;
  draft: Record<string, unknown>;
  sources: Record<string, string | undefined>;
  secretsInfo: Record<string, { hasValue: boolean }>;
  secretOverrides: Record<string, string>;
  errors: ValidationErrors;
  warnings: ValidationWarnings;
  onFieldChange: (key: string, v: unknown) => void;
  onSecretChange: (key: string, v: string | undefined) => void;
  access?: SettingsAccess;
}) {
  const src = sources[meta.key] as FieldValueSource | undefined;
  const envLocked = resolveEnvLocked(meta, sources);
  const rbacLocked = access ? !access.canEditKey(meta.key, meta) : false;
  const locked = envLocked || rbacLocked;
  const val = draft[meta.key];

  return (
    <div className="rounded-xl border border-slate-100 bg-white/80 p-4 shadow-sm">
      <FieldLabel right={<SettingsBadgeGroup restartRequired={meta.restartRequired} source={src} />}>
        {meta.label}
      </FieldLabel>
      <FieldHelper text={meta.description} />
      <SettingsFieldMetaLine metaKey={meta.key} />
      {envLocked ? <SettingsEnvOverrideBanner /> : null}
      {rbacLocked && !envLocked ? (
        <p className="mb-2 text-xs text-amber-800">You don&apos;t have permission to edit this field.</p>
      ) : null}

      <div className="mt-3">
        {meta.secret === true ? (
          <SecretFieldRow
            disabled={locked}
            hasValue={Boolean(secretsInfo[meta.key]?.hasValue)}
            pendingValue={secretOverrides[meta.key]}
            onChange={(v) => onSecretChange(meta.key, v)}
          />
        ) : meta.type === "boolean" ? (
          <ToggleFieldRow
            disabled={locked}
            checked={Boolean(val)}
            onChange={(v) => onFieldChange(meta.key, v)}
          />
        ) : meta.type === "string" ? (
          <TextFieldRow
            disabled={locked}
            placeholder={meta.placeholder}
            value={String(val ?? "")}
            onChange={(v) => onFieldChange(meta.key, v)}
          />
        ) : meta.type === "url" ? (
          <UrlFieldRow
            disabled={locked}
            value={String(val ?? "")}
            onChange={(v) => onFieldChange(meta.key, v)}
          />
        ) : isNumericFieldType(meta) ? (
          <NumberFieldRow
            disabled={locked}
            unit={meta.unit}
            integer={meta.type !== "float"}
            min={meta.validationRules?.min}
            max={meta.validationRules?.max}
            value={typeof val === "number" ? val : Number(val)}
            onChange={(v) => onFieldChange(meta.key, v)}
          />
        ) : null}
      </div>
      <FieldError message={errors.byKey[meta.key]} />
      <FieldWarning message={warnings.byKey[meta.key]} />
    </div>
  );
}
