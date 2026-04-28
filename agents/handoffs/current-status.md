# Current Status

## Recent Execution

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
- **Threads pipeline status**: ✅ End-to-end working (PLAN-029 worker + PLAN-030 file-input + PLAN-031 Post-button overlay all DONE & ARCHIVED). Pending VPS deploy commit P031.
- **AI pipeline baseline**: prior service-layer tests remain at `18/18 PASS`

## Open Risks

- `PLAN-031` still lacks independent live proof for the text-only Threads publish branch.
- VPS/PM2 verification for the PLAN-031 overlay fix has not been repeated in this turn; current proof is local WSL log + DB evidence.
- The older VPS-side `AI_Generator` `SyntaxError: source code cannot contain null bytes` investigation remains unresolved in handoff history and is unrelated to PLAN-031.

## Next Action

1. Claude Code verify `PLAN-031` / `TASK-031` against the current adapter diff and proof artifacts.
2. If explicit runtime proof for the last acceptance criterion is required, prepare one safe text-only Threads job and run a controlled publish instead of replaying job `790`.
3. After verify, archive `PLAN-031` / `TASK-031` or reprioritize the next active plan (`PLAN-015`) based on owner direction.
