# ToolsAuto - Current Project Status

*Last updated by: Antigravity — 2026-04-26 (AI Caption Pipeline Stabilization + Threads Auto-Posting Fixes)*

---

## Latest Execution (2026-04-26 — Antigravity)

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
| **Last Major Work** | AI Caption Pipeline Fix, Threads Auto-Posting Stabilization, Threads Settings UI |

---

## Blockers / Risks

- **AI_Generator PM2 SyntaxError**: The `SyntaxError: source code cannot contain null bytes` (referencing `/usr/bin/bash` line 1 ELF) indicates a VPS environment misconfiguration where a subprocess may be attempting to execute a binary as a script. This is intermittent and needs deeper investigation into subprocess spawning logic.
- **Threads Publisher Worker**: The `Threads_NewsWorker` PM2 process needs to be verified as running on VPS after deploy. The auto-posting flow (scrape → AI → job creation → publish) has not been end-to-end tested in production yet.

---

## Next Action

1. **TASK-017 (Threads News Automation) — Remaining items**:
   - [ ] Test đăng bài thật trên Threads (end-to-end in production).
   - [ ] Tích hợp vào Maintenance worker để scrape định kỳ (hiện dùng worker riêng).
   - [ ] Monitor Threads_NewsWorker logs on VPS.
2. **PLAN-015 (Business Suite GraphQL reverse-engineering)**: Vẫn ở Bước 1, chờ Codex.
3. **Monitor Production**: Tiếp tục theo dõi `pm2 logs AI_Generator_1` và `pm2 logs FB_Publisher_1`.
