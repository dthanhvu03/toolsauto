# TASK-032: Fix Threads Post URL Capture (Scoping to Own Profile)

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-032 |
| **Status** | In Progress |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-032 |
| **Created** | 2026-04-28 |
| **Updated** | 2026-04-28 |

---

## Objective
Fix the Threads adapter logic to ensure it captures the newly published post URL belonging to the authenticated account, preventing it from capturing unrelated viral posts from the home feed.

---

## Scope
- Modify \pp/adapters/threads/adapter.py\ to implement own-handle discovery and profile-based post capture.
- Ensure fallback capture logic filters by the discovered handle.

## Out of Scope
- Modifying the worker, dispatcher, or database schema.
- Changes to the media upload or login flow.

---

## Blockers
- None

---

## Acceptance Criteria
- [ ] Job đăng thành công → post_url trong DB là bài thật của account đó (URL chứa /@<handle-của-account>/post/...).
- [ ] Nếu adapter không xác định được own handle → return None, None → worker mark FAILED thay vì gắn URL nhầm.
- [ ] Account Nguyen Ngoc Vi (profile facebook_2) test thực tế: job mới có URL chính xác.

---

## Execution Notes
- [2026-04-28] Updated `app/adapters/threads/adapter.py` only:
  - Added `self._own_handle`, `_normalize_handle()`, `_discover_own_handle()`, and `_capture_own_latest_post()`.
  - `publish()` now clears `observed_urls` right before Post, waits 3-5s for commit, tries profile capture first, then falls back to own-handle filtered capture only.
  - `_capture_post_reference()` now safe-fails with `None, None` when no candidate matches the discovered handle.
*(Executor điền vào trong khi làm)*

---

## Verification Proof
- Static proof:
  - `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m py_compile app/adapters/threads/adapter.py && printf 'PY_COMPILE_OK\n'"` -> `PY_COMPILE_OK`
  - `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'\nfrom app.main import app\nprint('APP_IMPORT_OK %s' % len(app.routes))\nPY"` -> `APP_IMPORT_OK 207`
- Helper smoke proof:
  - `_normalize_handle('https://www.threads.net/@campuchino.iu9x')` -> `@campuchino.iu9x`
  - `_normalize_handle('https://www.threads.com/@campuchino.iu9x')` -> `@campuchino.iu9x`
  - `_capture_post_reference(...)` with mixed own/viral sample -> `('https://www.threads.net/@campuchino.iu9x/post/DXpDgbYj12x', 'DXpDgbYj12x')`
- Local runtime safety proof:
  - `open_session('content/profiles/facebook_3')` -> `SESSION_OK=True`, `OWN_HANDLE=None`, `CURRENT_URL=https://www.threads.com/`
  - On that same live session: `CAPTURE_POST_REFERENCE=(None, None)` and `PROFILE_CAPTURE=(None, None)`
  - Result: when own handle cannot be discovered, the adapter now safe-fails instead of emitting a random viral `post_url`.
- Remaining gap:
  - No authenticated local Threads profile in this workspace currently exposes a discoverable own handle.
  - Account `facebook_2` / VPS publish proof is still pending.
*(Bắt buộc điền trước khi chuyển Status → Verified)*

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-28 | In Progress | adapter.py updated; static proof passed; local runtime proves safe-fail branch; VPS verification still pending |
| 2026-04-28 | New | Task được tạo bởi Anti theo yêu cầu của user |
