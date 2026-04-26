# ToolsAuto - Current Project Status

*Last updated by: Claude Code — 2026-04-26 (TASK-019 Done: AI Analytics UI — Phase 7 handoff & archive)*

---

## Latest Execution (2026-04-26 — Claude Code)

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
| **Last Major Work** | TASK-019 AI Analytics UI (Observability Hub: 3 tabs + Acknowledge + Live AI Report) |
| **Alembic Head** | `c9d0e1f2a3b4` (add_incident_tables) |

---

## Blockers / Risks

- **AI_Generator PM2 SyntaxError**: The `SyntaxError: source code cannot contain null bytes` (referencing `/usr/bin/bash` line 1 ELF) indicates a VPS environment misconfiguration where a subprocess may be attempting to execute a binary as a script. This is intermittent and needs deeper investigation into subprocess spawning logic.
- **Threads Publisher Worker**: The `Threads_NewsWorker` PM2 process needs to be verified as running on VPS after deploy. The auto-posting flow (scrape → AI → job creation → publish) has not been end-to-end tested in production yet.

---

## Next Action

1. **Verify UI on production**: Sau khi deploy, vào `/app/logs` để check 3 tabs hoạt động trên môi trường thật + 9Router thật (test "Generate Live Report" gọi được Markdown thật, không phải fallback dev).
2. **Schedule AI Reporter** (theo dõi từ TASK-018, chưa có task riêng): đăng ký cron / PM2 cho `workers/ai_reporter.py` chạy 23:59 hằng ngày. Hiện chỉ chạy thủ công.
3. **Quan sát chất lượng grouping**: monitor `incident_logs` + `incident_groups` 1-2 tuần để đo độ chính xác của `error_signature` normalize. Nếu một family bị phân mảnh hoặc gộp nhầm → tinh chỉnh hàm normalize.
4. **TASK-017 (Threads News Automation) — Remaining items**:
   - [ ] Test đăng bài thật trên Threads (end-to-end in production).
   - [ ] Tích hợp vào Maintenance worker để scrape định kỳ (hiện dùng worker riêng).
   - [ ] Monitor Threads_NewsWorker logs on VPS.
5. **PLAN-015 (Business Suite GraphQL reverse-engineering)**: Vẫn ở Bước 1, chờ Codex.
6. **Monitor Production**: Tiếp tục theo dõi `pm2 logs AI_Generator_1`, `pm2 logs FB_Publisher_1`, và `incident_logs` table cho lỗi mới.
7. **DECISION-005 follow-ups (chưa có task)**: Phase 2 (Approval gate cho Auto-Healing), Tier 1-2 alerting (real-time + burst). Chờ Anti quyết định khi nào mở.
