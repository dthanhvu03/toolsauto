# TASK-049 — Local auto-coordination (Supervisor + Smart gates)

## Plan

PLAN-048

## Executor

Cursor Agent

## Acceptance

- [x] `manage.py stack` / `start.ps1 -Stack` giữ web + maintenance + publisher (singleton)
- [x] Claim gate dùng `chrome_toolsauto_count` (không block vì Chrome cá nhân)
- [x] Orphan ToolsAuto browser purge trên Windows
- [x] Không auto-approve DRAFT
- [x] Handoff + operator training cập nhật

## Notes

Smoke: total Chrome 64, toolsauto 0, `resource_blocks_claim=False`.
