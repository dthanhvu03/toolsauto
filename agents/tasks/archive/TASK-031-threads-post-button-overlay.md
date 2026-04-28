# TASK-031: Fix Threads Post Button Click Overlay

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-031 |
| **Status** | Execution Done (Pending Claude verify) |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-031 |
| **Created** | 2026-04-28 |
| **Updated** | 2026-04-28 |

---

## Objective
Fix the issue where the "Post" button on Threads is blocked by an overlay (media upload preview), causing timeouts. Ensure the button is clicked successfully using refined selectors and robust fallback mechanisms.

---

## Scope
- Update `POST_BUTTON_SELECTORS` in `app/adapters/threads/adapter.py` to be dialog-scoped.
- Implement wait for media preview visibility in the compose dialog.
- Implement robust multi-stage click strategy (Normal -> Force -> JS click).

---

## Acceptance Criteria
- [x] Job Threads with media can be posted successfully.
- [x] Post button click no longer timeouts due to overlay obstruction.
- [x] `post_url` and `external_post_id` are correctly captured and saved in DB.
- [ ] No regressions for text-only posts.

---

## Execution Notes
- [x] Step 1: Update selectors in `adapter.py`.
- [x] Step 2: Add thumbnail wait logic.
- [x] Step 3: Implement click fallbacks.
- [x] Step 4: Verify with Job 790 via local log + DB proof (`status=DONE`, `post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF`, `external_post_id=DXp-D0hjvPF`).

Execution Done. Cần Claude Code verify + handoff.

Note: No separate live text-only Threads publish is available in the current local DB (`TEXT_ONLY_JOB_NONE`), so the last acceptance criterion remains pending explicit runtime proof. The media preview wait is scoped inside `if media_path:` and did not change the text-only branch directly.

---

## Verification Proof
```text
$ wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m py_compile app/adapters/threads/adapter.py && printf 'PY_COMPILE_OK\n'"
PY_COMPILE_OK

$ Select-String -Path logs/app.log -Pattern 'Job-790|ThreadsAdapter: Publish completed for job 790' -Context 0,2
logs/app.log:37:2026-04-28 01:18:58 [INFO] threads_publisher: [THREADS_PUBLISHER] [Job-790] [CLAIM] Account='Hoang Khoa' Platform=threads
logs/app.log:38:2026-04-28 01:18:58 [INFO] threads_publisher: [THREADS_PUBLISHER] [Job-790] [PUBLISH] Starting Threads publish...
logs/app.log:50:2026-04-28 01:19:26 [INFO] app.adapters.threads.adapter: ThreadsAdapter: Publish completed for job 790 with post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF
logs/app.log:52:2026-04-28 01:19:26 [INFO] threads_publisher: [THREADS_PUBLISHER] [Job-790] [DONE] Successfully published.

$ wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'
from app.database.core import SessionLocal
from app.database.models import Job

db = SessionLocal()
try:
    job = db.query(Job).filter(Job.id == 790).first()
    for field in ['id', 'status', 'tries', 'post_url', 'external_post_id', 'last_error']:
        print(f'{field}={getattr(job, field, None)}')
finally:
    db.close()
PY"
id=790
status=DONE
tries=2
post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF
external_post_id=DXp-D0hjvPF
last_error=None

$ wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'
from app.database.core import SessionLocal
from app.database.models import Job

db = SessionLocal()
try:
    row = (
        db.query(Job.id)
        .filter(Job.platform == 'threads')
        .filter(Job.post_url.isnot(None))
        .filter((Job.media_path.is_(None)) | (Job.media_path == ''))
        .order_by(Job.id.desc())
        .first()
    )
    print('TEXT_ONLY_JOB_NONE' if row is None else f'TEXT_ONLY_JOB id={row.id}')
finally:
    db.close()
PY"
TEXT_ONLY_JOB_NONE
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-28 | In Progress | Task created to address PLAN-031 implementation |
| 2026-04-28 | Execution Done | Media-post overlay fix is proven on local job 790; text-only live proof is still pending Claude verify/handoff. |
