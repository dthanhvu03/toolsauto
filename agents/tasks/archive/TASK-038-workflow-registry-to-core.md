# TASK-038 — Move workflow_registry from features/system_panel/ to core/

**Status**: Planned (chờ Anti sign-off — Anti đã pre-flag từ Step 20 Verdict B)
**Plan**: [PLAN-037](../../plans/active/PLAN-037-feature-based-module-refactor.md) (boundary debt từ Phase 3 Step 20)
**Executor**: Codex (file move + import update)
**Verifier**: Claude Code

> **Gate**: KHÔNG execute trước khi Anti sign-off TASK này riêng. Đây là follow-up từ PLAN-037 Step 20 Verdict B.

## Background

Phase 3 Step 20 carved `system_panel` feature, gộp `workflow_registry.py` vào `app/features/system_panel/`. Anti review Verdict B flag: vi phạm ADR-007 import rule "features → features không được" — vì `dispatcher.py` + `features/threads/adapter` + `features/tiktok/adapter` + `features/facebook_publisher/adapter` (sau Step 24) đều import workflow_registry → tạo features → features dependency.

`workflow_registry` thực chất là CORE infrastructure (DB-driven adapter loading + selector cache + preset descriptions), được dispatcher central use. Phải nằm trong `app/core/`, không phải feature.

## Goal

Move `app/features/system_panel/workflow_registry.py` → `app/core/workflow_registry/` (hoặc `app/core/workflow/registry.py`).

Để `system_panel` còn lại 2 file (`service.py` + `router.py` + `__init__.py`) — vẫn là feature dashboard nhưng không mang shared infra nữa.

**KHÔNG đổi behavior**, chỉ đổi cấu trúc + import path.

## Scope

**Single file move**: `app/features/system_panel/workflow_registry.py` → `app/core/workflow_registry/__init__.py` (single-module package) hoặc `app/core/workflow_registry.py` (flat).

**Out of scope**:
- Đổi business logic / SQL / cache strategy.
- Move `system_panel/service.py` hoặc `router.py`.
- Refactor naming `WorkflowRegistry` class.

## Steps

1. [ ] Pre-flight: confirm worktree clean, alembic head c7d9e1f2a3b4.
2. [ ] Plain mv: `app/features/system_panel/workflow_registry.py` → `app/core/workflow_registry.py` (flat module, đơn giản hơn package).
3. [ ] `git add -A`.
4. [ ] Update import (Python regex script):
   - `from app.features.system_panel.workflow_registry` → `from app.core.workflow_registry`
   - `import app.features.system_panel.workflow_registry` → `import app.core.workflow_registry`
5. [ ] Update shim `app/services/__init__.py` _ALIASES:
   - `"workflow_registry": "app.features.system_panel.workflow_registry"` → `"app.core.workflow_registry"`
6. [ ] Smoke gates:
   - py_compile PASS
   - app import 207 routes
   - pytest 77/11 baseline
   - WR_OK + WR_SHIM_OK + WR_SHIM_IDENTITY_OK
   - **DISPATCHER_FB** (critical) — `get_adapter(Platform.FACEBOOK)` không error.
7. [ ] Verify ADR-007: features/* không còn import features/system_panel/workflow_registry, chỉ import core/workflow_registry.
8. [ ] 1 commit: `refactor(boundary-debt): move workflow_registry → app/core/ (ADR-007 compliance)`.
9. [ ] Update TASK-038 [x] với commit hash.
10. [ ] Claude Code verify + handoff entry.

## Files Touched (estimate)

- 1 file move (workflow_registry.py).
- ~13 callsite import update (dispatcher, FB adapter, generic adapter, common/locator, config_service, mcp_server.py, threads, tiktok adapters).
- 1 shim alias update.

## Acceptance Criteria

1. [ ] py_compile PASS, ROUTES 207, pytest 77/11.
2. [ ] DISPATCHER_FB + DISPATCHER_THREADS load adapter qua workflow_registry mới.
3. [ ] `app/features/system_panel/` còn 2 file (service.py + router.py + __init__.py), KHÔNG có workflow_registry.
4. [ ] grep `from app.features.system_panel.workflow_registry` → empty (mọi callsite đã chuyển).
5. [ ] Shim backwards-compat: `from app.services.workflow_registry` vẫn work.
6. [ ] git diff --stat: 1 rename + import update + 1 alias.

## Risks

- workflow_registry là core path đầu vào dispatcher → smoke FAIL = pipeline broken.
- Migrate khi VPS đang chạy → restart workers cần thiết (CI/CD auto-restart sau pull).
