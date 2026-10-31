import { Link2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/shared/lib/cn";
import { ghostBtnClass } from "@/shared/ui/controls";
import { PageHeader } from "@/shared/ui/PageHeader";
import { QueryBody } from "@/shared/ui/QueryBody";
import { Toast } from "@/shared/ui/Toast";
import { approveProject, markPosted, rejectProject } from "../api/studioApi";
import { JobsPanel } from "../components/JobsPanel";
import { ProjectCard } from "../components/ProjectCard";
import { UploadBox } from "../components/UploadBox";
import { useAction, useProjects, useSetup } from "../hooks/useStudio";
import { BOARD_COLUMNS } from "../lib/status";
import type { ProjectRow } from "../types/studio.types";

export function StudioBoardPage() {
  const q = useProjects();
  const setup = useSetup();
  const [col, setCol] = useState("review");
  const approve = useAction(
    (p: ProjectRow) => approveProject(p.id).then(() => p.channel_id == null),
    (manual) => (manual ? "Đã duyệt — tải video ở cột «Đã duyệt» để đăng tay." : "Đã duyệt — đang chuyển sang Buffer.")
  );
  const reject = useAction((id: number) => rejectProject(id), "Đã bỏ.");
  const posted = useAction((id: number) => markPosted(id), "Đã đánh dấu đã đăng.");
  // Một chỗ báo chung cho mọi nút trên bảng (duyệt / bỏ / đã đăng / chép caption).
  const [toast, setToast] = useState({ text: "", seq: 0 });
  const say = (text: string) => setToast((t) => ({ text, seq: t.seq + 1 }));
  useEffect(() => void (approve.msg && say(approve.msg)), [approve.seq]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void (reject.msg && say(reject.msg)), [reject.seq]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => void (posted.msg && say(posted.msg)), [posted.seq]); // eslint-disable-line react-hooks/exhaustive-deps
  const d = q.data;
  const column = BOARD_COLUMNS.find((c) => c.key === col) ?? BOARD_COLUMNS[1];
  const items = (d?.projects ?? []).filter((p) => column.statuses.includes(p.status));
  const count = (statuses: string[]) => statuses.reduce((n, s) => n + (d?.counts[s as keyof typeof d.counts] ?? 0), 0);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Studio"
        subtitle={d ? `${count(["REVIEW"])} video chờ duyệt${d.tasks_pending ? ` · ${d.tasks_pending} việc đang chạy` : ""}` : "—"}
      />
      <div className="mt-4 flex flex-col gap-2">
        <UploadBox channels={setup.data?.channels ?? []} />
        <Link to="/app/go/studio-tiktok" className={`${ghostBtnClass} inline-flex w-fit items-center gap-1.5`}>
          <Link2 className="size-4" /> Lấy video từ link TikTok…
        </Link>
      </div>
      <Toast text={toast.text} seq={toast.seq} />
      <JobsPanel hideDone />

      <div className="mt-4 flex gap-1.5 overflow-x-auto pb-1">
        {BOARD_COLUMNS.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => setCol(c.key)}
            className={cn(
              "shrink-0 rounded-full border px-3 py-1.5 text-sm font-medium",
              c.key === col ? "border-indigo-300 bg-indigo-50 text-indigo-800" : "border-slate-200 bg-white text-slate-600"
            )}
          >
            {c.label} <span className="ml-1 tabular-nums text-slate-400">{count(c.statuses)}</span>
          </button>
        ))}
      </div>

      <QueryBody isLoading={q.isLoading} isError={q.isError} loadingText="Đang tải…" errorText="Không tải được Studio (đã chạy alembic upgrade head chưa?)">
        {items.length === 0 ? (
          <p className="mt-8 text-center text-sm text-slate-400">Không có video nào ở «{column.label}».</p>
        ) : (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {items.map((p) => (
              <ProjectCard
                key={p.id}
                p={p}
                busy={approve.busy || reject.busy || posted.busy}
                onApprove={(proj) => approve.run(proj)}
                onReject={(id) => reject.run(id)}
                onPosted={(id) => posted.run(id)}
                onNotice={say}
              />
            ))}
          </div>
        )}
      </QueryBody>
    </div>
  );
}
