import type { SettingsFieldMeta } from "../../../types/settings.types";
import { resolveEnvLocked } from "../../../lib/fieldMeta";
import { NumberFieldRow } from "./NumberFieldRow";

function titleForGroup(metas: [SettingsFieldMeta, SettingsFieldMeta], groupId: string): string {
  return metas[0].groupLabel ?? metas[1].groupLabel ?? groupId.replace(/_/g, " ");
}

export function MinMaxGroupRow({
  groupId,
  metas,
  draft,
  sources,
  onChange,
  groupError,
  keyErrors,
}: {
  groupId: string;
  metas: [SettingsFieldMeta, SettingsFieldMeta];
  draft: Record<string, unknown>;
  sources: Record<string, string | undefined>;
  onChange: (key: string, v: number) => void;
  groupError?: string;
  keyErrors?: { min?: string; max?: string };
}) {
  const [minM, maxM] = metas;
  const lockMin = resolveEnvLocked(minM, sources);
  const lockMax = resolveEnvLocked(maxM, sources);

  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-slate-800">{titleForGroup(metas, groupId)}</p>
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <span className="mb-1 block text-[10px] font-medium uppercase text-slate-400">Min</span>
          <NumberFieldRow
            unit={minM.unit}
            disabled={lockMin}
            integer={minM.type !== "float"}
            value={(draft[minM.key] as number) ?? 0}
            onChange={(v) => onChange(minM.key, v)}
            min={minM.validationRules?.min}
            max={minM.validationRules?.max}
          />
          {keyErrors?.min ? <p className="mt-1 text-xs text-red-600">{keyErrors.min}</p> : null}
        </div>
        <div>
          <span className="mb-1 block text-[10px] font-medium uppercase text-slate-400">Max</span>
          <NumberFieldRow
            unit={maxM.unit}
            disabled={lockMax}
            integer={maxM.type !== "float"}
            value={(draft[maxM.key] as number) ?? 0}
            onChange={(v) => onChange(maxM.key, v)}
            min={maxM.validationRules?.min}
            max={maxM.validationRules?.max}
          />
          {keyErrors?.max ? <p className="mt-1 text-xs text-red-600">{keyErrors.max}</p> : null}
        </div>
      </div>
      {groupError ? <p className="mt-2 text-xs font-medium text-red-600">{groupError}</p> : null}
    </div>
  );
}
