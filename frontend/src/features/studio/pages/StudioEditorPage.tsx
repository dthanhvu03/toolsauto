import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ActionMsg } from "@/shared/ui/ActionMsg";
import { dangerBtnClass, ghostBtnClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { Panel } from "@/shared/ui/Panel";
import { QueryBody } from "@/shared/ui/QueryBody";
import * as api from "../api/studioApi";
import { ClipEditor } from "../components/ClipEditor";
import { SubtitleEditor } from "../components/SubtitleEditor";
import { TextAudioPanel } from "../components/TextAudioPanel";
import { useAction, useSetup } from "../hooks/useStudio";
import { keptSeconds } from "../lib/clips";
import { mmss, STATUS_LABEL, STATUS_STYLE } from "../lib/status";
import type { ProjectSpec } from "../types/studio.types";

const BUSY = new Set(["DRAFT", "RENDERING", "RENDERED"]);

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Panel className="p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</h2>
      {children}
    </Panel>
  );
}

export function StudioEditorPage() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["studio-project", id],
    queryFn: () => api.fetchProject(id),
    refetchInterval: (s) => (s.state.data && BUSY.has(s.state.data.project.status) ? 4_000 : false),
  });
  const setup = useSetup();
  const d = q.data;

  const [spec, setSpec] = useState<ProjectSpec | null>(null);
  const [caption, setCaption] = useState("");
  const [tags, setTags] = useState("");
  const [templateId, setTemplateId] = useState<number | "">("");
  const [channelId, setChannelId] = useState<number | "">("");
  const [variantCount, setVariantCount] = useState(3);
  const renderedAt = d?.project.rendered_at;
  useEffect(() => {
    if (!d) return;
    setSpec(d.spec);
    setCaption(d.project.caption ?? "");
    setTags((d.project.hashtags ?? []).join(" "));
    setTemplateId(d.template?.id ?? "");
    setChannelId(d.channel?.id ?? "");
    // Chỉ nạp lại khi có bản dựng mới / đổi trạng thái — không đè chỗ anh đang gõ mỗi lần hỏi lại.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d?.project.id, d?.project.status, renderedAt]);

  const refresh = [["studio-project", String(id)], ["studio-projects"]];
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["studio-project", id] });
    qc.invalidateQueries({ queryKey: ["studio-projects"] });
  };
  const save = useAction((s: ProjectSpec) => api.saveSpec(id, s).then(invalidate), "Đã lưu — đang render lại…", refresh);
  const meta = useAction(
    () => api.updateMeta(id, { caption, hashtags: tags.split(/\s+/).filter(Boolean), channel_id: channelId || undefined }).then(invalidate),
    "Đã lưu caption / kênh.",
    refresh
  );
  const approve = useAction(
    () => api.approveProject(id, { caption, hashtags: tags.split(/\s+/).filter(Boolean) }).then(invalidate),
    "Đã duyệt — đang chuyển sang Buffer.",
    refresh
  );
  const reject = useAction(() => api.rejectProject(id).then(invalidate), "Đã bỏ.", refresh);
  const remake = useAction(
    () => api.recompose(id, { template_id: templateId || null, channel_id: channelId || null }),
    "Đang dựng lại bằng mẫu mới — dự án mới sẽ hiện trong Studio.",
    refresh
  );

  const variants = useAction((n: number) => api.makeVariants(id, n), "Đang dựng biến thể — sẽ hiện trong Studio «Đang làm».", refresh);
  // Chỉ đoạn cắt (đầu / cuối) làm lệch số câu phụ đề — lật gương / âm lượng thì không.
  const cuts = (clips: ProjectSpec["clips"]) => JSON.stringify(clips.map((c) => [c.asset, c.start, c.end]));
  const clipsDirty = useMemo(() => !!d && !!spec && cuts(spec.clips) !== cuts(d.spec.clips), [d, spec]);
  const specDirty = useMemo(() => !!d && !!spec && JSON.stringify(spec) !== JSON.stringify(d.spec), [d, spec]);
  const durations = Object.fromEntries((d?.assets ?? []).map((a) => [a.id, a.duration ?? 0]));
  const msg = save.msg || meta.msg || approve.msg || reject.msg || remake.msg || variants.msg;

  return (
    <div className="mx-auto max-w-6xl">
      <Link to="/app/go/studio" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
        <ArrowLeft className="size-4" /> Studio
      </Link>
      <QueryBody isLoading={q.isLoading} isError={q.isError || (!q.isLoading && !d)} loadingText="Đang tải…" errorText="Không tải được dự án">
        {d && spec ? (
          <>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold">Dự án #{d.project.id}</h1>
              <span className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[d.project.status]}`}>{STATUS_LABEL[d.project.status]}</span>
              <span className="text-sm text-slate-500">
                {d.channel?.name ?? "chưa gắn kênh"} · mẫu {d.template?.name ?? "basic"} · {mmss(d.project.duration)}
              </span>
            </div>
            {d.project.error ? <p className="mt-2 text-sm text-red-700">{d.project.error}</p> : null}
            {!d.project.editable ? (
              <p className="mt-2 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-600">
                Video đã sang Buffer (material #{d.project.viral_material_id}) — chỉ xem. Đổi giờ / huỷ lịch qua Telegram.
              </p>
            ) : null}
            <ActionMsg text={msg} />

            <div className="mt-4 grid gap-4 lg:grid-cols-[340px_1fr]">
              <div className="lg:sticky lg:top-20 lg:self-start">
                {d.project.rendered_at && !BUSY.has(d.project.status) ? (
                  <video
                    key={d.project.rendered_at}
                    src={api.projectVideoUrl(d.project.id, d.project.rendered_at)}
                    controls
                    playsInline
                    className="mx-auto aspect-[9/16] max-h-[70vh] w-full rounded-2xl bg-black"
                  />
                ) : (
                  <div className="flex aspect-[9/16] max-h-[70vh] w-full items-center justify-center rounded-2xl bg-slate-900 text-sm text-slate-300">
                    {BUSY.has(d.project.status) ? "Đang dựng…" : "Chưa có bản render"}
                  </div>
                )}
                {d.project.editable ? (
                  <div className="mt-3 flex flex-col gap-2">
                    <button type="button" className={primaryBtnClass} disabled={!specDirty || save.busy} onClick={() => save.run(spec)}>
                      {save.busy ? "Đang lưu…" : `Lưu & render lại${specDirty ? ` (${mmss(keptSeconds(spec.clips, durations))})` : ""}`}
                    </button>
                    {d.project.status === "REVIEW" ? (
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className={`${ghostBtnClass} h-9 flex-1 border-emerald-300 text-sm text-emerald-800`}
                          disabled={approve.busy || specDirty || !caption.trim()}
                          title={specDirty ? "Lưu & render trước khi duyệt" : !caption.trim() ? "Cần caption" : ""}
                          onClick={() => approve.run(undefined)}
                        >
                          Duyệt → Buffer
                        </button>
                        <button type="button" className={`${dangerBtnClass} h-9 text-sm`} disabled={reject.busy} onClick={() => reject.run(undefined)}>
                          Bỏ
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="flex min-w-0 flex-col gap-4">
                <Section title="Caption & kênh">
                  <textarea
                    className="min-h-28 w-full rounded-lg border border-slate-200 p-2 text-sm"
                    value={caption}
                    disabled={!d.project.editable}
                    placeholder="Caption đăng kèm video"
                    onChange={(e) => setCaption(e.target.value)}
                  />
                  <input
                    className="mt-2 h-9 w-full rounded-lg border border-slate-200 px-3 text-sm"
                    value={tags}
                    disabled={!d.project.editable}
                    placeholder="#hashtag cách nhau dấu cách"
                    onChange={(e) => setTags(e.target.value)}
                  />
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <select className={selectClass} value={channelId} disabled={!d.project.editable} onChange={(e) => setChannelId(e.target.value ? Number(e.target.value) : "")}>
                      <option value="">Chưa gắn kênh</option>
                      {(setup.data?.channels ?? []).map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                    <button type="button" className={ghostBtnClass} disabled={!d.project.editable || meta.busy} onClick={() => meta.run(undefined)}>
                      Lưu caption / kênh
                    </button>
                  </div>
                </Section>

                {d.asset?.kind === "video" ? (
                  <Section title="Đoạn cắt">
                    <ClipEditor
                      clips={spec.clips}
                      main={d.asset}
                      assets={d.assets}
                      disabled={!d.project.editable}
                      canFlip={d.variants_allowed}
                      onChange={(clips) => setSpec({ ...spec, clips })}
                    />
                  </Section>
                ) : null}

                <Section title="Phụ đề">
                  <SubtitleEditor
                    sub={spec.subtitles}
                    lines={d.subtitle_lines}
                    locked={clipsDirty}
                    disabled={!d.project.editable}
                    onChange={(subtitles) => setSpec({ ...spec, subtitles })}
                  />
                </Section>

                <Section title="Màu, chữ & âm thanh">
                  <TextAudioPanel spec={spec} assets={d.assets} luts={d.luts} disabled={!d.project.editable} onChange={setSpec} />
                </Section>

                {d.variants_allowed ? (
                  <Section title="Biến thể A/B">
                    <div className="flex flex-wrap items-center gap-2">
                      <select className={selectClass} value={variantCount} onChange={(e) => setVariantCount(Number(e.target.value))}>
                        {[2, 3, 4, 5].map((n) => (
                          <option key={n} value={n}>
                            {n} biến thể
                          </option>
                        ))}
                      </select>
                      <button type="button" className={ghostBtnClass} disabled={variants.busy} onClick={() => variants.run(variantCount)}>
                        Dựng biến thể
                      </button>
                    </div>
                    <p className="mt-1 text-[11px] text-slate-400">
                      Cùng video gốc, mỗi bản ngẫu nhiên khác nhau theo tham số mẫu (mirror / lut; mẫu ab_montage xáo thứ tự đoạn). Dự án này giữ nguyên.
                    </p>
                  </Section>
                ) : null}

                <Section title="Đổi mẫu">
                  <div className="flex flex-wrap items-center gap-2">
                    <select className={selectClass} value={templateId} disabled={!d.project.editable} onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : "")}>
                      <option value="">basic (mặc định)</option>
                      {(setup.data?.templates ?? []).map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} · {t.kind}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className={ghostBtnClass}
                      disabled={!d.project.editable || remake.busy || templateId === (d.template?.id ?? "")}
                      onClick={() => remake.run(undefined)}
                    >
                      Dựng lại bằng mẫu này
                    </button>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400">Tạo dự án mới từ cùng video gốc; dự án này chuyển sang «Đã bỏ».</p>
                </Section>
              </div>
            </div>
          </>
        ) : null}
      </QueryBody>
    </div>
  );
}
