import type { ProjectStatus } from "../types/studio.types";

export const STATUS_LABEL: Record<ProjectStatus, string> = {
  DRAFT: "Đang dựng",
  RENDERING: "Đang render",
  RENDERED: "Đã render",
  REVIEW: "Chờ duyệt",
  APPROVED: "Đã duyệt",
  SCHEDULED: "Đã hẹn",
  POSTED: "Đã đăng",
  FAILED: "Lỗi",
  REJECTED: "Đã bỏ",
};

export const STATUS_STYLE: Record<ProjectStatus, string> = {
  DRAFT: "bg-slate-100 text-slate-700",
  RENDERING: "bg-sky-100 text-sky-800",
  RENDERED: "bg-sky-100 text-sky-800",
  REVIEW: "bg-amber-100 text-amber-900",
  APPROVED: "bg-indigo-100 text-indigo-800",
  SCHEDULED: "bg-emerald-100 text-emerald-800",
  POSTED: "bg-emerald-600 text-white",
  FAILED: "bg-red-100 text-red-800",
  REJECTED: "bg-slate-200 text-slate-500",
};

/** Cột bảng duyệt — thứ tự đúng hành trình của một video. */
export const BOARD_COLUMNS: { key: string; label: string; statuses: ProjectStatus[] }[] = [
  { key: "making", label: "Đang làm", statuses: ["DRAFT", "RENDERING", "RENDERED"] },
  { key: "review", label: "Chờ duyệt", statuses: ["REVIEW"] },
  { key: "approved", label: "Đã duyệt", statuses: ["APPROVED"] },
  { key: "scheduled", label: "Đã hẹn", statuses: ["SCHEDULED"] },
  { key: "posted", label: "Đã đăng", statuses: ["POSTED"] },
  { key: "failed", label: "Lỗi / bỏ", statuses: ["FAILED", "REJECTED"] },
];

export function mmss(sec?: number | null): string {
  const s = Math.max(0, Math.round(sec ?? 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export const round2 = (x: number) => Math.round(x * 100) / 100;
