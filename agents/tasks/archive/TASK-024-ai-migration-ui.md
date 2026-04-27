# TASK-024: Migrate AI Callers & UI Fallback Surface

**Status:** Done  
**Priority:** P3  
**Type:** Refactor / UX  
**Owner:** Claude Code  
**Created:** 2026-04-26  
**Reference:** ADR-006, TASK-023

---

## Objective
Chuyển đổi toàn bộ các caller đang dùng `GeminiAPIService` (legacy) sang dùng `AICaptionPipeline` thống nhất, đồng thời hiển thị trạng thái Fallback trên UI/Telegram.

## Acceptance Criteria
- [x] Refactor `workers/content_orchestrator.py`: text path đã được pipeline cover qua native fallback. **Vision path (`ask_with_file`) giữ tạm** vì pipeline chưa có native vision fallback — đã ghi rõ trong PLAN-022 §6.4 và đề xuất follow-up TASK-025/026.
- [x] Refactor `workers/ai_reporter.py`: dùng `meta["fallback_used"]` để thêm header cảnh báo Telegram.
- [x] UI Dashboard (`/app/logs/ai-report/live`): badge yellow "FALLBACK MODE" + meta line đầy đủ (provider/model/fallback_used/generated_at).
- [x] Telegram: header `<i>⚠️ Dự phòng: Gemini Native (model=..., 9Router fail_reason=...)</i>`.
- [x] `app/services/gemini_api.py` được mark DEPRECATED (module-level `DeprecationWarning` + docstring).

## Status History
- 2026-04-26: `New` — Created by Antigravity
- 2026-04-27: `Done` — Phase 2 migration + UI surface hoàn tất, Anti APPROVED tại PLAN-022 Sign-off Gate.
