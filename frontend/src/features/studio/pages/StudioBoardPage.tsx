import { useState } from "react";
import { cn } from "@/shared/lib/cn";
import { PageHeader } from "@/shared/ui/PageHeader";
import { QueryBody } from "@/shared/ui/QueryBody";
import { Toast } from "@/shared/ui/Toast";
import { approveProject, rejectProject } from "../api/studioApi";
import { ProjectCard } from "../components/ProjectCard";
import { UploadBox } from "../components/UploadBox";
import { useAction, useProjects, useSetup } from "../hooks/useStudio";
import { BOARD_COLUMNS } from "../lib/status";

export function StudioBoardPage() {
  const q = useProjects();
  const setup = useSetup();
  const [col, setCol] = useState("review");
  const approve = useAction((id: number) => approveProject(id), "Đã duyệt — đang chuyển sang Buffer.");
  const reject = useAction((id: number) => rejectProject(id), "Đã bỏ.");
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
      <div className="mt-4">
        <UploadBox channels={setup.data?.channels ?? []} />
      </div>
      <Toast text={approve.seq >= reject.seq ? approve.msg : reject.msg} seq={approve.seq + reject.seq} />
      {d?.tasks_pending ? (
        <p className="mt-3 flex items-center gap-2 rounded-lg bg-sky-50 px-3 py-2 text-sm text-sky-900">
          <span className="size-2 animate-pulse rounded-full bg-sky-500" />
          Đang xử lý {d.tasks_pending} bước (nhận file → phân tích lời thoại / cảnh → dựng → render → caption). Video hiện ở
          «Chờ duyệt» khi xong, thường 1–3 phút mỗi video — trang tự cập nhật.
        </p>
      ) : null}

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
                busy={approve.busy || reject.busy}
                onApprove={(id) => approve.run(id)}
                onReject={(id) => reject.run(id)}
              />
            ))}
          </div>
        )}
      </QueryBody>
    </div>
  );
}
