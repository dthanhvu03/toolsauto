# TASK-022: Split models.py into Domain Packages

**Status:** Done  
**Priority:** P2  
**Type:** Refactor  
**Owner:** Claude Code  
**Created:** 2026-04-26  
**Reference:** DECISION-006 §2.3, Vote 3/3 đồng ý  
**Blocked by:** TASK-021 (cần test baseline trước khi refactor)

---

## Objective
Tách `app/database/models.py` (829 LOC, ~15 models) thành package `app/database/models/` theo domain, giữ backward-compatible qua `__init__.py` re-export.

## Acceptance Criteria
- [x] `app/database/models/` là package với các file: jobs.py, accounts.py, viral.py, incidents.py, threads.py, settings.py, compliance.py
- [x] `__init__.py` re-export tất cả model (backward-compatible)
- [x] Mọi relationship dùng string: `relationship("Job")`, `ForeignKey("accounts.id")`
- [x] `alembic check` pass — không tạo migration mới
- [x] Import smoke test: `from app.database.models import Job, Account, IncidentLog` OK
- [x] Existing tests từ TASK-021 vẫn pass

## Status History
- 2026-04-26: `Planned` — Created by Antigravity
- 2026-04-26: `Done` — Models split successfully by Claude Code, verified by Anti.
