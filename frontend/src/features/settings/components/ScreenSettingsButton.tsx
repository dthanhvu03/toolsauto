import { useQueryClient } from "@tanstack/react-query";
import { Settings, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/shared/lib/cn";
import { testSettingsConnection } from "../api/settingsApi";
import { useSettingsController } from "../hooks/useSettingsController";
import { flattenRenderableFields } from "../lib/fieldGroups";
import { SCREEN_SETTINGS, groupScreenFields, type ScreenId } from "../lib/screenSettings";
import { hasBlockingErrors, validateForSection } from "../lib/validation";
import type { SettingsFieldMeta, TestConnectionState } from "../types/settings.types";
import { SettingsFieldRenderer } from "./field/SettingsFieldRenderer";
import { SettingsTestConnectionRow } from "./field/SettingsTestConnectionRow";
import { MinMaxGroupRow } from "./field/rows/MinMaxGroupRow";

/** Ô chữ dài (từ khóa, câu mẫu…) chiếm cả hàng; số / bật-tắt xếp 2 cột. */
const isWide = (m: SettingsFieldMeta) => m.type === "string" || m.type === "url" || m.secret === true;

/**
 * Nút ⚙️ đặt ở đầu màn hình → modal chỉ chứa cài đặt của màn hình đó (khai báo trong `SCREEN_SETTINGS`).
 * Lưu xong làm mới mọi dữ liệu trên trang để màn hình hiện giá trị mới ngay.
 */
export function ScreenSettingsButton({ screen, className }: { screen: ScreenId; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        title={SCREEN_SETTINGS[screen].title}
        aria-label={SCREEN_SETTINGS[screen].title}
        onClick={() => setOpen(true)}
        className={cn(
          "inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50 hover:text-slate-900",
          className
        )}
      >
        <Settings className="size-4" />
      </button>
      {open ? <ScreenSettingsModal screen={screen} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function ScreenSettingsModal({ screen, onClose }: { screen: ScreenId; onClose: () => void }) {
  const cfg = SCREEN_SETTINGS[screen];
  const ctl = useSettingsController({ role: "admin" });
  const qc = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [testById, setTestById] = useState<Record<string, TestConnectionState>>({});

  const groups = useMemo(() => groupScreenFields(ctl.schema, cfg), [ctl.schema, cfg]);
  const dirty = cfg.sections.filter((s) => ctl.dirtySections.has(s));
  const blocking = cfg.sections.some((s) => hasBlockingErrors(validateForSection(ctl.schema, ctl.draft, s)));

  const close = useCallback(() => {
    if (dirty.length && !window.confirm("Có thay đổi chưa lưu — đóng và bỏ thay đổi?")) return;
    onClose();
  }, [dirty.length, onClose]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const save = async () => {
    setSaving(true);
    setMsg(null);
    let ok = true;
    for (const s of dirty) ok = (await ctl.saveSection(s)) && ok;
    setSaving(false);
    if (!ok) {
      setMsg({ ok: false, text: "Lưu chưa được — xem ô báo lỗi đỏ." });
      return;
    }
    await qc.invalidateQueries();
    setMsg({ ok: true, text: "Đã lưu — có hiệu lực ngay (ô gắn «restart» cần khởi động lại tiến trình)." });
  };

  const runTest = async (testId: string, deps: string[]) => {
    setTestById((m) => ({ ...m, [testId]: { status: "loading" } }));
    const overrides = Object.fromEntries(deps.map((k) => [k, ctl.draft[k]]));
    try {
      const r = await testSettingsConnection(testId, { overrides });
      setTestById((m) => ({
        ...m,
        [testId]: { status: r.ok ? "success" : "error", latencyMs: r.latencyMs, message: r.message },
      }));
    } catch (e) {
      setTestById((m) => ({ ...m, [testId]: { status: "error", message: e instanceof Error ? e.message : "Lỗi" } }));
    }
  };

  const renderFields = (fields: SettingsFieldMeta[]) => {
    const tests = new Map<string, { label: string; deps: string[] }>();
    for (const f of fields) {
      if (f.testAction?.id) tests.set(f.testAction.id, { label: f.testAction.label, deps: f.testAction.dependsOnKeys });
    }
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {flattenRenderableFields(fields).map((item) =>
          item.kind === "group" ? (
            <div key={item.groupId} className="rounded-xl border border-slate-100 bg-white/80 p-4 shadow-sm md:col-span-2">
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
          ) : (
            <div key={item.meta.key} className={isWide(item.meta) ? "md:col-span-2" : undefined}>
              <SettingsFieldRenderer
                meta={item.meta}
                draft={ctl.draft}
                sources={ctl.sources}
                secretsInfo={ctl.secretsInfo}
                secretOverrides={ctl.secretOverrides}
                errors={ctl.validationErrors}
                warnings={ctl.validationWarnings}
                onFieldChange={(k, v) => {
                  setMsg(null);
                  ctl.setField(k, v);
                }}
                onSecretChange={ctl.setSecretField}
                access={ctl.access}
              />
            </div>
          )
        )}
        {[...tests].map(([tid, t]) => (
          <div key={tid} className="md:col-span-2">
            <SettingsTestConnectionRow
              label={t.label}
              state={testById[tid] ?? { status: "idle" }}
              onTest={() => runTest(tid, t.deps)}
            />
          </div>
        ))}
      </div>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 p-4 sm:p-8"
      onMouseDown={(e) => e.target === e.currentTarget && close()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={cfg.title}
        className="flex max-h-full w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-slate-50 shadow-2xl"
      >
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-5 py-3">
          <Settings className="size-4 text-slate-500" />
          <h2 className="text-base font-semibold text-slate-900">{cfg.title}</h2>
          <Link to="/app/settings" className="ml-auto text-xs text-slate-400 hover:underline" onClick={onClose}>
            Tất cả cài đặt →
          </Link>
          <button type="button" aria-label="Đóng" onClick={close} className="rounded-md p-1 text-slate-500 hover:bg-slate-100">
            <X className="size-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {ctl.loading ? (
            <p className="py-12 text-center text-sm text-slate-500">Đang tải cài đặt…</p>
          ) : ctl.loadError ? (
            <div className="py-12 text-center text-sm text-red-600">
              Không tải được cài đặt: {ctl.loadError}{" "}
              <button type="button" className="underline" onClick={ctl.reload}>
                Thử lại
              </button>
            </div>
          ) : groups.length === 0 ? (
            <p className="py-12 text-center text-sm text-slate-500">Màn hình này chưa có cài đặt nào.</p>
          ) : (
            <div className="space-y-6">
              {groups.map((g) => (
                <section key={g.title}>
                  <h3 className="mb-2 text-sm font-semibold text-slate-700">{g.title}</h3>
                  {renderFields(g.fields)}
                </section>
              ))}
            </div>
          )}
        </div>

        <footer className="flex flex-wrap items-center gap-2 border-t border-slate-200 bg-white px-5 py-3">
          {msg ? (
            <span className={cn("text-sm", msg.ok ? "text-emerald-700" : "text-red-600")}>{msg.text}</span>
          ) : dirty.length ? (
            <span className="text-sm text-amber-700">Có thay đổi chưa lưu</span>
          ) : null}
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              disabled={!dirty.length || saving}
              onClick={() => {
                ctl.discardAll();
                setMsg(null);
              }}
              className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              Bỏ thay đổi
            </button>
            <button
              type="button"
              disabled={!dirty.length || blocking || saving}
              onClick={save}
              className="h-9 rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40"
            >
              {saving ? "Đang lưu…" : "Lưu"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
