# TASK-030: Fix Threads Adapter File Upload Step

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-030 |
| **Status** | Done |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-030 |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Objective
Fix the Threads media-upload path so posts with images can find and use the hidden file input after the attach control is activated.

---

## Scope
- Update `app/adapters/threads/adapter.py`.
- Add attach-button selectors.
- Update the media upload flow inside `publish()`.

---

## Acceptance Criteria
- [ ] Threads jobs with media publish successfully.
- [ ] Jobs without media still work normally.
- [ ] `post_url` and `external_post_id` are stored correctly in the DB.

---

## Execution Notes
- 2026-04-27 Codex status:
  - Step 1 complete: `ATTACH_SELECTORS` and `_find_first_present()` added to the adapter.
  - Step 2 complete: `publish()` now attempts attach-button activation before locating the hidden file input.
  - Step 3 complete: static verification passed with `python -m py_compile app/adapters/threads/adapter.py`.
  - Local code execution is complete. Claude Code verify and VPS runtime proof are still pending.

---

## Verification Proof
- Command: `python -m py_compile app/adapters/threads/adapter.py`
- Result: exit 0, no output.
- Diff proof: `git diff -- app/adapters/threads/adapter.py` shows only the planned adapter changes for hidden file-input upload handling.
- Acceptance criteria status: live Threads publish proof is still pending, so job success, no-regression proof, and DB `post_url` / `external_post_id` confirmation remain open.
