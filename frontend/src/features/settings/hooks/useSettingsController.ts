import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  SectionId,
  SettingsAccess,
  SettingsFieldMeta,
  SettingsValuesResponse,
  UserRole,
  ValidationErrors,
  ValidationWarnings,
} from "../types/settings.types";
import { createDefaultSettingsAccess, sectionOrderFromSchema } from "../types/settings.types";
import { getSettingsSchema, getSettingsValues, patchSettingsSection } from "../api/settingsApi";
import { normalizeForCompare, normalizeOutbound } from "../lib/normalize";
import {
  collectWarnings,
  hasBlockingErrors,
  validateAllFields,
  validateForSection,
} from "../lib/validation";

export function useSettingsController(options?: { role?: UserRole }) {
  const role = options?.role ?? "admin";
  const access: SettingsAccess = useMemo(() => createDefaultSettingsAccess(role), [role]);

  const [schema, setSchema] = useState<SettingsFieldMeta[]>([]);
  const [snapshot, setSnapshot] = useState<Record<string, unknown>>({});
  const [sources, setSources] = useState<Record<string, string>>({});
  const [secretsInfo, setSecretsInfo] = useState<Record<string, { hasValue: boolean }>>({});
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [secretOverrides, setSecretOverrides] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [savingBySection, setSavingBySection] = useState<
    Record<string, "idle" | "saving" | "error">
  >({});
  const [toast, setToast] = useState<string | null>(null);

  const applyValues = useCallback((val: SettingsValuesResponse) => {
    setSnapshot({ ...val.values });
    setDraft({ ...val.values });
    setSources(val.sources ?? {});
    setSecretsInfo(val.secrets ?? {});
    setSecretOverrides({});
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [sch, val] = await Promise.all([getSettingsSchema(), getSettingsValues()]);
      setSchema(sch.fields);
      applyValues(val);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [applyValues]);

  useEffect(() => {
    reload();
  }, [reload]);

  const sectionOrder = useMemo(() => sectionOrderFromSchema(schema), [schema]);

  const validationErrors: ValidationErrors = useMemo(
    () => validateAllFields(schema, draft),
    [schema, draft]
  );

  const validationWarnings: ValidationWarnings = useMemo(
    () => collectWarnings(schema, draft),
    [schema, draft]
  );

  const blockingBySection = useMemo(() => {
    const m: Record<string, boolean> = {};
    for (const sid of sectionOrder) {
      m[sid] = hasBlockingErrors(validateForSection(schema, draft, sid));
    }
    return m;
  }, [schema, draft, sectionOrder]);

  const isDirty = useMemo(() => {
    for (const meta of schema) {
      if (meta.secret) {
        if (secretOverrides[meta.key] !== undefined) return true;
        continue;
      }
      if (
        JSON.stringify(normalizeForCompare(meta, draft[meta.key])) !==
        JSON.stringify(normalizeForCompare(meta, snapshot[meta.key]))
      ) {
        return true;
      }
    }
    return false;
  }, [schema, draft, snapshot, secretOverrides]);

  const dirtySections = useMemo(() => {
    const s = new Set<SectionId>();
    for (const meta of schema) {
      if (meta.secret) {
        if (secretOverrides[meta.key] !== undefined) s.add(meta.section);
        continue;
      }
      if (
        JSON.stringify(normalizeForCompare(meta, draft[meta.key])) !==
        JSON.stringify(normalizeForCompare(meta, snapshot[meta.key]))
      ) {
        s.add(meta.section);
      }
    }
    return s;
  }, [schema, draft, snapshot, secretOverrides]);

  const setField = useCallback((key: string, value: unknown) => {
    setDraft((d) => ({ ...d, [key]: value }));
  }, []);

  const setSecretField = useCallback((key: string, value: string | undefined) => {
    setSecretOverrides((prev) => {
      const next = { ...prev };
      if (value === undefined) delete next[key];
      else next[key] = value;
      return next;
    });
  }, []);

  const resetSection = useCallback(
    (section: SectionId) => {
      setDraft((d) => {
        const n = { ...d };
        for (const meta of schema) {
          if (meta.section === section) n[meta.key] = snapshot[meta.key];
        }
        return n;
      });
      setSecretOverrides((prev) => {
        const next = { ...prev };
        for (const meta of schema) {
          if (meta.section === section && meta.secret) delete next[meta.key];
        }
        return next;
      });
    },
    [schema, snapshot]
  );

  const discardAll = useCallback(() => {
    setDraft({ ...snapshot });
    setSecretOverrides({});
  }, [snapshot]);

  const buildSectionPayload = useCallback(
    (section: SectionId): Record<string, unknown> => {
      const payload: Record<string, unknown> = {};
      for (const meta of schema) {
        if (meta.section !== section || meta.envLocked) continue;
        if (!access.canEditKey(meta.key, meta)) continue;
        if (meta.secret) {
          if (secretOverrides[meta.key] !== undefined) {
            payload[meta.key] = secretOverrides[meta.key];
          }
          continue;
        }
        const o = normalizeOutbound(meta, draft[meta.key], snapshot);
        if (o !== undefined) payload[meta.key] = o;
      }
      return payload;
    },
    [schema, draft, snapshot, secretOverrides, access]
  );

  const saveSection = useCallback(
    async (section: SectionId) => {
      if (hasBlockingErrors(validateForSection(schema, draft, section))) {
        setToast("Fix validation errors in this section");
        return;
      }
      const payload = buildSectionPayload(section);
      if (Object.keys(payload).length === 0) {
        setToast("No changes in this section");
        return;
      }
      setSavingBySection((m) => ({ ...m, [section]: "saving" }));
      try {
        const res = await patchSettingsSection(section, payload);
        setToast(`Saved (${res.updated.length} keys)`);
        setSnapshot((prev) => {
          const n = { ...prev };
          for (const k of res.updated) n[k] = res.values?.[k] ?? draft[k];
          return n;
        });
        setDraft((d) => {
          const n = { ...d };
          for (const k of res.updated) n[k] = res.values?.[k] ?? d[k];
          return n;
        });
        setSecretOverrides((so) => {
          const next = { ...so };
          for (const k of res.updated) {
            if (schema.find((x) => x.key === k)?.secret) delete next[k];
          }
          return next;
        });
        setSavingBySection((m) => ({ ...m, [section]: "idle" }));
      } catch {
        setSavingBySection((m) => ({ ...m, [section]: "error" }));
        setToast("Save failed");
      }
    },
    [buildSectionPayload, draft, schema]
  );

  return {
    schema,
    sectionOrder,
    snapshot,
    sources,
    secretsInfo,
    draft,
    secretOverrides,
    loading,
    loadError,
    validationErrors,
    validationWarnings,
    blockingBySection,
    savingBySection,
    toast,
    setToast,
    isDirty,
    dirtySections,
    blockingGlobal: hasBlockingErrors(validationErrors),
    access,
    reload,
    setField,
    setSecretField,
    resetSection,
    discardAll,
    saveSection,
  };
}
