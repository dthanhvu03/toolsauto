# PLAN-032: Fix Threads Post URL Capture (Scoping to Own Profile)

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-032 |
| **Status** | Active |
| **Executor** | Codex |
| **Created by** | Antigravity |
| **Related Task** | TASK-032 |
| **Related ADR** | None |
| **Created** | 2026-04-28 |
| **Updated** | 2026-04-28 |

---

## Goal
Implement a robust post URL capture strategy in the Threads adapter by:
1. Discovering the user's handle during session init.
2. Navigating to the user's profile post-publish to find the latest post.
3. Filtering all captured URLs to match the user's handle.

---

## Context
After PLAN-031 enabled successful posting on Threads, it was discovered that the adapter sometimes captures post URLs from the home feed (viral posts) instead of the user's own post. This happens because Threads often redirects to the home feed after posting, and viral posts may load faster than the user's own post reference.

---

## Scope
### [MODIFY] [adapter.py](file:///Ubuntu/home/vu/toolsauto/app/adapters/threads/adapter.py)
- `__init__`: Add `self._own_handle`.
- `_discover_own_handle()`: New helper to extract handle from the UI.
- `open_session()`: Call discovery after authentication.
- `_capture_own_latest_post()`: New strategy to navigate to profile and grab the newest post.
- `publish()`: Update the capture loop to use the profile strategy first.
- `_capture_post_reference()`: Filter captured URLs by `self._own_handle`.

---

## Out of Scope
- Infrastructure changes.
- Changes to other platform adapters.

---

## Proposed Approach

**Bước 1**: Modify `__init__` and `open_session` to discover and store `self._own_handle`.
**Bước 2**: Implement `_capture_own_latest_post` which navigates to `https://www.threads.net/{handle}` and finds the first post link.
**Bước 3**: Update `publish` loop:
- Wait 3-5s for dialog to close and post to commit.
- Call `_capture_own_latest_post`.
- If successful, return `PublishResult`.
- If not, proceed to fallback capture but ensure it filters by handle.
**Bước 4**: Update `_capture_post_reference` to strictly filter by `self._own_handle` if available. If no match is found, return `None, None`.

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Profile navigation fails or times out | Low | Fallback to handle-filtered DOM capture. |
| Handle discovery fails | Low | Fallback to old (unfiltered) logic OR return None (safer). We will return None if handle is missing to avoid wrong URLs. |
| Threads UI changes profile link selector | Medium | Keep selector generic (`a[href^="/@"]`) and log warnings. |

---

## Validation Plan
- [ ] Run Threads publish job on VPS for account `facebook_2`.
- [ ] Verify `post_url` in database contains `/@nguyenngocvi/post/`.
- [ ] Verify that if handle discovery is forced to fail, the job fails instead of capturing a random URL.

---

## Rollback Plan
`git checkout app/adapters/threads/adapter.py`

---

## Execution Notes
- [2026-04-28][Step 1-4] Updated `app/adapters/threads/adapter.py` only:
  - Added `self._own_handle` state plus `_normalize_handle()` for both `threads.net` and `threads.com`.
  - Added `_discover_own_handle()` and `_capture_own_latest_post()`.
  - Updated `open_session()` to discover handle after session open.
  - Updated `publish()` to clear pre-click `observed_urls`, wait 3-5s after Post, try profile capture first, then fall back to own-handle filtered capture only.
  - Updated `_capture_post_reference()` to return `None, None` when no candidate matches `self._own_handle`.
- Code execution done. Claude Code verify + VPS handoff still required for acceptance criteria 1 and 3.
*(Executor điền vào theo thứ tự từng bước)*

---

## Anti Sign-off Gate ⛔
**Reviewed by**: Antigravity — [2026-04-28]

### Acceptance Criteria Check
| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Job đăng thành công → post_url đúng chủ thể | No | ⏳ |
| 2 | Nếu không xác định được handle → return None | No | ⏳ |
| 3 | Test thực tế trên VPS đạt kết quả đúng | No | ⏳ |

### Verdict
> **IN PROGRESS - Code complete, VPS verification pending**

## Executor Update - 2026-04-28
- Acceptance criterion 2 is now covered by local runtime safety proof:
  - `open_session('content/profiles/facebook_3')` -> `SESSION_OK=True`, `OWN_HANDLE=None`, `CURRENT_URL=https://www.threads.com/`
  - On that same live session: `CAPTURE_POST_REFERENCE=(None, None)` and `PROFILE_CAPTURE=(None, None)`
  - Result: when own handle cannot be discovered, the adapter now safe-fails instead of emitting a random viral `post_url`.
- Static proof:
  - `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m py_compile app/adapters/threads/adapter.py && printf 'PY_COMPILE_OK\n'"` -> `PY_COMPILE_OK`
  - `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'\nfrom app.main import app\nprint('APP_IMPORT_OK %s' % len(app.routes))\nPY"` -> `APP_IMPORT_OK 207`
- Helper smoke proof:
  - `_normalize_handle('https://www.threads.net/@campuchino.iu9x')` -> `@campuchino.iu9x`
  - `_normalize_handle('https://www.threads.com/@campuchino.iu9x')` -> `@campuchino.iu9x`
  - `_capture_post_reference(...)` with mixed own/viral sample -> `('https://www.threads.net/@campuchino.iu9x/post/DXpDgbYj12x', 'DXpDgbYj12x')`
- Remaining gap:
  - All available local Threads profiles currently open `https://www.threads.com/` without a discoverable own handle, so the success path is not locally reproducible in this workspace.
  - Acceptance criteria 1 and 3 still require a real VPS publish for account `facebook_2`.
- Code execution done. Claude Code verify + VPS handoff still required.
