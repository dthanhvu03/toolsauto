# TASK-042: Cross-account media publish guard

| Field | Value |
|---|---|
| **ID** | TASK-042 |
| **Plan** | PLAN-041 |
| **Status** | Verified · Phase 1+3 done (chờ commit/archive) |
| **Assignee** | Codex (backend) · Claude Code (UI badge/handoff nếu cần) |
| **Priority** | P1 |
| **Created** | 2026-07-24 |
| **Requested by** | Owner |

## Objective

Chặn cùng một video/media được đăng bởi nhiều account (hoặc tạo job trùng nội dung) — bổ sung lớp ngoài `dedupe_key` hiện tại (chỉ unique trong **1 account**).

## Acceptance Criteria

- [x] Không tạo được job thứ 2 (PENDING/RUNNING/DONE/DRAFT/AI/AWAITING) cùng `content_hash` trên **cùng platform**
- [x] Viral ingest: `viral_material_id` gate + set trên Job
- [x] Manual `create_job` / bulk: hash + assert trước insert
- [x] FAILED không chặn recreate
- [x] Migration `f4a1b2c3d4e5` + partial unique indexes Postgres
- [x] Tests `tests/test_cross_account_media_guard.py` — 4 passed
- [x] UI badge skip dup / job details hash (Phase 3)

## Out of Scope

- Anti-dupe visual ffmpeg (đã có ReupProcessor).
- Topic dedup Threads news (đã có).
- Chặn caption trùng text-only (không media).

## Blockers

- Cần Owner chốt policy: unique theo **platform** hay **global toàn hệ**; cửa sổ thời gian (mãi mãi vs N ngày).
