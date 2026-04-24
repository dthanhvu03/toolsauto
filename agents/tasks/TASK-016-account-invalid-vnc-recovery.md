# TASK-016: Account Invalid + VNC Recovery

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-016 |
| **Status** | Codex Execution Done |
| **Owner** | Codex |
| **Created** | 2026-04-24 |
| **Related Plan** | PLAN-016 |

---

## Goal
Fix the operational path where a Facebook account detected as logged out/checkpointed is not disabled consistently, and make VNC startup usable when no Xvfb display exists yet.

## Scope
- Account invalidation must be environment/path agnostic.
- Account invalidation must block future publisher claims.
- Publisher circuit breaker must update the real account active flag.
- VNC startup must create or reuse display `:99` without hardcoding profile paths.

## Out of Scope
- Facebook page-switch or publish selector logic.
- Direct GraphQL publishing.
- Production database mutation outside code behavior changes.

## Verification
- Python compile check for changed files.
- Run VNC startup script locally and capture actual output.

## Execution Result
- `AccountService.invalidate_account()` disables automation by setting `is_active=false` and `login_status=INVALID`.
- `JobService.mark_failed_or_retry()` circuit breaker now writes `Account.is_active`.
- `scripts/start_vps_vnc.py` starts or reuses `Xvfb :99`, then starts persistent `x11vnc` and `websockify`.

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
```
