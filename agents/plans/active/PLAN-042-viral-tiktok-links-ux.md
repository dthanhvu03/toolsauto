# PLAN-042: Viral ↔ TikTok Links role split + Smart bridge

| Field | Value |
|---|---|
| **ID** | PLAN-042 |
| **Task** | TASK-043 |
| **Status** | Done · Pending Owner verify |
| **Executor** | Claude Code |
| **Created** | 2026-07-24 |

## Problem

Hai trang Facebook silo chồng chéo; video kẹt `NEW` vì local chỉ chạy Web → không lộ Smart (reup/job/AI).

## Scope (Owner chọn A+C) — DONE

1. **Nguồn TikTok** = kênh đối thủ / inventory nguồn (bỏ tab Viral trùng).
2. **Nội dung viral** = pipeline: Quét + **Xử lý NEW** + badge job/reup + banner khi pipeline idle.
3. Backend: `POST /viral/process-new`, `POST /viral/{id}/process` gọi `ViralProcessorService.download_and_queue`.
4. Enrich table: `has_reup`, latest `job_id`/`job_status`/affiliate flag.

## Verify notes

- Banner `show_worker_banner=True` khi 50 NEW / 0 jobs viral
- process 1 NEW: download OK → reup FAIL thiếu ffprobe (blocker môi trường, không phải UX)

## Out of scope

- PM2 / start Maintenance trên Windows
- Gộp 2 route thành 1 trang
- Đổi logic download/reup/publish

## Verify

- `/app/tiktok-links` không còn tab Viral; có link sang `/app/viral`
- `/app/viral` có CTA xử lý; sau process 1 NEW → status đổi / có job badge hoặc FAILED rõ
- force-scan không phá `#viral-table` (toast + refresh)
