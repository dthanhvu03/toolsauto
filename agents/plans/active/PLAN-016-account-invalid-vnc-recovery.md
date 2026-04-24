# PLAN-016: Account Invalid + VNC Recovery

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-016 |
| **Status** | Codex Execution Done |
| **Executor** | Codex |
| **Created by** | User-directed hotfix |
| **Related Task** | TASK-016 |
| **Created** | 2026-04-24 |
| **Updated** | 2026-04-24 |

---

## Goal
Tighten account-invalid state handling and make the VNC login path usable across VPS/local without hardcoded profile paths.

## Context
- VPS logs can use `/root/toolsauto/content/profiles/facebook_1`.
- Local can use `/home/vu/toolsauto/...`.
- Profile path must remain DB/env driven via `account.resolved_profile_path`.
- `PLAN-015` is active but unrelated to this incident.

## Scope
1. Set `is_active=false` when an account is invalidated by fatal login/checkpoint detection.
2. Fix circuit breaker code to disable `Account.is_active`, not a non-contract `status` attribute.
3. Make VNC startup create display `:99` if no Xvfb is running.

## Validation Plan
- [x] Check 1: compile changed Python files.
- [x] Check 2: run `scripts/start_vps_vnc.py` and capture actual output.
- [x] Check 3: inspect `git diff` scope.

---

## Execution Notes
- ✅ Step 1: Account invalidation state.
  - `AccountService.invalidate_account()` now sets `is_active=false`, `login_status=INVALID`, clears `login_process_pid`, and preserves `login_error`.
  - `JobService.mark_failed_or_retry()` circuit breaker now sets `job.account.is_active=false` instead of writing a non-contract `status` attribute.
- ✅ Step 2: VNC startup display recovery.
  - `scripts/start_vps_vnc.py` now starts `Xvfb :99` when no display exists.
  - `x11vnc`, `openbox`, and `websockify` are started with `subprocess.Popen(..., start_new_session=True)` instead of shell backgrounding.
  - Port checks now verify the actual listening local ports `5900` and `6080`.

## Verification Proof
```
$ ./venv/bin/python -m py_compile app/services/account.py app/services/job.py scripts/start_vps_vnc.py
# exit code: 0

$ ./venv/bin/python scripts/start_vps_vnc.py
Status:
[OK] x11vnc is listening on 5900
[OK] websockify is listening on 6080

$ ss -tlnp
LISTEN 0 32  0.0.0.0:5900 0.0.0.0:* users:(("x11vnc",pid=2364193,fd=4))
LISTEN 0 100 0.0.0.0:6080 0.0.0.0:* users:(("websockify",pid=2364199,fd=3))

$ pgrep -a x11vnc
2364193 x11vnc -display :99 -forever -shared -rfbport 5900 -nopw -noxrecord -noxfixes -noxdamage
```

Execution Done. Cần Claude Code verify + handoff.

---

## Anti Sign-off Gate
**Reviewed by**: Pending

### Verdict
> CODEX EXECUTION DONE - PENDING CLAUDE CODE VERIFY
