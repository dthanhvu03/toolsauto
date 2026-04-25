# ToolsAuto - Current Project Status

*Last updated by: Claude Code — 2026-04-25 (PLAN-016 verify + sign-off + archive)*

---

## Latest Execution (2026-04-25 — Claude Code)

**Threads Dashboard UX touch-up (template-only, no behavior change):**
- Fix bug `{{ job.caption[:80] }}...` luôn nối "..." → dùng `truncate(80, true, '…')` + default '(no caption)'.
- Thêm empty state cho News Intelligence Feed và Job Pipeline khi list rỗng.
- Defensive `(acc.name or '?')[0]` cho avatar initial khi name rỗng.
- Validate: Jinja parse OK (`env.get_template('pages/app_threads.html')`).
- File: `app/templates/pages/app_threads.html` (chỉ template).

**PLAN-016 Verification & Sign-off:**
- Verified diff scope: Codex chỉ chạm 3 files đúng scope (`app/services/account.py`, `app/services/job.py`, `scripts/start_vps_vnc.py`) trong commit `6b34fbe`, plus follow-up VNC fixes ở `f0995c1` + `b871c55`.
- Compile proof: `py_compile` 3 file → exit 0.
- Runtime proof: `scripts/start_vps_vnc.py` chạy clean, `x11vnc:5900` + `websockify:6080` đều listening (Xvfb đã sẵn ở `:100`, fallback start `:99` không cần kích hoạt lần này).
- Code claim đúng: `invalidate_account()` set `is_active=False` + `login_status=INVALID` + clear `login_process_pid`; circuit breaker dùng `is_active` thay cho `status` non-contract.
- Sign-off **APPROVED** trong PLAN-016. Đã archive PLAN-016 + TASK-016.

---

## Previous Execution (2026-04-25 — Antigravity)

**Threads Account Dropdown Hotfix (Codex, user-directed):**
- Fixed `/threads` account linking backend to only show active Facebook-capable accounts in the Threads dropdown.
- Normalized comma-separated `Account.platform` tokens before checking `facebook` / `threads`.
- Guarded `/threads/link-account` so non-Facebook accounts cannot be linked to Threads accidentally.
- Verification proof:
  - `wsl -d Ubuntu --cd /home/vu/toolsauto -- ./venv/bin/python -m py_compile app/routers/threads.py` -> exit code 0.
  - Render/data check -> `linked=[(3, 'Hoang Khoa', 'facebook,threads')]`, `available=[(4, 'Nguyen Ngoc Vi', 'facebook')]`.
  - Template render check -> `has_select=True`, `has_fb_available=True`, `has_ig_available=False`, `option_count=1`.
  - Authenticated TestClient GET `/threads/` -> `status=200`, `has_select=True`, `option_count=1`.
  - `pm2 restart Web_Dashboard --update-env` -> restarted process ids `3` and `9`; both returned `online`.

**Threads Dashboard & System Optimization:**
- **UI/UX**: Implemented a Premium "Threads Master" Dashboard (`/threads`) with dark glassmorphism design, live HTMX feeds for News, and a visual Job Pipeline.
- **Cleanup**: Purged massive storage bloat in `logs/` (176MB of screenshots/HTML dumps reduced to ~700KB). Removed obsolete `scratch/` files and deprecated `database.db` (SQLite). Cleared Chromium Caches via `CleanupService`.
- **Facebook Production Instability Fixes**: Hardened the `FacebookAdapter` to resolve "smoothness" issues on the VPS (lazy-loading, slow rendering, slug-to-ID resolution).

---

## System State
| Item | State |
|---|---|
| **Environment** | WSL Ubuntu / Python 3.10 / Direct Server |
| **Database** | PostgreSQL (Production Standard) |
| **Backend** | Running (`pm2 logs`) |
| **Git Branch** | develop |
| **Last Major Work** | Threads Dashboard UI, Storage Recovery, and Facebook Page Switcher Reliability. |

---

## Done This Session (Verified)

### 1. Threads Master Dashboard
- ✅ Created `app/routers/threads.py` for backend data aggregation (Stats, News, Jobs).
- ✅ Built `app/templates/pages/app_threads.html` featuring a stunning Indigo/Purple dark mode design, utilizing HTMX for dynamic updates without page reloads.
- ✅ Integrated `/threads` into the main application sidebar (`app.html`).
- ✅ Registered `datetime` template filter in `main_templates.py` for global timestamp formatting.

### 2. Comprehensive System Cleanup
- ✅ **Logs**: Deleted thousands of `*.png`, `*.html`, and JSON trace files from `logs/`. Truncated active `.log` files to 0 bytes to reclaim space safely.
- ✅ **Cache**: Executed Chromium Cache/GPU clear across all account profiles, recovering gigabytes of space.
- ✅ **Scratch/Legacy**: Deleted root-level scratch scripts (`scratch_*.py`), `check_pg.py`, and the deprecated `database.db` (SQLite is no longer used).

### 3. Facebook "Smoothness" & Reliability Fixes
- ✅ **Lazy-Load Scrolling**: Added a 5-iteration scroll loop inside the Profile Switcher dialog (`div[role="dialog"]`) to ensure Pages out of the initial viewport are loaded into the DOM.
- ✅ **Dynamic Element Polling**: Upgraded `_wait_and_locate_array` to poll for 5 seconds (500ms intervals) instead of instantly failing, accommodating slow React rendering on the VPS.
- ✅ **Slug to Numeric ID Resolution**: Implemented `_extract_page_id_from_current_page()` to pull the underlying Facebook numeric ID directly from page metadata (App Links / JSON-LD) when jobs use vanity URLs (e.g., `/kids0810`). This guarantees a perfect `href` match in the profile switcher.
- ✅ **Signature Fix**: Removed incorrect `@staticmethod` from `_facebook_numeric_id_from_url` to align with the new class-bound logic.

---

## Blockers / Risks

- **Facebook Production Workflows**: Previously failed due to the Profile Switcher not finding the page. The newly deployed "Smoothness" fixes (Scrolling + Polling + ID Extraction) are designed to resolve this. Needs monitoring on the next run.
- **Account 3 (Hoang Khoa)**: Manages a large number of Pages, which was the root cause of the lazy-load failure. The scroll fix should stabilize this account.

---

## Next Action

1. **TASK-017 (Threads News Automation) — còn dở**:
   - Tích hợp `news_scraper` vào Maintenance worker (scrape RSS định kỳ).
   - Hoàn thiện `app/services/content_orchestrator.py` (method chính thức cho Threads news).
   - Cập nhật `workers/ai_generator.py` để xử lý nguồn tin tức.
   - Cập nhật `app/services/strategic.py` để trigger định kỳ.
   - Test đăng bài thật trên Threads sau khi anh duyệt.
2. **PLAN-015 (Business Suite GraphQL reverse-engineering)**: Vẫn ở Bước 1, chờ Codex.
3. **Monitor Production**: Tiếp tục theo dõi `pm2 logs FB_Publisher_1` cho FB smoothness fixes.
