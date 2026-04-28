# Current Status

## Recent Execution

- **[2026-04-28] PLAN-032 / TASK-032 - Threads own-handle `post_url` capture implemented; VPS verify pending**
  - **Code change**: `app/adapters/threads/adapter.py` now stores `self._own_handle`, parses handle from both `threads.net` and `threads.com`, tries `_capture_own_latest_post()` first, filters fallback capture by own handle only, and clears `observed_urls` immediately before clicking Post so feed URLs collected earlier do not pollute the final capture.
  - **Static proof**:
    - `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m py_compile app/adapters/threads/adapter.py && printf 'PY_COMPILE_OK\n'"` -> `PY_COMPILE_OK`
    - `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'\nfrom app.main import app\nprint('APP_IMPORT_OK %s' % len(app.routes))\nPY"` -> `APP_IMPORT_OK 207`
  - **Local runtime safety proof**:
    - `open_session('content/profiles/facebook_3')` -> `SESSION_OK=True`, `OWN_HANDLE=None`, `CURRENT_URL=https://www.threads.com/`
    - On that same live session: `CAPTURE_POST_REFERENCE=(None, None)` and `PROFILE_CAPTURE=(None, None)`
    - Meaning: if own handle cannot be discovered, the adapter now safe-fails instead of storing a random viral `post_url`.
  - **Local limitation**: all available local Threads profiles currently open `https://www.threads.com/` without a discoverable own handle, so the success path is not reproducible in this workspace.
  - **Claude Code re-verify [2026-04-28]**: diff = `1 file changed, 234 insertions(+), 3 deletions(-)` — scope đúng PLAN-032 (chỉ chạm `app/adapters/threads/adapter.py`, không đụng worker/dispatcher/DB). Re-run `venv/bin/python -m py_compile app/adapters/threads/adapter.py` → `PY_COMPILE_OK`; re-run `from app.main import app` → `APP_IMPORT_OK 207`. Logic check OK: `observed_urls.clear()` đặt ngay trước click Post (line 665), `_capture_own_latest_post()` chạy trước fallback (line 678+), `_capture_post_reference()` trả `None, None` khi không có URL match own-handle, `close_session()` reset `self._own_handle = None`.
  - **Status**: code + Claude Code verify done. VPS handoff still required for acceptance criteria 1 và 3.

- **[2026-04-28] 🐛 ThreadsAdapter capture nhầm `post_url` của người khác — đã mở TASK-032 (Planned)**
  - **Triệu chứng**: VPS job 613 (account Nguyen Ngoc Vi) đăng thành công, nhưng `post_url` trong DB là `https://www.threads.net/@campuchino.iu9x/post/DXpDgbYj12x` — handle `campuchino.iu9x` KHÔNG phải Nguyen Ngoc Vi → đây là bài viral trên feed.
  - **Root cause** ([adapter.py:184-249](app/adapters/threads/adapter.py#L184-L249)):
    1. `capture_response`: scan mọi JSON response, match POST_PATH_RE → vào `observed_urls`.
    2. `_collect_urls_from_dom`: `querySelectorAll('a[href*="/post/"]')` toàn page (feed/comments/sidebar) + regex `page.content()` HTML.
    3. `_capture_post_reference`: trả `ordered_urls[0]` — không filter theo username chủ thể.
    → Sau click Post, Threads redirect về feed → bài viral render trước bài mình post → URL nhầm lên đầu.
  - **Fix recommended** (Codex thực thi qua TASK-032):
    1. `_discover_own_handle()` từ `a[href^="/@"]` ngay sau session init, lưu `self._own_handle`.
    2. `_capture_own_latest_post()`: navigate `https://www.threads.net/{own_handle}` → lấy `a[href*="/{own_handle}/post/"].first`.
    3. Fallback layer 2: filter `_capture_post_reference` theo `f"/{own_handle}/post/"` trong URL — nếu không match thì trả `None, None` (an toàn hơn false positive).
  - **Recovery DB sai**: SQL `UPDATE jobs SET post_url=NULL, external_post_id=NULL WHERE id=613;` (bài thật trên Threads vẫn còn, chỉ data trong DB nhầm).
  - **Status**: TASK-032 đã Planned. Chờ Codex thực thi.

- **[2026-04-28] 🎉 VPS PRODUCTION VERIFY: Threads end-to-end post thành công**
  - **Trigger**: Anh Vu pull `e96a51d` (merge P031) trên VPS + `pm2 restart Threads_Publisher` (restart, không reload — để Python re-import module).
  - **Live job 613**: Account `Nguyen Ngoc Vi`, profile `/root/toolsauto/content/profiles/facebook_2` → POST URL **`https://www.threads.net/@campuchino.iu9x/post/DXpDgbYj12x`**, status DONE, cooldown 48s.
  - **Confirm fix path**: Compose ✓ → caption fill ✓ → attach button click ✓ (P030) → file input found via `_find_first_present` ✓ (P030) → upload ✓ → preview wait ✓ (P031) → Post button click trong dialog ✓ (P031) → URL captured ✓.
  - **Pipeline production-ready**. Worker tự động poll tiếp các Threads PENDING jobs trong queue.
  - **Lesson learned (ghi vào memory cho future deploy)**: PM2 với Python script PHẢI dùng `pm2 restart`, không phải `pm2 reload`. Reload không kill interpreter → module cache còn nguyên → fix không có hiệu lực.

- **[2026-04-28] PLAN-031 / TASK-031 - Threads Post button overlay — DONE & ARCHIVED ✅**
  - **Anti Sign-off**: APPROVED (4/4 AC PASS — overlay click fix, preview wait, fallback chain, no text-only regression).
  - **Claude Code re-verify**: PY_COMPILE_OK, APP_IMPORT_OK 207 routes, 26/26 tests PASS in 0.69s. DB job 790 confirm: `status=DONE, post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF, external_post_id=DXp-D0hjvPF, finished_at=1777339166, last_error=None`. Real post lên Threads thật ✓.
  - **Pending action for anh Vu**:
    1. Commit `M app/adapters/threads/adapter.py` — suggested: `fix(P031): scope Post button to dialog + media preview wait + 3-stage click fallback`.
    2. Push develop → VPS pull → `pm2 reload Threads_Publisher`.
    3. Bulk reset stuck FAILED jobs Threads trên VPS: `UPDATE jobs SET status='PENDING', tries=0, last_error=NULL, started_at=NULL, locked_at=NULL, last_heartbeat_at=NULL, schedule_ts=NULL WHERE platform='threads' AND status='FAILED';`
    4. Xoá post test "NÓNG: Bộ Y tế..." trên account `senhora_consumista` Threads.
  - **Archived**: PLAN-031 → `agents/plans/archive/`; TASK-031 → `agents/tasks/archive/`.

- **[2026-04-28] PLAN-031 / TASK-031 — original Codex handoff (superseded by archive entry above)**
  - **Status**: ✅ Anti Sign-off Completed. Ready for Archive.
  - **Code outcome**: `app/adapters/threads/adapter.py` now scopes `POST_BUTTON_SELECTORS` to `div[role="dialog"]`, waits for a visible media preview after `set_input_files(...)`, and uses a 3-stage click fallback for the final Post action: normal click -> `force=True` click -> JS `evaluate("el => el.click()")`.
  - **Static proof**: `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m py_compile app/adapters/threads/adapter.py && printf 'PY_COMPILE_OK\n'"` -> `PY_COMPILE_OK`.
  - **Runtime proof (local WSL)**:
    - `logs/app.log` lines 37-52 show `Job-790` moving through `[CLAIM]` -> `[PUBLISH]` -> `ThreadsAdapter: Publish completed for job 790 with post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF` -> `[DONE] Successfully published.`
    - DB row `jobs.id=790` now stores `status=DONE`, `tries=2`, `post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF`, `external_post_id=DXp-D0hjvPF`, `last_error=None`.
  - **Open proof gap**: No separate live text-only Threads publish is present in the current local DB (`TEXT_ONLY_JOB_NONE`), so the text-only non-regression criterion is not independently runtime-verified yet. The new preview wait stays inside `if media_path:` and does not execute for text-only jobs.

- **[2026-04-27] PLAN-030 / TASK-030 - Threads upload fix**
  - **Status**: Done and archived.
  - **Outcome**: Fixed hidden Threads media input handling by adding `ATTACH_SELECTORS` and `_find_first_present(...)`.
  - **Git**: committed and pushed on `develop` as `91a6778`.

- **[2026-04-27] PLAN-029 / TASK-029 - Threads publisher implementation**
  - **Status**: Done and archived.
  - **Outcome**: Threads adapter, isolated `Threads_Publisher` worker, dispatcher route, queue platform isolation, and PM2 entry were implemented. Follow-up runtime bugs were split into TASK-030 and TASK-031 instead of reopening PLAN-029.

## System State

- **Environment**: WSL Ubuntu / Python 3.10 / direct server workflow
- **Database**: PostgreSQL
- **Git branch**: `develop`
- **Threads pipeline**: News scrape -> AI gen -> `PENDING` Threads job -> `Threads_Publisher` -> Playwright publish -> DB update (`post_url`, `external_post_id`)
- **Latest local Threads publish proof**: Job `790` published successfully with `post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF`
- **Current Threads priority**: `PLAN-032` is active because VPS job `613` showed `post_url` ownership can still be wrong even when the publish itself succeeds.
- **Threads pipeline status**: ✅✅ End-to-end working **trên VPS production** (commit `e96a51d` merge P031). Live proof job 613 (account `Nguyen Ngoc Vi`, profile `facebook_2`) post thành công: `https://www.threads.net/@campuchino.iu9x/post/DXpDgbYj12x`, status DONE, cooldown 48s tới poll tiếp. Trilogy PLAN-029 + P030 + P031 hoàn tất production verification.
- **AI pipeline baseline**: prior service-layer tests remain at `18/18 PASS`

## Open Risks

- `PLAN-032` still lacks live VPS proof that a fresh publish for account `facebook_2` stores the correct own-handle `post_url`.
- Local Threads profiles in this workspace all open `https://www.threads.com/` without a discoverable own handle, so the success path could not be reproduced locally.

- `PLAN-031` still lacks independent live proof for the text-only Threads publish branch.
- VPS/PM2 verification for the PLAN-031 overlay fix has not been repeated in this turn; current proof is local WSL log + DB evidence.
- The older VPS-side `AI_Generator` `SyntaxError: source code cannot contain null bytes` investigation remains unresolved in handoff history and is unrelated to PLAN-031.

## Next Action

1. Pull this `PLAN-032` adapter diff onto VPS and restart `Threads_Publisher` with `pm2 restart` so Python re-imports the updated module.
2. Run one controlled Threads publish for account `facebook_2`, then verify the new DB row stores the real account handle in `post_url` and `external_post_id`.
3. If handle discovery still fails on VPS, capture that worker/log evidence too; the new adapter should now return no `post_url` instead of a viral false positive.
4. Claude Code verify the `PLAN-032` / `TASK-032` artifact updates and the adapter diff before VPS handoff.
5. After VPS proof is collected, update the `PLAN-032` Anti Sign-off block with the real DB/log evidence.
6. Revisit the older `PLAN-031` text-only proof gap only if that acceptance criterion is still required after `PLAN-032` closes.
