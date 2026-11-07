import { useState, type KeyboardEvent } from "react";
import { ScreenSettingsButton } from "@/features/settings/components/ScreenSettingsButton";
import { cn } from "@/shared/lib/cn";
import { PageHeader } from "@/shared/ui/PageHeader";
import { HealthOverview } from "../components/HealthOverview";
import { LegacyJobsPanel } from "../components/LegacyJobsPanel";
import { ProcessTable } from "../components/ProcessTable";
import { WindowsHostPanel } from "../components/WindowsHostPanel";

const TABS = [
  { id: "processes", label: "Tiến trình" },
  { id: "windows", label: "Máy Windows" },
  { id: "jobs", label: "Hàng đợi (hệ cũ)" },
] as const;
type Tab = (typeof TABS)[number]["id"];
const TAB_KEY = "syspanel.tab";

function savedTab(): Tab {
  try {
    const v = window.localStorage.getItem(TAB_KEY);
    return TABS.some((t) => t.id === v) ? (v as Tab) : "processes";
  } catch {
    return "processes";
  }
}

/**
 * Panel hệ thống: đầu trang luôn có ô tóm tắt (Windows + WSL + GPU) và «Cần chú ý»;
 * chi tiết chia tab — Tiến trình (PM2 + bot systemd) · Máy Windows · Hàng đợi job (hệ cũ). Nhớ tab đang xem.
 * Thanh tab tự làm (Tabs dùng chung xếp ngang list + nội dung vì `data-horizontal:` không khớp `data-orientation`).
 */
export function SyspanelPage() {
  const [tab, setTab] = useState<Tab>(savedTab);
  const pick = (v: Tab) => {
    setTab(v);
    try {
      window.localStorage.setItem(TAB_KEY, v);
    } catch {
      /* trình duyệt chặn lưu — chỉ không nhớ tab */
    }
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = TABS.findIndex((t) => t.id === tab);
    const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length].id;
    pick(next);
    document.getElementById(`syspanel-tab-${next}`)?.focus();
  };

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        actions={<ScreenSettingsButton screen="syspanel" />}
        title="Panel hệ thống"
        subtitle="Sức khoẻ máy Windows + WSL, tiến trình (bật / tắt), hàng đợi job — cookie Gemini vẫn ở Classic"
        classicHref="/syspanel"
      />
      <HealthOverview />

      <div
        role="tablist"
        aria-label="Chi tiết"
        onKeyDown={onKey}
        className="mt-6 flex gap-1 overflow-x-auto border-b border-slate-200"
      >
        {TABS.map((t) => {
          const on = t.id === tab;
          return (
            <button
              key={t.id}
              id={`syspanel-tab-${t.id}`}
              type="button"
              role="tab"
              aria-selected={on}
              aria-controls={`syspanel-panel-${t.id}`}
              tabIndex={on ? 0 : -1}
              onClick={() => pick(t.id)}
              className={cn(
                "-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                on ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <div id={`syspanel-panel-${tab}`} role="tabpanel" aria-labelledby={`syspanel-tab-${tab}`} className="mt-4">
        {tab === "processes" ? <ProcessTable /> : tab === "windows" ? <WindowsHostPanel /> : <LegacyJobsPanel />}
      </div>
    </div>
  );
}
