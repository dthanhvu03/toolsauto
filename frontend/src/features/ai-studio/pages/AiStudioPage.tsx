import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { primaryBtnClass } from "@/shared/ui/controls";
import { useAiStudioController } from "../hooks/useAiStudioController";
import type { StudioItem } from "../types/aiStudio.types";

function StudioGroup({
  title,
  items,
  onPick,
  activeKey,
}: {
  title: string;
  items: StudioItem[];
  onPick: (item: StudioItem) => void;
  activeKey?: string;
}) {
  return (
    <Panel className="mt-6">
      <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">{title}</div>
      <ul className="divide-y divide-slate-100">
        {items.map((it) => (
          <li key={it.key}>
            <button
              type="button"
              className={`w-full px-4 py-3 text-left ${it.key === activeKey ? "bg-indigo-50" : "hover:bg-slate-50"}`}
              onClick={() => onPick(it)}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{it.label}</span>
                <span className="text-[10px] text-slate-400">{it.chars} ký tự</span>
              </div>
              <p className="mt-1 font-mono text-[11px] text-slate-500">{it.key}</p>
              <p className="mt-1 line-clamp-2 text-xs text-slate-600">{it.preview || "(trống)"}</p>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function AiStudioPage() {
  const { query, data, selected, draft, setDraft, msg, saving, pick, save } = useAiStudioController();

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="AI Studio" subtitle="Sửa prompt ngay trên SPA" classicHref="/app/ai-studio" />
      <ActionMsg text={msg} />
      <QueryBody
        isLoading={query.isLoading}
        isError={query.isError}
        loadingText="Đang tải…"
        errorText="Lỗi tải AI Studio"
      >
        {data ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <StudioGroup title="Persona" items={data.personas} onPick={pick} activeKey={selected?.key} />
              <StudioGroup title="Config" items={data.configs} onPick={pick} activeKey={selected?.key} />
              <StudioGroup title="Platform" items={data.platforms} onPick={pick} activeKey={selected?.key} />
            </div>
            <Panel className="mt-6 h-fit">
              <div className="border-b border-slate-100 px-4 py-3 text-sm font-semibold">
                {selected ? selected.label : "Chọn một prompt"}
              </div>
              <div className="p-4">
                <textarea
                  className="min-h-[18rem] w-full rounded-lg border border-slate-200 p-3 font-mono text-xs"
                  value={draft}
                  disabled={!selected}
                  onChange={(e) => setDraft(e.target.value)}
                />
                <button type="button" className={`${primaryBtnClass} mt-3`} disabled={!selected || saving} onClick={save}>
                  Lưu
                </button>
                <p className="mt-2 text-xs text-slate-400">Sandbox test-run vẫn ở Classic.</p>
              </div>
            </Panel>
          </div>
        ) : null}
      </QueryBody>
    </div>
  );
}
