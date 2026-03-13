# Testing Strategy (Personal Stable Tool)

## Philosophy

This tool must be:
- Deterministic
- Restart-safe
- No illegal state transitions
- Worker-safe under failure

Testing must focus on:
1) State machine correctness
2) Queue locking correctness
3) Retry/backoff logic
4) Crash recovery
5) Adapter failure containment

We do NOT test Facebook DOM behavior here.
We test our internal system integrity.

---

# I. Test Layers

1. Unit Tests (Core Logic)
2. Integration Tests (DB + Worker)
3. Smoke Tests (Full pipeline dry-run)
4. Manual Validation Checklist

---

# II. Unit Tests (Critical)

## 1. State Machine Tests

Test all legal transitions:

- PENDING → RUNNING
- RUNNING → DONE
- RUNNING → FAILED
- FAILED → PENDING (manual retry)

Ensure illegal transitions raise exception.

Example:
- DONE → RUNNING must fail
- FAILED → DONE must fail

---

## 2. Atomic Lock Test

Simulate:

Worker A and Worker B try to lock same job.

Expected:
- Only 1 worker succeeds.
- Other receives 0 affected rows.

Must assert no duplicate RUNNING.

---

## 3. Retry Logic Test

Given:
- max_tries = 3

Simulate adapter failure:

Attempt 1:
- tries = 1
- schedule_ts updated +5m

Attempt 2:
- tries = 2
- schedule_ts updated +15m

Attempt 3:
- tries = 3
- status = FAILED

Ensure:
- Backoff increases correctly
- FAILED after max_tries

---

## 4. Cooldown & Daily Limit Tests

Given:
- daily_limit = 2
- cooldown = 1800 seconds

Simulate:
- 2 DONE today
Expected:
- 3rd job cannot run

Simulate:
- last_post_ts recent
Expected:
- job rescheduled

---

## 5. Crash Recovery Test

Simulate:
- job status = RUNNING
- locked_at older than threshold

On worker startup:
Expected:
- job reset to PENDING
- tries incremented

---

# III. Integration Tests

## 1. Full Worker Loop Test (Dry Mode)

Implement adapter mock:

publish(job) returns:
- success
- failure
- random failure

Test:
- job goes PENDING → RUNNING → DONE
- failure → backoff → eventually FAILED

---

## 2. File Movement Test

Given job success:
- file moves to content/done/

Given job failure after max_tries:
- file moves to content/failed/

---

# IV. Smoke Test Script

Create script:

scripts/smoke_test.py

Flow:
- Insert fake job
- Use MockAdapter
- Run worker tick once
- Validate:
    - status updated
    - log entry created

Smoke test must pass before production run.

---

# V. Adapter Safety Tests

Adapter must:

- Never crash worker
- Always return structured result
- Always produce error artifacts on failure

Test by:
- Raising exception inside adapter
- Ensure worker catches and updates job

---

# VI. Manual Validation Checklist

Before going live:

- [ ] Create job
- [ ] Worker picks job
- [ ] Job moves RUNNING
- [ ] Job DONE
- [ ] Retry works
- [ ] Reschedule works
- [ ] Crash worker mid-run
- [ ] Restart worker
- [ ] No orphan RUNNING jobs

---

# VII. Testing Discipline Rules

- No test should depend on Facebook UI.
- All adapter tests use mock adapter.
- Real Facebook test = manual QA only.

---

# Definition of Test-Ready

System is considered stable when:

- All unit tests pass
- Integration test passes
- Smoke test passes
- Manual checklist validated