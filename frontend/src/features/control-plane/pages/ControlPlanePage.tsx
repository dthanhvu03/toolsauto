import { Settings, Server, Sparkles, Workflow } from "lucide-react";
import { PageHeader } from "@/shared/ui/PageHeader";
import { QuickLink } from "@/features/overview/components/QuickLink";

export function ControlPlanePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Hub cấu hình"
        subtitle="Lối tắt bốn khu — không trùng nhau"
        classicHref="/app/control-plane"
      />
      <div className="mt-4 rounded-2xl border border-indigo-100 bg-indigo-50 px-5 py-4 text-sm text-slate-700">
        <p className="mb-2 font-semibold text-indigo-800">Bốn khu cấu hình</p>
        <ul className="list-inside list-disc space-y-1 text-xs text-slate-600">
          <li>
            <strong>Cài đặt vận hành</strong> — số, toggle, worker, viral, lịch Threads.
          </li>
          <li>
            <strong>AI Studio</strong> — prompt caption, persona, fallback.
          </li>
          <li>
            <strong>Cấu hình nền tảng</strong> — selector Playwright, workflow, CTA.
          </li>
          <li>
            <strong>Panel hệ thống</strong> — PM2, cookie Gemini, 9Router, disk.
          </li>
        </ul>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <QuickLink
          to="/app/settings"
          title="Cài đặt vận hành"
          desc="Giới hạn đăng, FFmpeg, worker tick"
          icon={Settings}
        />
        <QuickLink
          to="/app/go/ai-studio"
          title="AI Studio"
          desc="Thư viện prompt + sandbox Gemini"
          icon={Sparkles}
        />
        <QuickLink
          to="/app/go/platform-config"
          title="Cấu hình nền tảng"
          desc="Adapter, workflow, selector DOM"
          icon={Workflow}
        />
        <QuickLink
          to="/app/go/syspanel"
          title="Panel hệ thống"
          desc="PM2, cookie, disk, worker ops"
          icon={Server}
        />
      </div>
    </div>
  );
}
