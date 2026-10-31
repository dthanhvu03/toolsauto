import { useState } from "react";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { ghostBtnClass, inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import * as api from "../api/studioApi";
import { useAction, useAssets, useSetup } from "../hooks/useStudio";
import type { Asset, Channel, Template } from "../types/studio.types";

const FLAGS: { key: keyof Channel; label: string; hint: string }[] = [
  { key: "take_reup", label: "Nhận reup", hint: "video reup hệ cũ tải cho kênh này đi qua Studio" },
  { key: "auto_approve", label: "Tự duyệt", hint: "có caption là sang Buffer, không chờ anh duyệt" },
  { key: "show_credit", label: "Ghi nguồn", hint: "hiện «Nguồn: @…» trên video reup" },
  { key: "active", label: "Bật", hint: "tắt = Studio bỏ qua kênh này" },
];
const ASSET_SLOTS: { key: "logo_asset_id" | "intro_asset_id" | "outro_asset_id"; label: string; kind: Asset["kind"] }[] = [
  { key: "logo_asset_id", label: "Logo", kind: "image" },
  { key: "intro_asset_id", label: "Intro", kind: "video" },
  { key: "outro_asset_id", label: "Outro", kind: "video" },
];
const keys = [["studio-setup"]];

function ChannelRow({ c, templates, assets }: { c: Channel; templates: Template[]; assets: Asset[] }) {
  const act = useAction((body: Partial<Channel>) => api.updateChannel(c.id, body), `Đã lưu ${c.name}.`, keys);
  return (
    <Panel className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{c.name}</span>
        <span className="font-mono text-xs text-slate-400">{c.buffer_channel_id}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
        {FLAGS.map((f) => (
          <label key={f.key} className="flex items-center gap-1.5 text-sm" title={f.hint}>
            <input type="checkbox" checked={!!c[f.key]} disabled={act.busy} onChange={(e) => act.run({ [f.key]: e.target.checked })} />
            {f.label}
          </label>
        ))}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-4">
        <label className="text-xs text-slate-500">
          Mẫu mặc định
          <select className={`${selectClass} mt-1 w-full`} value={c.template_id ?? ""} onChange={(e) => act.run({ template_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">basic</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {ASSET_SLOTS.map((s) => (
          <label key={s.key} className="text-xs text-slate-500">
            {s.label}
            <select className={`${selectClass} mt-1 w-full`} value={c[s.key] ?? ""} onChange={(e) => act.run({ [s.key]: e.target.value ? Number(e.target.value) : null })}>
              <option value="">— không —</option>
              {assets
                .filter((a) => a.kind === s.kind)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    #{a.id} {a.title}
                  </option>
                ))}
            </select>
          </label>
        ))}
      </div>
      <ActionMsg text={act.msg} />
    </Panel>
  );
}

function TemplateEditor({ t, kinds }: { t?: Template; kinds: { kind: string; defaults: Record<string, unknown> }[] }) {
  const [name, setName] = useState(t?.name ?? "");
  const [kind, setKind] = useState(t?.kind ?? kinds[0]?.kind ?? "basic");
  const [params, setParams] = useState(JSON.stringify(t?.params ?? kinds[0]?.defaults ?? {}, null, 2));
  const [err, setErr] = useState("");
  const act = useAction(
    (body: Omit<Template, "id">) => (t ? api.updateTemplate(t.id, body) : api.createTemplate(body)),
    t ? "Đã lưu mẫu." : "Đã tạo mẫu.",
    keys
  );
  const submit = () => {
    try {
      act.run({ name, kind, params: JSON.parse(params || "{}") });
      setErr("");
    } catch {
      setErr("Tham số phải là JSON hợp lệ");
    }
  };
  return (
    <Panel className="p-4">
      <div className="flex flex-wrap gap-2">
        <input className={inputClass} placeholder="Tên mẫu" value={name} onChange={(e) => setName(e.target.value)} />
        <select
          className={selectClass}
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            if (!t) setParams(JSON.stringify(kinds.find((k) => k.kind === e.target.value)?.defaults ?? {}, null, 2));
          }}
        >
          {kinds.map((k) => (
            <option key={k.kind} value={k.kind}>
              {k.kind}
            </option>
          ))}
        </select>
        <button type="button" className={primaryBtnClass} disabled={!name.trim() || act.busy} onClick={submit}>
          {t ? "Lưu" : "Tạo mẫu"}
        </button>
      </div>
      <textarea className="mt-2 h-36 w-full rounded-lg border border-slate-200 p-2 font-mono text-xs" value={params} onChange={(e) => setParams(e.target.value)} />
      <ActionMsg text={err || act.msg} />
    </Panel>
  );
}

export function StudioSetupPage() {
  const q = useSetup();
  const assets = useAssets();
  const [bufferId, setBufferId] = useState("");
  const add = useAction((id: string) => api.createChannel({ buffer_channel_id: id }), "Đã thêm kênh vào Studio.", keys);
  const d = q.data;
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Kênh & mẫu" subtitle="Kênh Buffer nào đi qua Studio, dùng mẫu edit nào, logo / intro / outro" />
      <QueryBody isLoading={q.isLoading} isError={q.isError} loadingText="Đang tải…" errorText="Không tải được thiết lập Studio">
        {d ? (
          <>
            <h2 className="mt-6 text-sm font-semibold uppercase tracking-wide text-slate-400">Kênh</h2>
            <div className="mt-2 flex flex-wrap gap-2">
              <select className={selectClass} value={bufferId} onChange={(e) => setBufferId(e.target.value)}>
                <option value="">Thêm kênh Buffer vào Studio…</option>
                {d.buffer_channels.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
              <button type="button" className={ghostBtnClass + " h-9"} disabled={!bufferId || add.busy} onClick={() => add.run(bufferId)}>
                Thêm
              </button>
              <ActionMsg text={add.msg} />
            </div>
            <div className="mt-3 flex flex-col gap-3">
              {d.channels.length === 0 ? <p className="text-sm text-slate-400">Chưa có kênh nào trong Studio.</p> : null}
              {d.channels.map((c) => (
                <ChannelRow key={c.id} c={c} templates={d.templates} assets={assets.data?.assets ?? []} />
              ))}
            </div>

            <h2 className="mt-8 text-sm font-semibold uppercase tracking-wide text-slate-400">Mẫu edit</h2>
            <div className="mt-2 grid gap-3 lg:grid-cols-2">
              {d.templates.map((t) => (
                <TemplateEditor key={t.id} t={t} kinds={d.template_kinds} />
              ))}
              <TemplateEditor key={`new-${d.templates.length}`} kinds={d.template_kinds} />
            </div>
          </>
        ) : null}
      </QueryBody>
    </div>
  );
}
