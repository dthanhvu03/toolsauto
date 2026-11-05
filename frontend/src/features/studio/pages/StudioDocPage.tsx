import { useQuery } from "@tanstack/react-query";
import { Film, Search, Settings, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ghostBtnClass, inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Toast } from "@/shared/ui/Toast";
import * as api from "../api/studioApi";
import { useAction, useJobs } from "../hooks/useStudio";
import { projectVideoUrl } from "../api/studioApi";

type Candidate = {
  provider: string;
  image_url: string;
  thumb_url: string;
  source_page: string;
  title: string;
  author: string;
  license: string;
  license_url: string;
  width: number;
  height: number;
};

type Shot = {
  shot_id: string;
  beat_id: string;
  start_ms: number;
  end_ms: number;
  narration: string;
  motion: string;
  status: string;
  keywords: string[];
  candidates: Candidate[];
  search_note: string;
  selected: null | {
    asset_id: number;
    credit: string;
    license: string;
    rights_status: string;
    illustration: boolean;
    source_page: string;
    provider: string;
    author: string;
  };
};

type DocDetail = {
  project: { id: number; status: string; has_video: boolean; editable: boolean; error: string | null };
  audio: { id: number | null; title: string | null; duration: number | null };
  doc: {
    duration_ms: number;
    language: string | null;
    preview_end_ms: number;
    transcript: { start_ms: number; end_ms: number; raw_text: string; reviewed_text: string }[];
    beats: { beat_id: string; summary: string; fact_status: string }[];
    shots: Shot[];
  };
  rights_gate: { ok: boolean; blockers: string[]; can_export: boolean; window_end_ms: number };
};

const RIGHTS = ["RIGHTS_UNKNOWN", "RIGHTS_VERIFIED", "APPROVED", "RIGHTS_RESTRICTED"];
const PROVIDER_LABEL: Record<string, string> = {
  wikimedia: "Wikimedia",
  openverse: "Openverse",
  pexels: "Pexels",
  pixabay: "Pixabay",
  google: "Google",
  upload: "Tải lên",
};

function fmt(ms: number) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function StudioDocPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const dirty = useRef(false); // đang sửa transcript → không để lần tải lại 4s ghi đè
  const [fileName, setFileName] = useState("");
  const [language, setLanguage] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DocDetail | null>(null);
  const [shotId, setShotId] = useState("");
  const [query, setQuery] = useState("");
  const [rights, setRights] = useState("RIGHTS_UNKNOWN");
  const [license, setLicense] = useState("");
  const [credit, setCredit] = useState("");
  const [sourcePage, setSourcePage] = useState("");
  const [illustration, setIllustration] = useState(false);
  const [toast, setToast] = useState({ text: "", seq: 0 });
  const say = (text: string) => setToast((t) => ({ text, seq: t.seq + 1 }));

  const cfg = useQuery({ queryKey: ["studio-doc-config"], queryFn: api.fetchDocConfig, staleTime: 30_000 });
  const lang = language ?? cfg.data?.default_language ?? "auto";

  const jobs = useJobs(taskId ? [taskId] : []);
  const tracked = useMemo(() => (jobs.data?.jobs ?? []).find((j) => j.id === taskId), [jobs.data, taskId]);
  const shot = detail?.doc.shots.find((s) => s.shot_id === shotId) ?? null;

  useEffect(() => {
    const pid = tracked?.project_id;
    if (pid && pid !== projectId) setProjectId(pid);
  }, [tracked?.project_id, projectId]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    const load = () =>
      api.fetchDocProject(projectId).then((raw) => {
        if (cancelled || dirty.current) return;
        const d = raw as DocDetail;
        setDetail(d);
        setShotId((cur) => cur || d.doc?.shots?.[0]?.shot_id || "");
      }).catch((e) => say(String(e.message || e)));
    void load();
    const t = setInterval(() => void load(), 4000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [projectId]);

  // đổi cảnh → ô tìm hiện từ khóa đầu tiên của cảnh đó
  useEffect(() => {
    setQuery(shot?.keywords?.[0] ?? "");
  }, [shotId]); // eslint-disable-line react-hooks/exhaustive-deps

  const apply = (d: unknown) => setDetail(d as DocDetail);

  const upload = useAction(
    async (file: File) => {
      const res = await api.uploadDocAudio(file, { language: lang });
      setTaskId(res.task_id);
      setProjectId(null);
      setDetail(null);
      setShotId("");
      return res;
    },
    "Đã nhận audio — đang chép lời và chia cảnh.",
    [["studio-jobs"]]
  );

  const saveTranscript = useAction(
    async () => {
      if (!detail || !projectId) throw new Error("chưa có dự án");
      const d = await api.saveDocTranscript(
        projectId,
        detail.doc.transcript.map((s) => ({
          start_ms: s.start_ms,
          end_ms: s.end_ms,
          raw_text: s.raw_text,
          reviewed_text: s.reviewed_text,
        }))
      );
      dirty.current = false;
      apply(d);
    },
    "Đã lưu lời đã sửa (phụ đề dùng bản này)."
  );

  const search = useAction(
    async () => {
      if (!projectId || !shot) throw new Error("chọn cảnh trước");
      const typed = query.trim();
      const rest = (shot.keywords ?? []).filter((k) => k !== typed);
      apply(await api.searchDocImages(projectId, shot.shot_id, typed ? [typed, ...rest] : rest));
    },
    "Đã tìm ảnh."
  );

  const pick = useAction(
    async (index: number) => {
      if (!projectId || !shot) throw new Error("chọn cảnh trước");
      apply(await api.pickDocImage(projectId, shot.shot_id, index));
    },
    "Đã tải ảnh về và gắn vào cảnh."
  );

  const attach = useAction(
    async (file: File) => {
      if (!projectId || !shotId) throw new Error("chọn cảnh trước");
      apply(
        await api.attachDocImage(projectId, shotId, file, {
          credit,
          license,
          rights_status: rights,
          illustration,
          source_page: sourcePage,
          proof_note: illustration ? "ảnh minh họa tự làm" : "",
        })
      );
    },
    "Đã gắn ảnh của anh vào cảnh."
  );

  const previewStrict = useAction(
    async () => {
      if (!projectId) throw new Error("chưa có dự án");
      return api.requestDocPreview(projectId, true);
    },
    "Đã xếp dựng video (có kiểm quyền)."
  );

  const previewLoose = useAction(
    async () => {
      if (!projectId) throw new Error("chưa có dự án");
      return api.requestDocPreview(projectId, false);
    },
    "Đã xếp dựng bản xem thử (bỏ qua quyền — không dùng để đăng)."
  );

  const settingsUrl = cfg.data?.settings_url ?? "/app/settings";
  const withImage = detail?.doc.shots.filter((s) => s.selected).length ?? 0;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Audio → Documentary"
        subtitle="Tải audio · chép lời · chia cảnh theo lời · gắn ảnh (tải lên hoặc tìm trên internet) · dựng video"
      />
      <Toast text={toast.text} seq={toast.seq} />
      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
        <Link to="/app/go/studio" className="underline">← Studio</Link>
        <a href={settingsUrl} className="inline-flex items-center gap-1 underline">
          <Settings className="size-3.5" /> Cài đặt Audio→Doc
        </a>
        {cfg.data ? (
          <span>
            Khung {cfg.data.canvas} · dựng {cfg.data.preview_sec ? `${cfg.data.preview_sec}s đầu` : "toàn bộ audio"} · nguồn ảnh:{" "}
            {cfg.data.sources.length ? cfg.data.sources.map((s) => PROVIDER_LABEL[s] ?? s).join(", ") : "chưa bật"}
          </span>
        ) : null}
      </p>

      <section className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800">1. Tải audio</h2>
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <input
            ref={fileRef}
            type="file"
            accept="audio/*,.mp3,.wav,.m4a"
            className="hidden"
            onChange={(e) => setFileName(e.target.files?.[0]?.name ?? "")}
          />
          <button type="button" className="h-9 rounded-lg border border-slate-200 px-3 text-sm" onClick={() => fileRef.current?.click()}>
            {fileName || "Chọn MP3 / WAV / M4A…"}
          </button>
          <label className="text-xs text-slate-600">
            Ngôn ngữ audio
            <select className={`${selectClass} mt-1 block`} value={lang} onChange={(e) => setLanguage(e.target.value)}>
              {(cfg.data?.languages ?? [{ code: "auto", label: "Tự nhận" }]).map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className={`${primaryBtnClass} inline-flex items-center gap-1.5`}
            disabled={!fileName || upload.busy}
            onClick={() => {
              const f = fileRef.current?.files?.[0];
              if (f) upload.run(f);
            }}
          >
            <Upload className="size-4" /> Bắt đầu
          </button>
        </div>
        {taskId ? (
          <p className="mt-2 text-xs text-slate-500">
            Việc #{taskId}
            {tracked ? ` · ${tracked.state} · ${tracked.current || "…"}` : ""}
            {projectId ? ` · dự án #${projectId}` : " · đang chép lời / chia cảnh…"}
          </p>
        ) : null}
        {upload.msg ? <p className="mt-1 text-xs text-emerald-700">{upload.msg}</p> : null}
      </section>

      {detail ? (
        <>
          <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">
              2. Lời đã chép ({detail.doc.transcript.length} câu) · audio {fmt(detail.doc.duration_ms)}
              {detail.doc.language ? ` · ngôn ngữ ${detail.doc.language}` : ""}
            </h2>
            <div className="mt-2 max-h-56 space-y-2 overflow-y-auto">
              {detail.doc.transcript.length === 0 ? (
                <p className="text-sm text-slate-400">Không chép được lời (audio không có tiếng nói). Cảnh được chia đều theo thời gian.</p>
              ) : (
                detail.doc.transcript.map((seg, i) => (
                  <div key={`${seg.start_ms}-${i}`} className="grid gap-1 rounded-lg bg-slate-50 p-2 text-sm sm:grid-cols-[4.5rem_1fr]">
                    <span className="tabular-nums text-slate-500">{fmt(seg.start_ms)}</span>
                    <input
                      className={inputClass}
                      value={seg.reviewed_text}
                      title={`Máy chép: ${seg.raw_text}`}
                      onChange={(e) => {
                        dirty.current = true;
                        const next = structuredClone(detail);
                        next.doc.transcript[i].reviewed_text = e.target.value;
                        setDetail(next);
                      }}
                    />
                  </div>
                ))
              )}
            </div>
            <button
              type="button"
              className={`${ghostBtnClass} mt-2`}
              disabled={saveTranscript.busy || !detail.doc.transcript.length}
              onClick={() => saveTranscript.run(undefined)}
            >
              Lưu lời đã sửa
            </button>
            {saveTranscript.msg ? <p className="mt-1 text-xs text-slate-600">{saveTranscript.msg}</p> : null}
          </section>

          <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">
              3. Cảnh ({withImage}/{detail.doc.shots.length} có ảnh) · {detail.doc.beats.length} đoạn ý
            </h2>
            <div className="mt-2 grid gap-3 md:grid-cols-[16rem_1fr]">
              <ul className="max-h-[28rem] space-y-1 overflow-y-auto text-sm">
                {detail.doc.shots.map((s) => (
                  <li key={s.shot_id}>
                    <button
                      type="button"
                      className={`w-full rounded-lg px-2 py-1.5 text-left ${shotId === s.shot_id ? "bg-indigo-50 text-indigo-900" : "hover:bg-slate-50"}`}
                      onClick={() => setShotId(s.shot_id)}
                    >
                      <span className="tabular-nums text-slate-500">{fmt(s.start_ms)}–{fmt(s.end_ms)}</span>{" "}
                      {s.selected ? (
                        <span className="text-emerald-700">· {PROVIDER_LABEL[s.selected.provider] ?? s.selected.provider}</span>
                      ) : (
                        <span className="text-amber-700">· chưa ảnh</span>
                      )}
                      <span className="block truncate text-xs text-slate-400">{s.narration || "(không lời)"}</span>
                    </button>
                  </li>
                ))}
              </ul>

              {shot ? (
                <div className="min-w-0 space-y-3">
                  <div className="rounded-lg bg-slate-50 p-2 text-sm">
                    <span className="font-medium">{shot.shot_id}</span>{" "}
                    <span className="text-slate-500">{fmt(shot.start_ms)}–{fmt(shot.end_ms)} · {shot.motion}</span>
                    <p className="mt-1 text-slate-700">{shot.narration || "(không lời)"}</p>
                    {shot.selected ? (
                      <p className="mt-1 text-xs text-emerald-800">
                        Đang dùng: {PROVIDER_LABEL[shot.selected.provider] ?? shot.selected.provider} · {shot.selected.rights_status}
                        {shot.selected.license ? ` · ${shot.selected.license}` : ""}
                        {shot.selected.author ? ` · ${shot.selected.author}` : ""}
                      </p>
                    ) : null}
                  </div>

                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        className={`${inputClass} min-w-0 flex-1`}
                        placeholder="Từ khóa tìm ảnh"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") search.run(undefined);
                        }}
                      />
                      <button type="button" className={`${ghostBtnClass} inline-flex items-center gap-1`} disabled={search.busy} onClick={() => search.run(undefined)}>
                        <Search className="size-4" /> {search.busy ? "Đang tìm…" : "Tìm ảnh"}
                      </button>
                    </div>
                    {shot.keywords.length > 1 ? (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {shot.keywords.map((k) => (
                          <button key={k} type="button" className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200" onClick={() => setQuery(k)}>
                            {k}
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {shot.search_note ? <p className="mt-1 text-xs text-amber-700">{shot.search_note}</p> : null}
                  </div>

                  {shot.candidates.length ? (
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                      {shot.candidates.map((c, i) => (
                        <button
                          key={c.image_url}
                          type="button"
                          disabled={pick.busy}
                          className="overflow-hidden rounded-lg border border-slate-200 text-left hover:border-indigo-400"
                          onClick={() => pick.run(i)}
                          title={c.title}
                        >
                          <img src={c.thumb_url || c.image_url} alt={c.title} loading="lazy" className="aspect-video w-full bg-slate-100 object-cover" />
                          <span className="block truncate px-1.5 py-1 text-[11px] text-slate-600">
                            {PROVIDER_LABEL[c.provider] ?? c.provider} · {c.license === "unknown" ? "chưa rõ quyền" : c.license}
                            {c.author ? ` · ${c.author}` : ""}
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400">Chưa có ảnh gợi ý — bấm «Tìm ảnh».</p>
                  )}

                  <details className="rounded-lg border border-slate-200 p-2">
                    <summary className="cursor-pointer text-sm text-slate-700">Tải ảnh của anh lên cho cảnh này</summary>
                    <div className="mt-2 flex flex-wrap items-end gap-2">
                      <label className="text-xs text-slate-600">
                        Quyền
                        <select className={`${selectClass} mt-1 block`} value={rights} onChange={(e) => setRights(e.target.value)}>
                          {RIGHTS.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                      </label>
                      <label className="text-xs text-slate-600">
                        Giấy phép
                        <input className={`${inputClass} mt-1 block w-32`} value={license} onChange={(e) => setLicense(e.target.value)} />
                      </label>
                      <label className="text-xs text-slate-600">
                        Tác giả / ghi công
                        <input className={`${inputClass} mt-1 block w-36`} value={credit} onChange={(e) => setCredit(e.target.value)} />
                      </label>
                      <label className="text-xs text-slate-600">
                        Trang nguồn
                        <input className={`${inputClass} mt-1 block w-44`} value={sourcePage} onChange={(e) => setSourcePage(e.target.value)} />
                      </label>
                      <label className="flex items-center gap-1.5 text-xs text-slate-600">
                        <input type="checkbox" checked={illustration} onChange={(e) => setIllustration(e.target.checked)} />
                        Ảnh minh họa tự làm
                      </label>
                      <label className={`${ghostBtnClass} cursor-pointer`}>
                        Chọn ảnh…
                        <input
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          className="hidden"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f) attach.run(f);
                            e.target.value = "";
                          }}
                        />
                      </label>
                    </div>
                  </details>
                  {pick.msg || attach.msg || search.msg ? (
                    <p className="text-xs text-slate-600">{pick.msg || attach.msg || search.msg}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </section>

          <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">
              4. Dựng video ({fmt(detail.rights_gate.window_end_ms)}) &amp; kiểm quyền
            </h2>
            <div className={`mt-2 rounded-lg px-3 py-2 text-sm ${detail.rights_gate.ok ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-950"}`}>
              {detail.rights_gate.ok
                ? "Mọi cảnh đã đủ quyền — dựng được bản chính."
                : `Chưa dựng bản chính được: ${detail.rights_gate.blockers.slice(0, 5).join(" · ")}${detail.rights_gate.blockers.length > 5 ? ` … (+${detail.rights_gate.blockers.length - 5})` : ""}`}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className={primaryBtnClass} disabled={previewStrict.busy} onClick={() => previewStrict.run(undefined)}>
                <Film className="mr-1 inline size-4" /> Dựng (kiểm quyền)
              </button>
              <button type="button" className={ghostBtnClass} disabled={previewLoose.busy} onClick={() => previewLoose.run(undefined)}>
                Dựng xem thử (bỏ qua quyền)
              </button>
            </div>
            {previewStrict.msg || previewLoose.msg ? (
              <p className="mt-2 text-xs text-slate-600">{previewStrict.msg || previewLoose.msg}</p>
            ) : null}
            {detail.project.has_video ? (
              <video className="mt-3 max-h-80 w-full rounded-xl bg-black" controls src={projectVideoUrl(detail.project.id)} />
            ) : (
              <p className="mt-2 text-xs text-slate-400">Chưa có video. Worker Studio dựng xong thì video hiện ở đây.</p>
            )}
            {detail.project.error ? <p className="mt-2 text-sm text-red-600">{detail.project.error}</p> : null}
          </section>
        </>
      ) : null}
    </div>
  );
}
