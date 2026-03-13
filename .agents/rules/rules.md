---
trigger: always_on
---

# AI Assistant Database Discipline Rules

## CRITICAL INSTRUCTION: NON-DESTRUCTIVE DB OPERATIONS

The AI Assistant must **NEVER** perform destructive SQL operations on production database files (`data/auto_publisher.db`, `data/automation.db`).

1. **PROHIBITED ACTIONS:**
   - `DELETE FROM ...`
   - `DROP TABLE ...`
   - `TRUNCATE TABLE ...`
   - `db.query(Model).delete()` via SQLAlchemy on real database connections.
   - Using `.schema` and then overwriting tables.
2. **TESTING PROTOCOLS:**
   - Any standalone script or Python shell test written to verify logic MUST use an in-memory database (`sqlite:///:memory:`) OR a temporary isolated file (`/tmp/mocker_db.sqlite`).
   - If a test absolutely requires inspecting or inserting data into the REAL database file, all operations MUST be wrapped in a transaction blocks, and MUST conclude with `db.rollback()` instead of `db.commit()`.
3. **ENFORCEMENT:**
   - Always run a `SELECT count(*)` before and after structural queries to verify data retention.
   - If the User asks to clean up data, confirm the exact query and wait for User Approval before executing the command.
     Do NOT deviate from these rules under any circumstances. Failure to comply violates the "Personal-Stable" operational guarantee.

## CRITICAL INSTRUCTION: IMPORT SCOPE DISCIPLINE

To prevent Python `UnboundLocalError`:

- NEVER place `import X` inside an `if` block or loop inside a function if `X` is used anywhere else in that same function.
- Python treats any `import` (or assignment) inside a function as making that variable **local** to the entire function scope.
- **Rule of thumb**: Place all function-level dynamic imports at the very **top** of the function, before any logic.

---

## CRITICAL INSTRUCTION: WORKER STABILITY & PROCESS SAFETY

To prevent silent crashes and unrecoverable worker states:

1. **EXCEPTION HANDLING:**
   - Every worker main loop MUST have a top-level `try/except Exception as e` that catches all errors.
   - Never let an unhandled exception kill a worker silently. Always log before exiting.
   - Use this pattern in all workers:
     ```python
     while True:
         try:
             # worker logic
         except Exception as e:
             logger.error(f"[WorkerName] Unhandled error: {e}", exc_info=True)
             time.sleep(30)  # backoff before retry
             continue
     ```

2. **JOB STATE INTEGRITY:**
   - A job must NEVER be left in `PROCESSING` state if a worker crashes.
   - On worker startup, scan for jobs stuck in `PROCESSING` and reset them to `PENDING` or `FAILED`.
   - Pattern:
     ```python
     # On startup
     db.query(Job).filter(Job.status == "PROCESSING").update({"status": "PENDING"})
     db.commit()
     ```

3. **GRACEFUL SHUTDOWN:**
   - All workers must handle `SIGTERM` and `SIGINT` signals.
   - On shutdown signal: finish current task, then exit cleanly. Never kill mid-write.

---

## CRITICAL INSTRUCTION: BROWSER AUTOMATION SAFETY (Playwright / Selenium / Undetected Chrome)

To prevent browser sessions leaking and accounts getting flagged:

1. **ALWAYS close browser instances** in a `finally` block, never rely on garbage collection:

   ```python
   driver = None
   try:
       driver = start_browser()
       # automation logic
   finally:
       if driver:
           driver.quit()
   ```

2. **ONE BROWSER PER ACCOUNT** — never reuse a browser instance across different Facebook accounts.

3. **TIMEOUT ON EVERY ACTION:**
   - Every `find_element`, `click`, `send_keys` MUST have an explicit timeout (max 30s).
   - Never use implicit infinite waits. Use `WebDriverWait(driver, 30)`.

4. **SCREENSHOT ON FAILURE:**
   - When any browser action fails, auto-save a screenshot to `/logs/screenshots/[timestamp]_[account_id].png`.
   - This is mandatory for debugging without watching the screen.

5. **PROHIBITED:**
   - Never hardcode `time.sleep(X)` with fixed values for human simulation.
   - Always use `time.sleep(random.uniform(min, max))` to mimic real behavior.

---

## CRITICAL INSTRUCTION: GEMINI RPA FRAGILITY MANAGEMENT

The Gemini RPA module (`gemini_rpa.py`) is the most fragile component. Apply these rules strictly:

1. **DOM SELECTORS:**
   - Never hardcode a single CSS class selector. Always define selectors in a config dict at the top of the file:
     ```python
     GEMINI_SELECTORS = {
         "response_text": "model-response-text",  # UPDATE HERE if Google changes
         "input_box": "ql-editor",
         "submit_btn": "send-button",
     }
     ```
   - When Google updates the UI, only this dict needs changing — not scattered throughout the code.

2. **RETRY DISCIPLINE:**
   - Max 3 retries per Gemini call, with 30s delay between attempts.
   - After 3 failures: set job status = `FAILED`, notify Telegram, do NOT retry again automatically.

3. **SESSION VALIDATION:**
   - Before every Gemini call, verify the session is alive by checking for a known DOM element.
   - If session is expired (cookie invalid), notify Telegram immediately with message:
     `"⚠️ Gemini session expired. Please refresh cookies manually."`
   - Do NOT attempt to auto-login to Google accounts.

4. **FALLBACK AWARENESS:**
   - If Gemini RPA fails 3 times in a row across multiple jobs, set a global flag `GEMINI_CIRCUIT_OPEN = True`.
   - While circuit is open, skip AI generation and notify user every 1 hour until manually reset.

---

## CRITICAL INSTRUCTION: CONCURRENT ACCOUNT MANAGEMENT

To protect Facebook accounts from bulk bans when running on a single IP:

1. **HARD LIMIT:**
   - `MAX_CONCURRENT_ACCOUNTS = 2` is the default. Never exceed this without explicit User confirmation.
   - This value must live in a single config location (e.g., `config.py` or `.env`), never scattered in code.

2. **QUEUE DISCIPLINE:**
   - Jobs waiting for an account slot MUST stay in `QUEUED` status, never `PENDING` confusion.
   - Queue order: FIFO (first in, first out). No job skipping.

3. **INTER-ACTION DELAYS:**
   - Minimum delay between posts from the same account: 30 minutes.
   - Delay between switching accounts: `random.uniform(30, 90)` seconds.
   - Never post from 2 accounts within the same 10-second window.

4. **PROHIBITED:**
   - Never run the same account in 2 browser instances simultaneously.
   - Never share cookies/session files between accounts.

---

## CRITICAL INSTRUCTION: LOGGING STANDARDS

Consistent logs are critical for a solo developer maintaining this system:

1. **LOG FORMAT** — every log line must include:

   ```
   [TIMESTAMP] [WORKER_NAME] [JOB_ID] [LEVEL] Message
   # Example:
   [2026-03-08 02:15:33] [Publisher] [JOB-042] [INFO] Starting post for account fb_acc_01
   [2026-03-08 02:15:45] [Publisher] [JOB-042] [ERROR] Checkpoint detected, screenshot saved
   ```

2. **LOG ROTATION:**
   - Max log file size: 10MB. Keep last 5 rotated files.
   - Use `logging.handlers.RotatingFileHandler`, never plain `open()` for logs.

3. **PROHIBITED:**
   - Never use `print()` for operational logging. Use the `logger` instance.
   - Never log sensitive data: cookies, passwords, API keys, phone numbers.

---

## CRITICAL INSTRUCTION: FILE & MEDIA HYGIENE

To prevent disk space exhaustion on local machine:

1. **TEMP FILES:**
   - All downloaded videos, extracted audio, and frame images are TEMP files.
   - They MUST be deleted after the job completes (success or failure).
   - Use `try/finally` to guarantee cleanup:
     ```python
     try:
         process_video(temp_path)
     finally:
         if os.path.exists(temp_path):
             os.remove(temp_path)
     ```

2. **STORAGE LIMITS:**
   - If free disk space drops below 2GB, pause all new jobs and notify Telegram:
     `"⚠️ Low disk space: [X]GB remaining. New jobs paused."`
   - Check disk space at the start of every job.

3. **MEDIA FOLDER STRUCTURE** — never dump files to root:
   ```
   /media/
     /downloads/     ← raw downloaded videos (delete after processing)
     /processed/     ← edited videos ready to publish (delete after publish)
     /thumbnails/    ← collage images (delete after publish)
   /logs/
     /screenshots/   ← browser failure screenshots (keep 7 days)
   ```

---

## QUICK REFERENCE: WHAT AI MUST ALWAYS DO

| Situation                          | Required Action                          |
| ---------------------------------- | ---------------------------------------- |
| Worker crashes                     | Log error + sleep 30s + restart loop     |
| Job stuck in PROCESSING on startup | Reset to PENDING                         |
| Gemini DOM not found               | Retry 3x → FAILED + Telegram alert       |
| Browser action fails               | Screenshot + log + close browser cleanly |
| Disk < 2GB                         | Pause jobs + Telegram alert              |
| User asks to DELETE data           | Confirm query + wait for approval        |
| Adding new selector                | Add to config dict, not hardcoded        |
| Writing test with DB               | Use `:memory:` or `/tmp/` only           |

## QUICK REFERENCE: WHAT AI MUST NEVER DO

| Prohibited                         | Reason                             |
| ---------------------------------- | ---------------------------------- |
| `DELETE FROM` on production DB     | Data loss, unrecoverable           |
| Fixed `time.sleep()` for human sim | Detectable pattern by Meta         |
| Reuse browser across accounts      | Account linkage, ban risk          |
| Leave job in `PROCESSING` on crash | Queue deadlock                     |
| Log cookies or passwords           | Security risk                      |
| Hardcode DOM selectors inline      | Unmaintainable when Google updates |
| Run >2 accounts concurrently       | IP-based ban chùm risk             |
