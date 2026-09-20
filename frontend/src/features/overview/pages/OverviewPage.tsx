import { ListTodo, Server } from "lucide-react";
import { PageHeader } from "@/shared/ui/PageHeader";
import { QueryBody } from "@/shared/ui/QueryBody";
import { CockpitAlerts } from "../components/CockpitAlerts";
import { QuickLink } from "../components/QuickLink";
import { StatCard } from "../components/StatCard";
import { useOverview } from "../hooks/useOverview";
import type { OverviewOps } from "../types/overview.types";

function workerTone(ops: OverviewOps): "ok" | "warn" | "bad" {
  const age = ops.worker.heartbeat_age_seconds;
  if (ops.worker.status === "RUNNING" && (age == null || age > 120)) return "bad";
  if (ops.worker.status === "RUNNING") return "ok";
  if (ops.worker.status === "PAUSE" || ops.worker.status === "SAFE") return "warn";
  return "bad";
}

function workerHint(ops: OverviewOps): string {
  const parts: string[] = [];
  const age = ops.worker.heartbeat_age_seconds;
  if (age == null) parts.push("chưa có heartbeat");
  else parts.push(`heartbeat ${age}s`);
  if (ops.worker.current_job_id) parts.push(`job #${ops.worker.current_job_id}`);
  if (ops.worker.safe_mode && ops.worker.status !== "SAFE") parts.push("SAFE MODE");
  return parts.join(" · ");
}

export function OverviewPage() {
  const q = useOverview();
  const d = q.data;
  const ops = d?.ops;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Tổng quan" subtitle="Máy còn sống không — 1 màn hình" />
      <QueryBody
        isLoading={q.isLoading}
        isError={q.isError || (!q.isLoading && !d)}
        loadingText="Đang tải tổng quan…"
        errorText="Không tải được /api/admin/overview. Kiểm tra đăng nhập / FastAPI."
      >
        {d && ops ? (
          <>
            <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <StatCard
                label="Worker"
                value={ops.worker.status}
                hint={workerHint(ops)}
                tone={workerTone(ops)}
              />
              <StatCard
                label="Ổ đĩa trống"
                value={`${ops.disk.free_gb} GB`}
                hint={`ngưỡng pause ${ops.disk.pause_below_gb} GB · ${Math.round(ops.disk.pct)}% · ${ops.disk.label}`}
                tone={ops.disk.below_pause ? "bad" : ops.disk.free_gb < 5 ? "warn" : "ok"}
              />
              <StatCard
                label="Gemini circuit"
                value={ops.gemini_circuit.open ? "Mở" : "Đóng"}
                hint={ops.gemini_circuit.open ? "AI job đang bị chặn" : "Gemini RPA bình thường"}
                tone={ops.gemini_circuit.open ? "bad" : "ok"}
              />
              <StatCard
                label="Checkpoint FB"
                value={String(ops.checkpoint.count)}
                hint={`${ops.checkpoint.accounts ?? 0} acc · ${ops.checkpoint.jobs ?? 0} job · ${ops.checkpoint.sessions ?? 0} phiên`}
                tone={ops.checkpoint.count > 0 ? "bad" : "ok"}
              />
              <StatCard
                label="Job FAILED"
                value={String(ops.failed_jobs.count)}
                hint="3 mới nhất bên dưới"
                tone={ops.failed_jobs.count > 0 ? "warn" : "ok"}
              />
            </div>

            <CockpitAlerts failed={ops.failed_jobs.latest} checkpoints={ops.checkpoint.latest} />

            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <QuickLink
                to="/app/go/jobs"
                title="Hàng đợi job"
                desc="Xem FAILED / CHECKPOINT / retry"
                icon={ListTodo}
              />
              <QuickLink
                to="/app/go/syspanel"
                title="Panel hệ thống"
                desc="Pause / resume / safe mode worker"
                icon={Server}
              />
            </div>
          </>
        ) : d ? (
          <p className="mt-6 text-sm text-slate-400">API overview chưa có dữ liệu cockpit.</p>
        ) : null}
      </QueryBody>
    </div>
  );
}
