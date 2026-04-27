- **[2026-04-27]** Done TASK-026: Async Pipeline & Threads Caller Migration ✅
  - Triển khai `generate_text_async` và `call_native_gemini_async` (Async SDK).
  - Hoàn tất migrate Threads worker sang kiến trúc AI Pipeline.
  - 23/23 async tests PASS.

## System Health
- **AI Pipeline**: Hoàn thiện 100% (Sync & Async, Text & Vision) với 2 tầng fallback Tier 1 -> Tier 2.

### TASK-025 — ADR-006 Extension: Native Fallback cho Vision Path — DONE
**Outcome:** Hệ thống AI Pipeline hoàn thiện tính năng dự phòng cho tác vụ Vision. `generate_caption` giờ hỗ trợ Tier 1 (9Router) → Tier 2 (Native Gemini SDK). Loại bỏ hoàn toàn legacy `ask_with_file` trong `content_orchestrator.py`. 26/26 pytest PASS.

### TASK-023 + TASK-024 — ADR-006 AI Fallback Strategy implementation — DONE
**Outcome:** Hệ thống AI Pipeline có 2 tầng tin cậy: Tier 1 (9Router canonical) → Tier 2 (Native Gemini fallback). Khi 9Router lỗi (rate limit / circuit open / disabled / 5xx), pipeline tự động chuyển sang gọi Google Gemini SDK trực tiếp. Telegram report + Dashboard UI surface "FALLBACK MODE" rõ ràng để người vận hành biết output đến từ path nào.

| TASK | Title | Owner | Status |
|---|---|---|---|
| **TASK-023** | Implement AI Native Fallback | Claude Code | ✅ Done |
| **TASK-024** | Migrate AI Callers & UI | Claude Code | ✅ Done |

**Files added/modified:**
- `app/services/ai_native_fallback.py` (mới, ~135 LOC) — `call_native_gemini(prompt) -> (text, meta)`. Lazy-import `google.genai`, model rotation 5 model + cooldown 60s. **Đây là nơi DUY NHẤT trong codebase import `google.genai` cho text path** (ADR-006 isolation rule).
- `app/services/ai_pipeline.py` — `generate_text()` rewrite: Tier 1 → Tier 2 → fail. Meta unified với `fallback_used`, `primary_fail_reason`, `fallback_failed`. Pipeline KHÔNG import `google.genai` trực tiếp — delegate qua lazy import.
- `app/services/gemini_api.py` — Module-level `DeprecationWarning` + docstring giải thích vì sao chưa xoá (vision/async path còn dùng).
- `app/services/content_orchestrator.py` — Block `ask_with_file` legacy được comment-hoá với lý do vision path chưa có native fallback.
- `workers/ai_reporter.py` — Telegram header thêm `⚠️ Dự phòng: Gemini Native (model=..., 9Router fail_reason=...)` khi `fallback_used=True`.
- `app/routers/dashboard.py` — Route `/app/logs/ai-report/live` thêm yellow banner "FALLBACK MODE" + meta line đầy đủ (provider/model/fallback_used/generated_at).
- `tests/test_ai_native_fallback.py` (mới) — 4 test mock `google.genai` qua `sys.modules` injection.
- `tests/test_ai_pipeline.py` — Rewrite, 6 test (4 cũ updated + 2 mới fallback path).
- `tests/test_ai_reporter.py` — Thêm test `test_build_report_surfaces_fallback_warning_when_native_used`.

**Verification (chi tiết trong PLAN-022 §6 đã archive):**
- Compile sạch 6 file modified.
- Pytest baseline + new tests: **18/18 PASS** trong 2.16s.
- FastAPI live UI smoke (TestClient + cookie auth + stub pipeline): **7/7 PASS** — banner "FALLBACK MODE" xuất hiện đúng khi `fallback_used=True`, không xuất hiện ở negative case.

**Anti APPROVED Sign-off:** ✅ tại PLAN-022 Sign-off Gate (2026-04-27). PLAN-022 + TASK-023 + TASK-024 đã archive.

**Lệch scope đã ghi rõ + đề xuất follow-up:**
- `gemini_api.py` chưa bị xoá. Còn 7 caller (vision/async path) — out of scope ADR-006 text path.
- Block `GeminiAPIService.ask_with_file` ở `content_orchestrator.py:547` giữ tạm vì pipeline chưa có native vision fallback. Nếu xoá theo literal PLAN sẽ mất behavior.
- **TASK-025 (gợi ý)**: Mở rộng ADR-006 cho vision path → `call_native_gemini_vision` + `pipeline.generate_caption_with_native_fallback`.
- **TASK-026 (gợi ý)**: Migrate `ask_async` (caller duy nhất: `workers/threads_auto_reply.py`).

**Decision Log:** ADR-006 (Phương án A + Guardrails) đã được implement đầy đủ cho text path. Vote 2A/1B-conditional khi RFC: anh Vu chốt A → Claude Code thực thi đúng spec. DECISION-006 P3 (Unify AI Pathway) phần text path: closed. Vision/async path còn lại như follow-up.

---

## Previous Execution (2026-04-26 — Multi-agent: Anti + Codex + Claude Code)

### Sprint summary — DECISION-006 P0/P1/P2 trilogy

3 task của DECISION-006 (Codebase Refactor RFC) đã hoàn thành liên tiếp:

| TASK | Title | Owner | Status |
|---|---|---|---|
| **TASK-020** | Schedule AI Reporter Cron | Antigravity | ✅ Done |
| **TASK-021** | Service Test Baseline | Codex | ✅ Done |
| **TASK-022** | Split models.py into Package | Claude Code | ✅ Done |

#### TASK-020 — Cron AI Reporter (P0)
- `crontab` entry: `0 1 * * *` UTC = `08:00 Asia/Saigon` daily.
- Output → `logs/ai_reporter.log`.
- Heartbeat đảm bảo: gửi report cả khi không có incident, để biết scheduler/Telegram/AI path còn sống.
- Đã thay thế "chạy thủ công" sau TASK-018 — observability loop giờ tự động hoàn toàn.

#### TASK-021 — Service Test Baseline (P1)
- 3 file test mới trong `tests/`: `test_incident_logger.py`, `test_ai_reporter.py`, `test_ai_pipeline.py`.
- 11 test cases mock 9Router HTTP / Telegram / Playwright — KHÔNG gọi live API.
- Coverage: `redact_context`, `build_error_signature`, UPSERT logic, `build_report` (success/fallback/empty), `pipeline.generate_text` (200/429/disabled), JSON parser.
- Đây là safety net BẮT BUỘC trước khi refactor models.py — đã chứng tỏ giá trị ngay khi TASK-022 chạy.

#### TASK-022 — Models split (P2)
- `app/database/models.py` (829 LOC) → package 9 file trong `app/database/models/` (base + 7 domain + __init__).
- **24 model** classes được rải vào 7 file domain (accounts, jobs, viral, incidents, threads, settings, compliance).
- `__init__.py` re-export 26 symbols (24 classes + Base + now_ts) → **0 caller file phải sửa** (69 file caller, 96 import statement).
- Quy tắc tuân thủ: 100% string `relationship`/`ForeignKey`, lazy import duy nhất ở `Account.pick_next_target_page` (cross-domain method).
- `alembic check`: ✅ "No new upgrade operations detected" — schema match.
- TASK-021 baseline: ✅ **11/11 PASS** sau refactor.
- Broader pytest: 43 passed, 13 failed — toàn bộ 13 fail là pre-existing (FB adapter API drift, Playwright timeout, workflow registry, DB fixtures), KHÔNG liên quan models split.

**ADR ký kèm:** [ADR-006 AI Pipeline Fallback Strategy](agents/decisions/ADR-006-ai-fallback-strategy.md) đang ở mục "Owner Decision" — chờ anh Vu chốt phương án (A/B/C) cho P3 Unify AI Pathway. Vote: Anti=A, Claude-Code=A, Codex=B (chấp nhận A có guardrail).

**Files & artifacts:**
- Code mới: `app/database/models/` package (9 files, ~960 LOC tổng), `tests/test_*.py` (3 files, 11 test cases).
- Code xoá: `app/database/models.py` (829 LOC, file gốc).
- Crontab: 1 entry mới cho ai_reporter.
- Plans archived: PLAN-020 (test baseline), PLAN-021 (models split).
- Tasks archived: TASK-020, TASK-021, TASK-022.

---

## Previous Execution (2026-04-26 — Claude Code, earlier today)

### TASK-019 — AI Analytics UI (Observability Hub) — DONE

**Outcome:** Trang `/app/logs` được nâng cấp thành **Observability Hub** với 3 tabs (AI Analytics default / Domain Events / PM2 Logs). Người vận hành giờ có thể xem incident groups, sinh AI report live qua 9Router pipeline, và Acknowledge từng nhóm lỗi mà không phụ thuộc Telegram.

**Files added/modified:**
- `app/routers/dashboard.py` — Thêm import `IncidentGroup` + 3 routes mới: `GET /app/logs/ai-analytics` (HTMX fragment), `GET /app/logs/ai-report/live` (gọi `pipeline.generate_text` qua 9Router → render Markdown bằng `markdown2`), `POST /app/logs/incident/{signature}/ack` (đổi status sang `acknowledged`, trả row HTML đã update). Tái sử dụng `_build_prompt` từ `workers/ai_reporter` để UI và Telegram report đồng bộ.
- `app/templates/pages/app_logs.html` — Refactor thành 3 tabs với JS show/hide + lazy-load HTMX (chỉ fetch lần đầu kích hoạt). Auto-refresh 5s của Domain Events được gate theo tab visibility (không tốn cycle khi đang ở tab khác). PM2 tab dùng fetch() vào `<pre>` đọc từ `/app/logs/tail`.
- `app/templates/fragments/ai_analytics_tab.html` (mới) — Card 1 "AI Health Report" + Card 2 "Top Incidents" table 7 cột (Signature, Platform/Sev, Count, Last Seen, Sample, Status, Action).
- `app/templates/fragments/incident_group_row.html` (mới) — partial 1 row, dùng chung trong table loop và làm response của ack endpoint (HTMX swap outerHTML).

**Pre-requisite (đã làm trước trong lúc lập plan):** `workers/ai_reporter.py` đã chuyển từ `GeminiAPIService` độc lập sang `pipeline.generate_text` của 9Router.

**Verification (8/8 check pass — chi tiết trong PLAN-019 đã archive):**
- `GET /app/logs` render đủ 3 tabs với AI làm default.
- `GET /app/logs/ai-analytics` fragment chứa table + ack button cho seeded row.
- `POST .../ack` trả row HTML cập nhật (badge "Acknowledged", button biến mất).
- DB persist `status=acknowledged, acknowledged_by=dashboard, acknowledged_at`.
- 404 graceful cho signature không tồn tại.
- Re-fetch tab hiển thị đúng status mới.
- `/app/logs/ai-report/live` fallback an toàn khi 9Router offline (200 OK + inline error message, không crash).
- `/app/logs/tail` (PM2) trả 3867 chars text — hoạt động.

**Anti APPROVED Sign-off:** ✅ tại PLAN-019 Sign-off Gate (2026-04-26). PLAN-019 + TASK-019 đã archive.

**Decision Log:** Đây là deliverable thứ 2 từ DECISION-005 (sau TASK-018 backend). Phase 1 "Suggest-only" của Auto-Healing đã có cả backend (incident logging + Telegram report) lẫn UI (Observability Hub). Phase 2 (Approval gate) và Phase 3 (Auto-execute whitelist) vẫn chưa được mở task — chờ Anti quyết định.

---

## Previous Execution (2026-04-26 — Codex, Phase 7 by Claude Code)

### TASK-018 — AI Log Analyzer (Observability & Reporting MVP) — DONE

**Outcome:** Hệ thống thu thập lỗi có cấu trúc tại Dispatcher boundary + Daily Health Report qua Telegram (Gemini 2.5 Flash) đã đi vào hoạt động. Auto-Healing CHƯA có (theo DECISION-005, Out of Scope giai đoạn này).

**Files added/modified:**
- `app/database/models.py` — Thêm `IncidentLog` + `IncidentGroup`.
- `alembic/versions/c9d0e1f2a3b4_add_incident_tables.py` — Migration mới (đã `alembic upgrade head` thành công, revision hiện tại là `c9d0e1f2a3b4 (head)`).
- `app/services/incident_logger.py` (mới) — SHA1 `error_signature`, redact `cookie/token/password/proxy_auth`, INSERT `incident_logs` + UPSERT `incident_groups` qua SQLAlchemy PG `ON CONFLICT`.
- `app/adapters/dispatcher.py` — Bắt exception ngoài cùng + `PageMismatchError`, log incident bằng session riêng để không phá transaction publisher.
- `workers/ai_reporter.py` (mới) — Query top 20 groups 24h → Gemini Flash → TelegramNotifier qua `NotifierService`.

**Verification (proof đã archive trong PLAN-018):**
- Migration applied OK; cả 2 bảng tồn tại với đầy đủ cột.
- Synthetic dispatcher failure → 1 incident được ghi (`signature=124a8788f77ad921`), `dispatcher_result_ok=False`.
- Redact verified: cookie/token/proxy_auth bị loại khỏi `context_json` (`secret_in_context=False`); field an toàn được giữ.
- AI Reporter chạy thủ công thành công: Gemini 2.5 Flash trả về ~18s, Telegram gửi OK (`groups=2`).

**Anti APPROVED Sign-off:** ✅ tại PLAN-018 Sign-off Gate (2026-04-26). PLAN-018 + TASK-018 đã archive.

**Decision Log:**
- DECISION-005 (RFC AI Log Analyzer) đã thảo luận xong cả 5 mục (3.1–3.5). Đây là TASK đầu tiên triển khai từ ADR đó. Phase 1 (Suggest-only) đã hoàn tất; Phase 2 (Approval gate) và Phase 3 (Auto-execute whitelist) chưa được mở task.

---

## Previous Execution (2026-04-26 — Antigravity)

### 1. AI Caption Pipeline Stabilization
**Problem:** AI worker (`AI_Generator`) was crashing with `SyntaxError: source code cannot contain null bytes` and jobs were stalling in `AI_PROCESSING` state due to JSON schema validation failures.

**Root Cause:** Gemini API sometimes returns `null` for optional fields (`hashtags`, `keywords`, `affiliate_keyword`), but the Pydantic schema and JSON validator were treating `null` as a contract violation.

**Fixes Applied:**
- **`app/services/ai_pipeline.py`**: Updated `CaptionPayload` Pydantic model — `hashtags`, `keywords` now `Optional[List[str]]`, `affiliate_keyword` now `Optional[str]`.
- **`app/services/content_orchestrator.py`**: Updated `_is_valid_caption_schema_json` to accept `None` values for optional fields instead of rejecting them.
- **`workers/ai_generator.py`**: Added defensive null checks when processing hashtags/keywords from AI results to prevent AttributeError.

### 2. Threads Auto-Posting Bug Fixes
**Problem:** Threads auto-posting was completely silent — no jobs were being created despite account being connected and auto mode enabled.

**Root Causes Found & Fixed:**
- **Cooldown miscounting** (`app/services/threads_news.py` line 73-76): The cooldown query was counting ALL threads jobs (including `VERIFY_THREADS` verification jobs) as "posts". Fixed to only count `job_type == "post"`.
- **Hardcoded account selection** (`app/services/threads_news.py` line 91): Was hardcoded to find `Account.profile_path.like("%facebook_3")` (Hoang Khoa only). Fixed to dynamically find any account with `platform LIKE "%threads%"` and `is_active == True`.

### 3. Threads Settings UI (Remove Hardcoded Values)
**Problem:** All Threads configuration was hardcoded — AI prompt, scrape cycle, character limits — with no way to customize from the dashboard.

**New Settings added to `app/services/settings.py` under section "Threads Auto":**

| Setting Key | Type | Default | Description |
|---|---|---|---|
| `THREADS_AUTO_MODE` | bool | `false` | Bật/tắt auto posting |
| `THREADS_POST_INTERVAL_MIN` | int | `180` | Cooldown giữa 2 bài (phút) |
| `THREADS_SCRAPE_CYCLE_MIN` | int | `30` | Chu kỳ quét tin mới (phút) |
| `THREADS_MAX_CHARS_PER_SEGMENT` | int | `450` | Ký tự tối đa mỗi bài trong thread |
| `THREADS_MAX_CAPTION_LENGTH` | int | `500` | Ký tự tối đa caption (cắt cuối) |
| `THREADS_AI_PROMPT` | text | (template) | AI Prompt viết bài, hỗ trợ `{title}`, `{summary}`, `{source_name}`, `{max_chars}` |

**Files Updated:**
- `app/services/settings.py` — 6 new SettingSpec entries
- `app/services/threads_news.py` — Replaced hardcoded prompt, char limits with `get_setting()` calls
- `workers/threads_news_worker.py` — Sleep cycle now reads from `THREADS_SCRAPE_CYCLE_MIN` setting

---

## Previous Execution (2026-04-25 — Claude Code)

**Threads Dashboard UX touch-up (template-only, no behavior change):**
- Fix bug `{{ job.caption[:80] }}...` luôn nối "..." → dùng `truncate(80, true, '…')` + default '(no caption)'.
- Thêm empty state cho News Intelligence Feed và Job Pipeline khi list rỗng.
- Defensive `(acc.name or '?')[0]` cho avatar initial khi name rỗng.
- Validate: Jinja parse OK (`env.get_template('pages/app_threads.html')`).
- File: `app/templates/pages/app_threads.html` (chỉ template).

**PLAN-016 Verification & Sign-off:**
- Verified diff scope: Codex chỉ chạm 3 files đúng scope (`app/services/account.py`, `app/services/job.py`, `scripts/start_vps_vnc.py`) trong commit `6b34fbe`, plus follow-up VNC fixes ở `f0995c1` + `b871c55`.
- Compile proof: `py_compile` 3 file → exit 0.
- Runtime proof: `scripts/start_vps_vnc.py` chạy clean, `x11vnc:5900` + `websockify:6080` đều listening.
- Sign-off **APPROVED** trong PLAN-016. Đã archive PLAN-016 + TASK-016.

---

## System State
| Item | State |
|---|---|
| **Environment** | WSL Ubuntu / Python 3.10 / Direct Server |
| **Database** | PostgreSQL (Production Standard) |
| **Backend** | Running (`pm2 logs`) |
| **Git Branch** | develop |
| **Last Major Work** | TASK-023/024: ADR-006 AI Fallback (9Router → Native Gemini, isolated, surfaced UX) |
| **Models Package** | `app/database/models/` (9 files, 24 model classes, backward-compat 100%) |
| **AI Pipeline** | 2-tier: 9Router (canonical) → Native Gemini (fallback, isolated in `ai_native_fallback.py`) |
| **Test Baseline** | `tests/test_{incident_logger,ai_reporter,ai_pipeline,ai_native_fallback}.py` — **18/18 PASS** |
| **Cron Jobs** | AI Reporter daily 08:00 Asia/Saigon |
| **Alembic Head** | `c9d0e1f2a3b4` (add_incident_tables) |
| **Deprecated Modules** | `app/services/gemini_api.py` (text path) — emits `DeprecationWarning`; vision/async still allowed temporarily |

---

## Blockers / Risks

- **AI_Generator PM2 SyntaxError**: The `SyntaxError: source code cannot contain null bytes` (referencing `/usr/bin/bash` line 1 ELF) indicates a VPS environment misconfiguration where a subprocess may be attempting to execute a binary as a script. This is intermittent and needs deeper investigation into subprocess spawning logic.
- **Threads Publisher Worker**: The `Threads_NewsWorker` PM2 process needs to be verified as running on VPS after deploy. The auto-posting flow (scrape → AI → job creation → publish) has not been end-to-end tested in production yet.

---

## Next Action

1. **Verify ADR-006 fallback trên production**:
   - Quan sát Telegram report sáng mai (08:00) — nếu 9Router OK, header bình thường; nếu fail, header chứa `⚠️ Dự phòng: Gemini Native`.
   - Vào Dashboard `/app/logs` tab AI Analytics → bấm "Generate Live Report" → khi 9Router xuống nhân tạo (vd disable), kiểm tra banner yellow "FALLBACK MODE" hiển thị đúng.
2. **DECISION-006 follow-ups (chưa mở task)**:
   - **TASK-025 (gợi ý)**: Mở rộng ADR-006 cho **vision path**. Tạo `call_native_gemini_vision()` + `pipeline.generate_caption_with_native_fallback()`. Sau đó xoá block `ask_with_file` trong `content_orchestrator.py:547`.
   - **TASK-026 (gợi ý)**: Migrate `ask_async` (caller duy nhất `workers/threads_auto_reply.py`) — async wrapper.
   - Sau khi 2 task trên xong, có thể xoá `gemini_api.py` hoàn toàn.
3. **Quan sát incident grouping**: monitor `incident_logs` + `incident_groups` 1-2 tuần để đo độ chính xác `error_signature` normalize.
4. **TASK-017 (Threads News Automation) — Remaining items**:
   - [ ] Test đăng bài thật trên Threads (end-to-end in production).
   - [ ] Tích hợp vào Maintenance worker để scrape định kỳ.
   - [ ] Monitor Threads_NewsWorker logs on VPS.
5. **PLAN-015 (Business Suite GraphQL)**: Vẫn ở Bước 1, chờ Codex.
6. **Monitor Production**: `pm2 logs AI_Generator_1`, `pm2 logs FB_Publisher_1`, `incident_logs` table.
7. **DECISION-005 follow-ups (chưa có task)**: Phase 2 (Approval gate cho Auto-Healing), Tier 1-2 alerting (real-time + burst).
8. **DECISION-006 P4-P5 (chưa mở task)**: P4 FB Adapter split opportunistic, P5 Router refactor opportunistic.
