import type { SettingsFieldMeta } from "../types/settings.types";

export function groupFieldsByGroupId(
  fields: SettingsFieldMeta[]
): Map<string, SettingsFieldMeta[]> {
  const m = new Map<string, SettingsFieldMeta[]>();
  for (const f of fields) {
    if (!f.groupId) continue;
    const arr = m.get(f.groupId) ?? [];
    arr.push(f);
    m.set(f.groupId, arr);
  }
  return m;
}

export type RenderItem =
  | { kind: "single"; meta: SettingsFieldMeta }
  | { kind: "group"; groupId: string; metas: [SettingsFieldMeta, SettingsFieldMeta] };

export function flattenRenderableFields(fields: SettingsFieldMeta[]): RenderItem[] {
  const emittedGroups = new Set<string>();
  const out: RenderItem[] = [];

  for (const f of fields) {
    if (f.groupId && emittedGroups.has(f.groupId)) continue;
    if (f.groupId) {
      const peers = fields.filter((x) => x.groupId === f.groupId);
      if (peers.length === 2) {
        const min = peers.find((p) => p.pairedRole === "min");
        const max = peers.find((p) => p.pairedRole === "max");
        if (min && max) {
          emittedGroups.add(f.groupId);
          out.push({ kind: "group", groupId: f.groupId, metas: [min, max] });
          continue;
        }
      }
    }
    out.push({ kind: "single", meta: f });
  }
  return out;
}

export function fieldsInSection(schema: SettingsFieldMeta[], section: string): SettingsFieldMeta[] {
  return schema.filter((f) => f.section === section);
}
