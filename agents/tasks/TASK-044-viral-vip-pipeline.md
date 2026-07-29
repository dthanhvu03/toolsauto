# TASK-044: Viral VIP pipeline status + retry UX

| Field | Value |
|---|---|
| **ID** | TASK-044 |
| **Plan** | PLAN-043 |
| **Status** | Done · Pending Owner verify |
| **Assignee** | Claude Code |
| **Created** | 2026-07-24 |

## Acceptance

- [x] PROCESSING khi đang xử lý; stale recover
- [x] FAILED dùng ViralStatus; Thử lại trên UI
- [x] process_tries < 3 cho retryable errors
- [x] Counters + ffmpeg banner + cave sticky

## Note

Local thiếu ffmpeg → process bị chặn sớm với message rõ (không spam fail reup).
