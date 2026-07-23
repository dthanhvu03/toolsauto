# PLAN-038: Tách vai Settings vs AI Studio (single source of truth cho prompt)

| Field | Value |
|---|---|
| **Status** | Done (2026-07-22) · **Archived** 2026-07-23 |
| **Priority** | P2 |
| **Executor** | Claude Code (UX + metadata filter); Codex chỉ nếu cần sửa validation bulk-save |
| **Related Task** | TASK-040 |
| **Created** | 2026-07-22 |

---

## Goal

Người vận hành chỉ sửa **mọi prompt / template text** trên **AI Studio**; **Settings** chỉ còn runtime số, toggle, env và giới hạn AI (Whisper, max caption…). Không đổi schema DB, không đổi behavior pipeline/worker.

---

## Context (hiện trạng)

| Key / nhóm | Settings UI | AI Studio UI | Ghi chú |
|---|---|---|---|
| `ai.prompt.*` (personas + configs) | Ẩn bằng filter template section | Có | Đã tách một phần |
| `ai.fallback_caption_pool`, `ai.fallback_hashtag_pool` | **AI & Whisper** (input) | **Configs** (editor) | **Trùng** |
| `THREADS_AI_PROMPT` | **Threads Auto** | Không | Prompt nằm lệch chỗ |
| Whisper, `ai.max_*`, `MAX_HASHTAGS`… | **AI & Whisper** | Không | Giữ Settings |

Cả hai màn đều ghi `runtime_settings` qua `upsert_setting()` — trùng **UI**, không trùng storage.

---

## Principles

1. **Một key = một màn sửa** (trừ read-only env).
2. **Settings** = control plane; **AI Studio** = prompt library + sandbox.
3. **Backward compatible**: API save/reset/bulk-save vẫn chấp nhận key hợp lệ (automation/scripts); chỉ ẩn khỏi form Settings.
4. **Minimal diff**: không gộp route, không xóa `SETTINGS` entries.

---

## Scope

### In scope

- Metadata `studio_only` (hoặc tương đương) trên `SettingSpec` + helper lọc cho trang Settings.
- Bỏ filter cứng section name trong `app_settings.html`; dùng `sections` đã lọc từ server.
- Ẩn trên Settings: toàn bộ key đã liệt kê trong **Studio key registry** (xem Phase 1).
- AI Studio: thêm **Threads** prompt; deeplink `?key=` mở đúng template.
- Callout trong section **AI & Whisper** (Settings): link sang AI Studio.
- Copy/nav: subtitle Settings vs AI Studio; nhãn nav rõ vai (optional divider).
- Test guard: studio keys không render trên `/app/settings`.
- Cập nhật handoff + proof trong PLAN.

### Out of scope

- Gộp AI Studio thành tab trong Settings.
- Đổi `BrainFactory` / worker / pipeline logic.
- Sandbox test cho Threads (chỉ editor + lưu).
- i18n đầy đủ.
- ADR bắt buộc (tuỳ chọn DECISION ngắn nếu Anti muốn).

---

## Phase 1 — Registry & metadata (Claude Code)

**Files:** `app/core/settings.py`

1. Thêm field `studio_only: bool = False` vào `SettingSpec`.
2. Set `studio_only=True` cho:
   - `ai.prompt.beauty`, `fashion`, `tech`, `home`, `funny`, `general`
   - `ai.prompt.visual_hook`, `ai.prompt.engagement_secrets`
   - `ai.fallback_caption_pool`, `ai.fallback_hashtag_pool`
   - `THREADS_AI_PROMPT`
3. Helpers:
   - `is_studio_only(spec) -> bool`
   - `list_specs_for_settings_ui() -> dict[str, list[SettingSpec]]` — loại `studio_only` và section rỗng.
4. (Tuỳ chọn) `AI_STUDIO_TEMPLATE_KEYS: tuple[str, ...]` — single list dùng cho test + `ai_studio_service` (tránh drift).

**Acceptance:** import app OK; grep xác nhận 10 keys `studio_only=True`.

---

## Phase 2 — Settings context (Claude Code)

**Files:** `app/platform/dashboard_service.py`, `app/templates/pages/app_settings.html`

1. `get_settings_context()` dùng `list_specs_for_settings_ui()` thay vì `list_specs_by_section()` raw.
2. `section_counts` tính trên specs đã lọc.
3. Xóa điều kiện Jinja `section not in ['AI Prompt Configs', 'AI Prompt Personas']`.
4. Trong section **AI & Whisper**, thêm banner (1 card full-width trên grid):

   > Prompt persona, fallback pool, Threads template → [AI Studio](/app/ai-studio)

5. Reset forms loop: chỉ tạo form reset cho key hiển thị trên Settings (không studio_only).

**Acceptance:** `/app/settings` HTML không chứa `name="ai.fallback_caption_pool"` / `THREADS_AI_PROMPT` / `ai.prompt.general`.

---

## Phase 3 — AI Studio mở rộng (Claude Code)

**Files:** `app/features/system_panel/ai_studio_service.py`, `app/templates/pages/app_ai_studio.html`, `app/features/system_panel/ai_studio_router.py`

1. Thêm nhóm sidebar **Platforms** (hoặc mở rộng Configs):
   - `threads_ai`: key `THREADS_AI_PROMPT`, label rõ, icon đơn giản.
2. Load value giống personas (override DB → default_getter).
3. Deeplink:
   - Router truyền `initial_key` từ `request.query_params.get("key")`.
   - Template/JS: on load, nếu `initial_key` khớp nav item → `selectPrompt(...)`.
4. Cập nhật subtitle AI Studio: nhắc placeholder `{title}`, `{max_chars}` cho Threads template.

**Acceptance:** `/app/ai-studio?key=THREADS_AI_PROMPT` mở editor đúng; lưu qua `/app/ai-studio/save` vẫn ghi DB.

---

## Phase 4 — Nav & copy (Claude Code)

**Files:** `app/templates/layouts/app.html`, `app/templates/pages/app_settings.html` (subtitle), `app/templates/pages/app_ai_studio.html`, (optional) `app/templates/pages/app_control_plane.html`

1. Settings nav label/subtitle: *Cài đặt vận hành* / runtime.
2. AI Studio: bỏ `font-semibold text-indigo-600` lệch style nav (optional — đồng bộ với Settings).
3. Control plane card: một dòng “Prompt → AI Studio only”.

---

## Phase 5 — Verification (Claude Code)

**Tests (mới hoặc mở rộng):** `tests/test_settings_ui_surface.py`

```text
- Client login hoặc TestClient với auth bypass nếu có fixture sẵn
- GET /app/settings → assert studio keys absent from body
- GET /app/ai-studio → assert THREADS_AI_PROMPT trong sidebar HTML hoặc data-key
```

**Manual checklist:**

- [ ] Sửa fallback trên AI Studio → bulk Settings không ghi đè (vì không còn field).
- [ ] Sandbox Facebook niche vẫn chạy (persona + visual hook từ DB).
- [ ] Threads worker/service vẫn đọc `THREADS_AI_PROMPT` từ runtime (không đổi code đọc).

**Commands:**

```bash
venv\Scripts\python.exe -m pytest tests/test_settings_ui_surface.py -q
venv\Scripts\python.exe -c "from app.main import app; print('OK')"
```

Ghi output vào **Execution Notes** và **Verification Proof** (TASK-040).

---

## Risks & mitigation

| Rủi ro | Xác suất | Tác động | Mitigation |
|---|---|---|---|
| User quen sửa fallback trên Settings | TB | Nhẹ | Banner + link AI Studio |
| Bulk-save script POST key studio_only | Thấp | TB | API vẫn cho phép — document trong PLAN |
| Drift danh sách key Studio vs settings flag | TB | Nhẹ | `AI_STUDIO_TEMPLATE_KEYS` + test |
| Deeplink key invalid | Thấp | Nhẹ | Fallback general persona |

**Rollback:** revert commit Phase 1–4; DB không đổi.

---

## Definition of Done

- [x] Không còn field studio-only trên `/app/settings`.
- [x] `THREADS_AI_PROMPT` chỉnh được trên AI Studio.
- [x] Test guard pass + manual checklist ticked (automated; sandbox manual optional).
- [x] `agents/handoffs/current-status.md` updated.
- [ ] TASK-040 → Verified; PLAN + TASK archive khi merge/deploy OK.

---

## Execution Notes

- Phase 1–4: `SettingSpec.studio_only`, `list_specs_for_settings_ui()`, Settings banner + filter server-side, AI Studio Platforms + `?key=` deeplink, nav/copy.
- Phase 5: `tests/test_settings_ui_surface.py` — 3 passed; `from app.main import app` OK.

---

## Related

- Prior art: PLAN-024 (AI migration UI), filter section trong `app_settings.html`
- Config doc: `docs/CONFIG.md` — optional 1 đoạn “UI surfaces”
