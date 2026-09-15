import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { testSettingsConnection } from "../api/settingsApi";
import { SettingsFieldRenderer } from "../components/field/SettingsFieldRenderer";
import { SettingsTestConnectionRow } from "../components/field/SettingsTestConnectionRow";
import { MinMaxGroupRow } from "../components/field/rows/MinMaxGroupRow";
import { SettingsPageHeader } from "../components/layout/SettingsPageHeader";
import { SettingsSectionCard } from "../components/layout/SettingsSectionCard";
import { SettingsSectionNav } from "../components/layout/SettingsSectionNav";
import { SettingsUnsavedBar } from "../components/layout/SettingsUnsavedBar";
import { useSettingsController } from "../hooks/useSettingsController";
import { fieldsInSection, flattenRenderableFields } from "../lib/fieldGroups";
import type { RenderItem } from "../lib/fieldGroups";
import type { SectionId, TestConnectionState } from "../types/settings.types";
import { sectionLabelFromSchema } from "../types/settings.types";

export function SettingsPage() {
  const ctl = useSettingsController({ role: "admin" });
  const [activeSection, setActiveSection] = useState<SectionId | undefined>();
  const [testById, setTestById] = useState<Record<string, TestConnectionState>>({});

  useEffect(() => {
    if (!ctl.toast) return;
    const t = setTimeout(() => ctl.setToast(null), 4000);
    return () => clearTimeout(t);
  }, [ctl.toast, ctl.setToast]);

  const sectionLabels = useMemo(() => {
    const m: Record<string, string> = {};
    for (const sid of ctl.sectionOrder) {
      m[sid] = sectionLabelFromSchema(ctl.schema, sid);
    }
    return m;
  }, [ctl.schema, ctl.sectionOrder]);

  const sectionCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of ctl.sectionOrder) c[s] = fieldsInSection(ctl.schema, s).length;
    return c;
  }, [ctl.schema, ctl.sectionOrder]);

  const scrollTo = useCallback((id: SectionId) => {
    setActiveSection(id);
    document.getElementById(`section-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const runTest = useCallback(async (testId: string) => {
    setTestById((m) => ({ ...m, [testId]: { status: "loading" } }));
    try {
      const r = await testSettingsConnection(testId, {
        overrides: {
          TIKWM_API_BASE: ctl.draft.TIKWM_API_BASE,
          TIKWM_API_TIMEOUT_SEC: ctl.draft.TIKWM_API_TIMEOUT_SEC,
        },
      });
      setTestById((m) => ({
        ...m,
        [testId]: {
          status: r.ok ? "success" : "error",
          latencyMs: r.latencyMs,
          message: r.message,
        },
      }));
    } catch (e) {
      setTestById((m) => ({
        ...m,
        [testId]: { status: "error", message: e instanceof Error ? e.message : "Error" },
      }));
    }
  }, [ctl.draft]);

  const renderSectionFields = (sectionId: SectionId) => {
    const fields = fieldsInSection(ctl.schema, sectionId);
    const items = flattenRenderableFields(fields);
    let lastSub: string | null | undefined;
    const nodes: ReactNode[] = [];

    const pushSubheading = (sub: string | null | undefined) => {
      if ((sub ?? "") === (lastSub ?? "")) return;
      lastSub = sub;
      if (sub) {
        nodes.push(
          <div key={`sub-${sub}-${nodes.length}`}>
            <h3 className="font-display mt-2 text-sm font-semibold capitalize text-slate-700">
              {sub}
            </h3>
          </div>
        );
      }
    };

    const renderItem = (item: RenderItem) => {
      if (item.kind === "group") {
        pushSubheading(item.metas[0].subsection);
        nodes.push(
          <div
            key={item.groupId}
            className="rounded-xl border border-slate-100 bg-white/80 p-4 shadow-sm"
          >
            <MinMaxGroupRow
              groupId={item.groupId}
              metas={item.metas}
              draft={ctl.draft}
              sources={ctl.sources}
              groupError={ctl.validationErrors.byGroup[item.groupId]}
              keyErrors={{
                min: ctl.validationErrors.byKey[item.metas[0].key],
                max: ctl.validationErrors.byKey[item.metas[1].key],
              }}
              onChange={(k, v) => ctl.setField(k, v)}
            />
          </div>
        );
        return;
      }
      pushSubheading(item.meta.subsection);
      nodes.push(
        <SettingsFieldRenderer
          key={item.meta.key}
          meta={item.meta}
          draft={ctl.draft}
          sources={ctl.sources}
          secretsInfo={ctl.secretsInfo}
          secretOverrides={ctl.secretOverrides}
          errors={ctl.validationErrors}
          warnings={ctl.validationWarnings}
          onFieldChange={ctl.setField}
          onSecretChange={ctl.setSecretField}
          access={ctl.access}
        />
      );
    };

    items.forEach(renderItem);

    const testIds = new Set<string>();
    for (const f of fields) {
      if (f.testAction?.id) testIds.add(f.testAction.id);
    }
    for (const tid of testIds) {
      const action = fields.find((f) => f.testAction?.id === tid)?.testAction;
      if (!action) continue;
      nodes.push(
        <SettingsTestConnectionRow
          key={`test-${tid}`}
          label={action.label}
          state={testById[tid] ?? { status: "idle" }}
          onTest={() => runTest(tid)}
        />
      );
    }

    return <div className="flex flex-col gap-4">{nodes}</div>;
  };

  if (ctl.loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        Loading settings…
      </div>
    );
  }
  if (ctl.loadError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2 text-red-600">
        <p>{ctl.loadError}</p>
        <p className="max-w-md text-center text-xs text-slate-500">
          Start FastAPI on :8000 (Vite proxies /api). Or set VITE_SETTINGS_USE_MOCK=true for
          offline mock.
        </p>
        <button
          type="button"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-white"
          onClick={ctl.reload}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-24">
      <SettingsPageHeader envLabel="local" />
      {ctl.toast ? (
        <div className="fixed right-4 top-20 z-40 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm shadow-lg">
          {ctl.toast}
        </div>
      ) : null}

      <div className="mx-auto flex max-w-6xl">
        <SettingsSectionNav
          sectionOrder={ctl.sectionOrder}
          labels={sectionLabels}
          counts={sectionCounts}
          activeSection={activeSection}
          onNavigate={scrollTo}
        />
        <main className="min-w-0 flex-1 space-y-6 px-4 py-6">
          {ctl.sectionOrder.map((sectionId) => {
            const saveDisabled =
              ctl.savingBySection[sectionId] === "saving" ||
              !ctl.dirtySections.has(sectionId) ||
              ctl.blockingBySection[sectionId];
            return (
              <SettingsSectionCard
                key={sectionId}
                sectionId={sectionId}
                title={sectionLabels[sectionId] ?? sectionId}
                modified={ctl.dirtySections.has(sectionId)}
                footer={
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => ctl.saveSection(sectionId)}
                      disabled={saveDisabled}
                      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40"
                    >
                      {ctl.savingBySection[sectionId] === "saving" ? "Saving…" : "Save section"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (
                          ctl.dirtySections.has(sectionId) &&
                          !window.confirm("Discard changes in this section?")
                        ) {
                          return;
                        }
                        ctl.resetSection(sectionId);
                      }}
                      className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Reset section
                    </button>
                  </div>
                }
              >
                {renderSectionFields(sectionId)}
              </SettingsSectionCard>
            );
          })}
        </main>
      </div>

      <SettingsUnsavedBar
        visible={ctl.isDirty}
        onDiscard={() => {
          if (!window.confirm("Discard all unsaved changes?")) return;
          ctl.discardAll();
        }}
      />
    </div>
  );
}
