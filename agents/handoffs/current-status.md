# Current Status

## System State

- Local: **http://127.0.0.1:8002**
- FB Reels harden: unify `/reels/` URL + smart upload/Next waits (working tree → commit)

## Done This Session [2026-07-23]

- Ops harden `f6c789c` (poll/checkpoint/daily skip)
- Reels patch: `reels_tab_url` dùng chung pre_scan+verify; `wait_until_upload_ready` / `wait_until_next_enabled`

## Next Action

1. Owner chạy 1 job Reels thật → DONE + post_url
2. Nếu fail: checklist `logs/fb/job_*`
