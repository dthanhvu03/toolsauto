# PLAN-043: Viral page VIP — PROCESSING, retry, pipeline UX

| Field | Value |
|---|---|
| **ID** | PLAN-043 |
| **Task** | TASK-044 |
| **Status** | Done · Pending Owner verify |
| **Executor** | Claude Code |
| **Created** | 2026-07-24 |

## Scope

1. `ViralStatus.PROCESSING` + recover stale PROCESSING (>30m → NEW).
2. Fix `_mark_material_failed` → `ViralStatus.FAILED` (không dùng JobStatus).
3. `process_tries` + retry: manual **Thử lại**; Maintenance/auto batch chỉ retry FAILED retryable với tries < 3.
4. UI VIP: status counters, badge PROCESSING, nút Thử lại, banner ffmpeg, filter PROCESSING, sticky bar cave tokens.

## Out of scope

- Cài ffmpeg hệ thống hộ Owner
- Đổi publish / AI caption logic
- Gộp trang TikTok Links
