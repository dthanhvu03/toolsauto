# Monitoring & Health Guide (Personal Stable Mode)

Monitoring is required even for personal tool.
If you cannot see system health, you cannot trust automation.

---

# I. Logging Architecture

## Log Files

logs/
  app.log
  worker.log
  jobs/
      job_<id>/
          screenshot.png
          error.html
          trace.zip (optional)

---

## Log Levels

INFO:
- Job state transitions
- Worker tick
- Adapter step start/finish

WARNING:
- Retry triggered
- Cooldown reschedule
- Daily limit exceeded

ERROR:
- Adapter failure
- DB failure
- Unexpected exception

CRITICAL:
- Worker crash
- DB unavailable

---

# II. Worker Health Monitoring

Worker must log heartbeat:

Every tick:
    "Worker tick at <timestamp>"

Add health timestamp file:

data/worker_heartbeat.txt

Update every tick.

---

# III. Health Endpoint (FastAPI)

Add:

GET /health

Returns:

{
  "status": "ok",
  "db": "ok",
  "worker_heartbeat_age_seconds": X
}

If heartbeat older than threshold (e.g. 120s):
    status = degraded

---

# IV. Log Rotation

For personal mode:

- Use RotatingFileHandler
- Max size: 5MB
- Keep last 5 files

Never allow unlimited log growth.

---

# V. Failure Artifact Policy

On adapter error:

Must save:

- Screenshot
- Page HTML dump
- Error message

Store path in DB (job.last_error or job_events)

---

# VI. Alert Strategy (Optional but Recommended)

Minimal alert:

If job FAILED:
- Print clear log line
- Optionally send Telegram message (future)

If worker crash:
- Systemd auto-restart
- Log CRITICAL

---

# VII. Monitoring Checklist

Daily quick check:

- [ ] Worker running
- [ ] Heartbeat fresh
- [ ] No orphan RUNNING jobs
- [ ] FAILED count low
- [ ] Logs readable

---

# VIII. Safe Restart Procedure

Before restart:

1. Stop worker
2. Ensure no RUNNING jobs
   If any:
      reset to PENDING

3. Restart worker

Never restart while adapter in middle of publish.

---

# IX. Resource Monitoring

Recommended:

- Memory usage
- CPU usage
- Browser instance count

Ensure:
- Only 1 Playwright context per job
- No orphan browser processes

---

# X. Degradation Modes

If repeated adapter failures:

- Auto-disable account
- Stop new jobs
- Log warning

Prevent infinite failure loop.

---

# XI. Stability Criteria

System considered stable when:

- Worker runs 48h without crash
- No memory leak
- No stuck RUNNING jobs
- Logs under control
- Restart safe

---

# Golden Rule

If something fails silently,
it is worse than failing loudly.

Always log explicitly.