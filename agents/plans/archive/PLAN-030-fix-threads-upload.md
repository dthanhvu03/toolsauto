# PLAN-030: Fix Threads Adapter File Upload Step

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-030 |
| **Status** | Active |
| **Executor** | Codex |
| **Created by** | Antigravity |
| **Related Task** | TASK-030 |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Goal
Fix the Threads media upload failure where the adapter cannot find the file input for posts with media.

---

## Context
- Symptom: all Threads jobs with media fail with `Could not find Threads media file input.`
- Root cause 1: `_find_first_visible()` rejects hidden `input[type="file"]` elements because `is_visible()` is false.
- Root cause 2: the adapter does not activate the attach-media control before searching for the file input.

---

## Scope
1. Update `app/adapters/threads/adapter.py`.
2. Add `ATTACH_SELECTORS`.
3. Add `_find_first_present()` for DOM-presence checks without visibility gating.
4. Update `publish()` so media upload clicks attach first, then finds the hidden file input and calls `set_input_files()`.

## Out of Scope
- Do not change worker, dispatcher, or queue logic.
- Do not refactor caption or login flow.

---

## Proposed Approach
1. Add `ATTACH_SELECTORS` for the visible attach-media entry points.
2. Add `_find_first_present()` that returns the first locator with `count() > 0`.
3. In the `media_path` branch of `publish()`:
   - try to click the attach control,
   - wait briefly,
   - locate the hidden file input with `_find_first_present()`,
   - call `set_input_files(media_path)`.

---

## Risks
| Risk | Level | Mitigation |
|---|---|---|
| Attach selectors drift with UI changes | Medium | Use multiple selectors and aria-label fallbacks. |
| File input still appears late after click | Low | Wait briefly after click and use a longer input lookup timeout. |

---

## Validation Plan
- [x] Check 1: `python -m py_compile app/adapters/threads/adapter.py`
- [ ] Check 2: Run on VPS and confirm `Publish completed` plus `post_url`.

---

## Execution Notes
- 2026-04-27 Codex applied the full PLAN-030 code patch in one scoped edit to `app/adapters/threads/adapter.py`.
- Added `ATTACH_SELECTORS` to cover visible attach-media entry points before upload.
- Added `_find_first_present()` so hidden `input[type="file"]` nodes can still be found when they exist in the DOM but fail `is_visible()`.
- Updated the `publish()` media branch to click the attach control first when present, wait briefly, then locate the hidden file input and call `set_input_files(media_path)`.
- Scope guard: no worker, dispatcher, queue, caption, or login logic changed.
- Local code execution is complete. Claude Code verify and VPS runtime proof are still pending.

---

## Verification Proof
- Command: `python -m py_compile app/adapters/threads/adapter.py`
- Result: exit 0, no output.
- Command: `git diff -- app/adapters/threads/adapter.py`
- Result: diff is limited to three scoped changes in the adapter: `ATTACH_SELECTORS`, `_find_first_present()`, and attach-before-file-input upload flow.
- Runtime gap: VPS publish verification is still pending. `Publish completed`, `post_url`, and `external_post_id` are not proven in this turn.
