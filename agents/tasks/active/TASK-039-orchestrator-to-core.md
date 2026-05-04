# TASK-039 — Move orchestrator.py to core/ + fix viral_intake legacy import

**Status**: Planned (chờ Anti sign-off — Anti đã propose từ Step 23 Verdict B)
**Plan**: [PLAN-037](../../plans/active/PLAN-037-feature-based-module-refactor.md) (boundary debt từ Phase 3 Step 23)
**Executor**: Codex (file move + import update + boundary lint)
**Verifier**: Claude Code

> **Gate**: KHÔNG execute trước khi Anti sign-off TASK này riêng. Có thể làm song song hoặc sau TASK-038.

## Background

Phase 3 Step 23 carved viral_intake feature. Phát sinh circular dependency qua shim:
- `features/viral_intake/processor.py` import `app.services.content.orchestrator` (legacy path → shim → `app/services/content/orchestrator.py`).
- `app/services/content/orchestrator.py` import viral_processor → shim → `features/viral_intake/processor.py`.

Hiện tại work qua shim runtime, nhưng:
1. Vi phạm ADR-007: feature import legacy `app.services.content.X`.
2. Sẽ phá vỡ ngay khi Phase 4 (PLAN-037 §"Phase 4") tách orchestrator vì 2 module sẽ trực tiếp circular.

**Anti's revised approach** (khác PLAN-037 §"Phase 4" gốc — gốc nói split orchestrator thành viral_intake/orchestrator + facebook_publisher/reup_pipeline):

**Move orchestrator nguyên vẹn vào `app/core/orchestrator/`** (hoặc `app/core/content/orchestrator.py`). orchestrator là cross-feature pipeline (Threads + FB content gen), thuộc core infrastructure. Không tách như PLAN gốc — đơn giản hơn + đúng boundary hơn.

## Goal

Move `app/services/content/orchestrator.py` → `app/core/orchestrator.py` (flat module). Update mọi callsite + shim.

Sau đó: viral_intake/processor + features khác chỉ import `app.core.orchestrator`, không còn legacy `app.services.content.X`.

## Scope

**Single file move**: `app/services/content/orchestrator.py` (951 LOC) → `app/core/orchestrator.py`.

**Out of scope**:
- Move các file content/ khác (media_processor, video_protector, yt_dlp_path) — sẽ Phase 4 hoặc remain.
- Tách orchestrator thành 2 module (PLAN-037 §"Phase 4" gốc) — Anti revised approach: keep nguyên, move sang core/.
- Đổi business logic / contract.

## Steps

1. [ ] Pre-flight: worktree clean, TASK-038 (workflow_registry) ideally done trước (clearer state).
2. [ ] Plain mv: `app/services/content/orchestrator.py` → `app/core/orchestrator.py`.
3. [ ] `git add -A`.
4. [ ] Update import (Python regex script):
   - `from app.services.content.orchestrator` → `from app.core.orchestrator`
   - `from app.services.content_orchestrator` → `from app.core.orchestrator`
   - `import app.services.content.orchestrator` → `import app.core.orchestrator`
5. [ ] Update shim `app/services/__init__.py` _ALIASES:
   - `"content_orchestrator": "content.orchestrator"` → `"app.core.orchestrator"`
6. [ ] Smoke gates:
   - py_compile PASS, app import 207, pytest 77/11.
   - ORCH_OK: `from app.core.orchestrator import ContentOrchestrator, OutputContractViolation`.
   - ORCH_SHIM_OK: legacy `from app.services.content_orchestrator import ContentOrchestrator`.
   - **Worker import**: `import workers.ai_generator` (uses orchestrator).
   - **Threads news**: `from app.features.threads.service.threads_news import process_news_to_threads`.
7. [ ] Verify ADR-007: viral_intake/processor không còn import `app.services.content.X`, chỉ import `app.core.X`.
8. [ ] 1 commit: `refactor(boundary-debt): move orchestrator → app/core/ (resolve viral_intake legacy import)`.
9. [ ] Update TASK-039 [x] với commit hash.
10. [ ] Claude Code verify + handoff entry.

## Files Touched (estimate)

- 1 file move (orchestrator.py 951 LOC).
- ~5-7 callsite import update:
  - app/core/ai/service.py
  - app/features/threads/service/threads_news.py
  - app/features/viral_intake/processor.py (key fix)
  - workers/ai_generator.py (2 inline imports)
  - workers/maintenance.py (nếu có)
- 1 shim alias update.

## Acceptance Criteria

1. [ ] py_compile PASS, ROUTES 207, pytest 77/11.
2. [ ] features/viral_intake/processor.py grep zero `from app.services.content`.
3. [ ] features/threads/service/threads_news.py grep zero `from app.services.content_orchestrator`.
4. [ ] Shim backwards-compat: `from app.services.content_orchestrator` work cho legacy callsites trong scripts/archive/.
5. [ ] Worker integration: ai_generator + maintenance + threads workers vẫn import OK.
6. [ ] git diff --stat: 1 rename + import update + 1 alias.

## Risks

- orchestrator là content generation pipeline central → smoke FAIL = AI generation broken.
- Phase 4 trong PLAN-037 vốn nói split orchestrator. Anti revised: KHÔNG split, move whole. Reasoning: orchestrator là cross-feature shared service, thuộc core. Tách 2 phần (viral_intake + facebook_publisher) làm phức tạp + duplicate logic.
- Order với TASK-038: ưu tiên TASK-038 trước (workflow_registry là dispatcher input, smaller scope), TASK-039 sau (orchestrator size lớn hơn).

## Coordination với PLAN-037 Phase 4

PLAN-037 §"Phase 4" (gốc) nói "Tách orchestrator.py thành viral_intake/orchestrator.py + facebook_publisher/reup_pipeline.py". TASK-039 thay thế Phase 4 task này với approach đơn giản hơn (move whole sang core/).

Sau TASK-039 done, Phase 4 effective = COMPLETED. Có thể skip Phase 4 trong PLAN-037 hoặc rename Phase 4 thành "Cleanup content/" (move remaining media_processor, video_protector, yt_dlp_path nếu cần — tuỳ Anti decide).
