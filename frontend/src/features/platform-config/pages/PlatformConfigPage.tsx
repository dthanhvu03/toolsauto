import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { usePlatformConfigController } from "../hooks/usePlatformConfigController";

export function PlatformConfigPage() {
  const ctl = usePlatformConfigController();

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Cấu hình nền tảng"
        subtitle="Danh sách native — CRUD selector / workflow / CTA vẫn Classic"
        classicHref="/platform-config/"
      />
      <Panel className="mt-4">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Platforms</div>
        <QueryBody
          isLoading={ctl.platforms.isLoading}
          isError={ctl.platforms.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải platforms"
        >
          {(ctl.platforms.data ?? []).length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-slate-400">Chưa có platform</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {(ctl.platforms.data ?? []).map((p) => (
                <li key={p.id} className="flex items-center justify-between px-4 py-2 text-sm">
                  <span>
                    {p.display_emoji ? `${p.display_emoji} ` : ""}
                    <strong>{p.display_name || p.platform}</strong>
                    <span className="ml-2 text-xs text-slate-400">{p.adapter_class}</span>
                  </span>
                  <span className={p.is_active ? "text-xs text-emerald-700" : "text-xs text-slate-400"}>
                    {p.is_active ? "active" : "tắt"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </QueryBody>
      </Panel>
      <Panel className="mt-6">
        <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">Workflows</div>
        <QueryBody
          isLoading={ctl.workflows.isLoading}
          isError={ctl.workflows.isError}
          loadingText="Đang tải…"
          errorText="Lỗi tải workflows"
        >
          {(ctl.workflows.data ?? []).length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-slate-400">Chưa có workflow</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {(ctl.workflows.data ?? []).map((w) => (
                <li key={w.id} className="flex items-center justify-between px-4 py-2 text-sm">
                  <span>
                    <strong>{w.name}</strong>
                    <span className="ml-2 text-xs text-slate-400">
                      {w.platform} · {w.job_type} · {Array.isArray(w.steps) ? w.steps.length : 0} bước
                    </span>
                  </span>
                  <span className={w.is_active ? "text-xs text-emerald-700" : "text-xs text-slate-400"}>
                    {w.is_active ? "active" : "tắt"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </QueryBody>
      </Panel>
    </div>
  );
}
