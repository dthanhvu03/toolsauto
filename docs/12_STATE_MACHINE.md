# Job State Machine (Strict Rules)

## Allowed States

PENDING
RUNNING
DONE
FAILED
CANCELLED (optional future)

---

## State Transition Table

| From      | To        | Condition |
|-----------|----------|-----------|
| PENDING   | RUNNING  | Worker lock success |
| RUNNING   | DONE     | Adapter success |
| RUNNING   | FAILED   | Adapter error & tries >= max_tries |
| RUNNING   | PENDING  | Adapter error & tries < max_tries |
| PENDING   | CANCELLED| User cancels manually |
| FAILED    | PENDING  | User clicks retry |
| DONE      | (none)   | Final state |

---

## Strict Transition Rules

1. Worker must NEVER process job not in PENDING state.
2. Lock must be atomic:
   UPDATE jobs SET status='RUNNING'
   WHERE id=? AND status='PENDING'

3. RUNNING jobs must not remain locked forever.
   If locked_at older than X minutes:
       auto reset to PENDING (crash recovery).

4. DONE and FAILED are terminal states.
   Only manual action can move FAILED → PENDING.

5. A job cannot go DONE without:
   - started_at
   - finished_at
   - account.last_post_ts updated

6. All transitions must be logged in job_events.

---

## Crash Recovery Rule

If worker crashes during RUNNING:
- On next startup:
  - Find RUNNING jobs with locked_at older than threshold (e.g. 15 min)
  - Reset them to PENDING
  - Increment tries

---

## Acceptance Criteria

- No illegal transitions allowed.
- State change logic centralized in service layer.
- No direct status update in random code blocks.