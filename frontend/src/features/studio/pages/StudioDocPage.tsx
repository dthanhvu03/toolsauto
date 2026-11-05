import { Film, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ghostBtnClass, inputClass, primaryBtnClass, selectClass } from "@/shared/ui/controls";
import { PageHeader } from "@/shared/ui/PageHeader";
import { Toast } from "@/shared/ui/Toast";
import * as api from "../api/studioApi";
import { useAction, useJobs } from "../hooks/useStudio";
import { projectVideoUrl } from "../api/studioApi";

type Shot = {
  shot_id: string;
  beat_id: string;
  start_ms: number;
  end_ms: number;
  narration: string;
  motion: string;
  status: string;
  selected: null | {
    asset_id: number;
    credit: string;
    license: string;
    rights_status: string;
    illustration: boolean;
    source_page: string;
  };
};

type DocDetail = {
  project: { id: number; status: string; has_video: boolean; editable: boolean; error: string | null };
  audio: { id: number | null; title: string | null; duration: number | null };
  doc: {
    duration_ms: number;
    preview_end_ms: number;
    transcript: { start_ms: number; end_ms: number; raw_text: string; reviewed_text: string }[];
    beats: { beat_id: string; summary: string; fact_status: string }[];
    shots: Shot[];
  };
  rights_gate: { ok: boolean; blockers: string[]; can_export: boolean };
};

function fmt(ms: number) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function StudioDocPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [taskId, setTaskId] = useState<number | null>(null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DocDetail | null>(null);
  const [shotId, setShotId] = useState("");
  const [rights, setRights] = useState("RIGHTS_VERIFIED");
  const [license, setLicense] = useState("owned");
  const [credit, setCredit] = useState("");
  const [illustration, setIllustration] = useState(false);
  const [toast, setToast] = useState({ text: "", seq: 0 });
  const say = (text: string) => setToast((t) => ({ text, seq: t.seq + 1 }));

  const jobs = useJobs(taskId ? [taskId] : []);
  const tracked = useMemo(() => (jobs.data?.jobs ?? []).find((j) => j.id === taskId), [jobs.data, taskId]);

  useEffect(() => {
    const pid = tracked?.project_id;
    if (pid && pid !== projectId) setProjectId(pid);
  }, [tracked?.project_id, projectId]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    const load = () =>
      api.fetchDocProject(projectId).then((raw) => {
        if (!cancelled) {
          const d = raw as DocDetail;
          setDetail(d);
          if (!shotId && d.doc?.shots?.[0]) setShotId(d.doc.shots[0].shot_id);
        }
      }).catch((e) => say(String(e.message || e)));
    void load();
    const t = setInterval(() => void load(), 4000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = useAction(
    async (file: File) => {
      const res = await api.uploadDocAudio(file);
      setTaskId(res.task_id);
      setProjectId(null);
      setDetail(null);
      return res;
    },
    "Đã nhận audio — đang chạy intake → analyze → doc_plan.",
    [["studio-jobs"]]
  );

  const saveTranscript = useAction(
    async () => {
      if (!detail || !projectId) throw new Error("chưa có dự án");
      return api.saveDocTranscript(
        projectId,
        detail.doc.transcript.map((s) => ({
          start_ms: s.start_ms,
          end_ms: s.end_ms,
          raw_text: s.raw_text,
          reviewed_text: s.reviewed_text,
        }))
      ).then((d) => {
        setDetail(d as DocDetail);
      });
    },
    "Đã lưu transcript reviewed."
  );

  const attach = useAction(
    async (file: File) => {
      if (!projectId || !shotId) throw new Error("chọn shot trước");
      const d = await api.attachDocImage(projectId, shotId, file, {
        credit,
        license,
        rights_status: rights,
        illustration,
        source_page: "",
        proof_note: illustration ? "ảnh minh họa POC" : "upload tay POC",
      });
      setDetail(d as DocDetail);
    },
    "Đã gắn ảnh vào shot."
  );

  const previewStrict = useAction(
    async () => {
      if (!projectId) throw new Error("chưa có dự án");
      return api.requestDocPreview(projectId, true);
    },
    "Đã xếp render (có kiểm quyền)."
  );

  const previewLoose = useAction(
    async () => {
      if (!projectId) throw new Error("chưa có dự án");
      return api.requestDocPreview(projectId, false);
    },
    "Đã xếp render thử (cho phép thiếu quyền — chỉ POC)."
  );

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Audio → Documentary (POC)"
        subtitle="Phase 0: transcript · beats/shots · upload ảnh + quyền · preview 30–60s · khóa export khi RIGHTS_UNKNOWN"
      />
      <Toast text={toast.text} seq={toast.seq} />
      <p className="mt-2 text-sm text-slate-500">
        <Link to="/app/go/studio" className="underline">← Studio</Link>
        {" · "}Không gọi API tìm ảnh / không mua license trong POC.
      </p>

      <section className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800">1. Upload audio</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2">
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
            {projectId ? ` · dự án #${projectId}` : " · chờ doc_plan tạo dự án…"}
          </p>
        ) : null}
        {upload.msg ? <p className="mt-1 text-xs text-emerald-700">{upload.msg}</p> : null}
      </section>

      {detail ? (
        <>
          <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">
              2. Transcript ({detail.doc.transcript.length} đoạn) · audio {fmt(detail.doc.duration_ms)}
            </h2>
            <div className="mt-2 max-h-56 space-y-2 overflow-y-auto">
              {detail.doc.transcript.length === 0 ? (
                <p className="text-sm text-slate-400">Chưa có lời (fixture tone / Whisper trống). Có thể thêm tay sau.</p>
              ) : (
                detail.doc.transcript.map((seg, i) => (
                  <div key={`${seg.start_ms}-${i}`} className="grid gap-1 rounded-lg bg-slate-50 p-2 text-sm sm:grid-cols-[4.5rem_1fr_1fr]">
                    <span className="tabular-nums text-slate-500">{fmt(seg.start_ms)}</span>
                    <input
                      className={inputClass}
                      value={seg.raw_text}
                      readOnly
                      title="raw (máy)"
                    />
                    <input
                      className={inputClass}
                      value={seg.reviewed_text}
                      onChange={(e) => {
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
              Lưu bản reviewed
            </button>
            {saveTranscript.msg ? <p className="mt-1 text-xs text-slate-600">{saveTranscript.msg}</p> : null}
          </section>

          <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">
              3. Shots ({detail.doc.shots.length}) · beats {detail.doc.beats.length}
            </h2>
            <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-sm">
              {detail.doc.shots.slice(0, 40).map((s) => (
                <li key={s.shot_id}>
                  <button
                    type="button"
                    className={`w-full rounded-lg px-2 py-1.5 text-left ${shotId === s.shot_id ? "bg-indigo-50 text-indigo-900" : "hover:bg-slate-50"}`}
                    onClick={() => setShotId(s.shot_id)}
                  >
                    <span className="font-medium">{s.shot_id}</span>{" "}
                    <span className="text-slate-500">{fmt(s.start_ms)}–{fmt(s.end_ms)}</span>{" "}
                    <span className="text-slate-400">{s.motion}</span>
                    {s.selected ? (
                      <span className="ml-1 text-emerald-700">· #{s.selected.asset_id} · {s.selected.rights_status}</span>
                    ) : (
                      <span className="ml-1 text-amber-700">· chưa ảnh</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>

            <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3">
              <label className="text-xs text-slate-600">
                Shot
                <select className={`${selectClass} mt-1 block`} value={shotId} onChange={(e) => setShotId(e.target.value)}>
                  {detail.doc.shots.map((s) => (
                    <option key={s.shot_id} value={s.shot_id}>{s.shot_id}</option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-slate-600">
                Quyền
                <select className={`${selectClass} mt-1 block`} value={rights} onChange={(e) => setRights(e.target.value)}>
                  <option value="RIGHTS_VERIFIED">RIGHTS_VERIFIED</option>
                  <option value="APPROVED">APPROVED</option>
                  <option value="RIGHTS_UNKNOWN">RIGHTS_UNKNOWN</option>
                  <option value="RIGHTS_RESTRICTED">RIGHTS_RESTRICTED</option>
                </select>
              </label>
              <label className="text-xs text-slate-600">
                License
                <input className={`${inputClass} mt-1 block w-36`} value={license} onChange={(e) => setLicense(e.target.value)} />
              </label>
              <label className="text-xs text-slate-600">
                Credit
                <input className={`${inputClass} mt-1 block w-36`} value={credit} onChange={(e) => setCredit(e.target.value)} />
              </label>
              <label className="flex items-center gap-1.5 text-xs text-slate-600">
                <input type="checkbox" checked={illustration} onChange={(e) => setIllustration(e.target.checked)} />
                Minh họa
              </label>
              <label className={`${ghostBtnClass} cursor-pointer`}>
                Gắn ảnh…
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) attach.run(f);
                    e.target.value = "";
                  }}
                />
              </label>
            </div>
            {attach.msg ? <p className="mt-2 text-xs text-slate-600">{attach.msg}</p> : null}
          </section>

          <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-800">4. Preview &amp; QC quyền</h2>
            <div className={`mt-2 rounded-lg px-3 py-2 text-sm ${detail.rights_gate.ok ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-950"}`}>
              {detail.rights_gate.ok
                ? "Đủ quyền trong cửa sổ preview — có thể xuất/render nghiêm."
                : `Khóa export: ${detail.rights_gate.blockers.slice(0, 5).join(" · ")}${detail.rights_gate.blockers.length > 5 ? "…" : ""}`}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                className={primaryBtnClass}
                disabled={previewStrict.busy}
                onClick={() => previewStrict.run(undefined)}
              >
                <Film className="mr-1 inline size-4" /> Render (khóa quyền)
              </button>
              <button
                type="button"
                className={ghostBtnClass}
                disabled={previewLoose.busy}
                onClick={() => previewLoose.run(undefined)}
              >
                Render thử POC (bỏ qua quyền)
              </button>
            </div>
            {(previewStrict.msg || previewLoose.msg) ? (
              <p className="mt-2 text-xs text-slate-600">{previewStrict.msg || previewLoose.msg}</p>
            ) : null}
            {detail.project.has_video ? (
              <video className="mt-3 max-h-80 w-full rounded-xl bg-black" controls src={projectVideoUrl(detail.project.id)} />
            ) : (
              <p className="mt-2 text-xs text-slate-400">Chưa có file render. Sau khi worker xong, video hiện ở đây.</p>
            )}
            {detail.project.error ? <p className="mt-2 text-sm text-red-600">{detail.project.error}</p> : null}
          </section>
        </>
      ) : null}
    </div>
  );
}
