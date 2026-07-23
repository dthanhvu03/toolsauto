# TASK-040: Tách UX Settings vs AI Studio (prompt single source)

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-040 |
| **Status** | Verified · **Archived** 2026-07-23 |
| **Priority** | P2 |
| **Owner** | Antigravity / User intake |
| **Executor** | Claude Code |
| **Related Plan** | PLAN-038 |
| **Created** | 2026-07-22 |
| **Updated** | 2026-07-22 |

---

## Objective

Loại bỏ trùng lặp chỉnh sửa prompt giữa **Cài đặt** và **AI Studio**: mọi template text (persona, hook, fallback, Threads) chỉ sửa trên AI Studio; Settings giữ tham số vận hành AI.

---

## Scope

- Thực hiện PLAN-038 Phase 1–5 (metadata, dashboard context, templates, AI Studio, tests).
- Cập nhật handoff khi Verified.

## Out of Scope

- Backend worker/pipeline refactor.
- Sandbox Threads.
- Commit/push (trừ khi user yêu cầu).

---

## Blockers

- Không có.

---

## Acceptance Criteria

- [x] Trên `/app/settings`, không render input cho: `ai.fallback_*`, `ai.prompt.*`, `THREADS_AI_PROMPT`.
- [x] Section **AI & Whisper** vẫn hiển thị Whisper + giới hạn số (max caption, hashtag…).
- [x] `/app/ai-studio` có mục **Platforms** cho `THREADS_AI_PROMPT`.
- [x] Deeplink `/app/ai-studio?key=THREADS_AI_PROMPT` chọn đúng template (JS on load).
- [x] `pytest tests/test_settings_ui_surface.py` pass.
- [x] Không đổi format API `/app/settings/bulk-save` và `/app/ai-studio/save`.

---

## Execution Notes

- [ ] Phase 1: `SettingSpec.studio_only` + helpers
- [ ] Phase 2: `get_settings_context` + `app_settings.html`
- [ ] Phase 3: AI Studio Threads + deeplink
- [ ] Phase 4: Nav/copy
- [ ] Phase 5: Test + manual checklist

---

## Verification Proof

```
venv\Scripts\python.exe -m pytest tests\test_settings_ui_surface.py -q
... 3 passed in 0.35s
venv\Scripts\python.exe -c "from app.main import app; print('OK')"
OK
```

---

## Status History

| Date | Status | Note |
|---|---|---|
| 2026-07-22 | Planned | PLAN-038 created; chờ Executor |
