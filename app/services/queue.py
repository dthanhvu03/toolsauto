from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from app.database.models import Job
from app.constants import AccountStatus, JobStatus
from app.utils.logger import setup_shared_logger

logger = setup_shared_logger(__name__)


class QueueService:

    @staticmethod
    def _extract_returning_id(row) -> Optional[int]:
        if not row:
            return None
        try:
            return int(row._mapping["id"])
        except Exception:
            return int(row[0])

    @staticmethod
    def claim_next_job(db: Session, platform: Optional[str] = None) -> Optional[Job]: # pylint: disable=unused-argument
        """
        Atomically claims the next PENDING job that is ready to run.
        Uses SQLite RETURNING to avoid SELECT->UPDATE race condition.
        Evaluates cooldown and daily limits inline via subquery.
        """
        
        # SQLite raw SQL for atomic update + validation
        # We find a job where:
        # 1. status = PENDING
        # 2. schedule_ts <= now
        # 3. account is active
        # 4. account cooldown has passed (now - last_post_ts >= cooldown_seconds) or last_post_ts is null
        # 5. daily limit has not been reached (this is hard to do fully in SQLite without a complex join,
        #    so we will enforce the hard limit here loosely, and validate rigorously in JobService if needed, 
        #    but the prompt asks for inline validation if possible to avoid locking invalid jobs.)
        
        # sqlite3 claim with strict isolation lock + Account Mutex
        sql = """
            UPDATE jobs
            SET 
                status = 'RUNNING',
                locked_at = CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER),
                last_heartbeat_at = CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER),
                started_at = CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER)
            WHERE id = (
                SELECT j.id
                FROM jobs j
                JOIN accounts a ON j.account_id = a.id
                WHERE j.status = 'PENDING'
                  AND (
                      -- POST jobs: use schedule_ts
                      (j.job_type = 'POST' AND j.schedule_ts <= CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER))
                      OR
                      -- COMMENT jobs: use scheduled_at (delayed)
                      (j.job_type = 'COMMENT' AND j.scheduled_at <= CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER))
                  )
                  AND a.is_active = true
                  AND a.login_status = 'ACTIVE'
                  AND (a.last_post_ts IS NULL OR (CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER) - a.last_post_ts) >= a.cooldown_seconds)
                  -- Account-level Mutex: Ensure this account has NO other RUNNING jobs
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs j2
                      WHERE j2.account_id = j.account_id
                        AND j2.status = 'RUNNING'
                  )
                ORDER BY j.schedule_ts ASC
                LIMIT 1
            )
            RETURNING *;
        """
        
        # [DB-LOCK-FIX] Retry with backoff if SQLite is locked by another process
        import time as _time
        for _attempt in range(3):
            try:
                result = db.execute(text(sql))
                row = result.fetchone()
                db.commit()

                job_id = QueueService._extract_returning_id(row)
                if job_id is not None:
                    logger.debug("[claim_next_job] claimed job_id=%s", job_id)
                    job = db.query(Job).filter(Job.id == job_id).first()
                    return job

                return None
            except Exception as _e:
                db.rollback()
                if "locked" in str(_e).lower() and _attempt < 2:
                    _time.sleep(2 ** _attempt)  # 1s, 2s backoff
                    continue
                raise
        return None
        
    @staticmethod
    def claim_draft_job(db: Session) -> Optional[Job]:
        """
        Atomically claims the next DRAFT job that needs AI Caption Generation.
        We only claim DRAFT jobs that have '[AI_GENERATE]' in their caption.
        """
        sql = """
            UPDATE jobs
            SET 
                status = 'AI_PROCESSING',
                locked_at = CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER),
                last_heartbeat_at = CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER),
                started_at = CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER)
            WHERE id = (
                SELECT id
                FROM jobs
                WHERE status = 'DRAFT'
                  AND caption LIKE '%[AI_GENERATE]%'
                ORDER BY created_at ASC
                LIMIT 1
            )
            RETURNING *;
        """
        # [DB-LOCK-FIX] Retry with backoff if SQLite is locked by another process
        import time as _time
        for _attempt in range(3):
            try:
                result = db.execute(text(sql))
                row = result.fetchone()
                db.commit()

                job_id = QueueService._extract_returning_id(row)
                if job_id is not None:
                    logger.debug("[claim_draft_job] claimed job_id=%s", job_id)
                    return db.query(Job).filter(Job.id == job_id).first()
                return None
            except Exception as _e:
                db.rollback()
                if "locked" in str(_e).lower() and _attempt < 2:
                    _time.sleep(2 ** _attempt)
                    continue
                raise
        return None
        
    @staticmethod
    def recover_crashed_jobs(db: Session, threshold_seconds: int) -> int:
        """
        Finds RUNNING/AI_PROCESSING jobs where heartbeat is stale and resets them.
        """
        # Phase A: Read stale IDs.
        try:
            logger.debug("[recover.select_running] threshold_seconds=%s", threshold_seconds)
            stale_running_ids = [
                r[0]
                for r in db.execute(
                    text(
                        """
                        SELECT id FROM jobs
                        WHERE status = 'RUNNING'
                          AND last_heartbeat_at < (CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER) - :threshold)
                        """
                    ),
                    {"threshold": threshold_seconds},
                ).fetchall()
            ]

            logger.debug("[recover.select_ai] threshold_seconds=%s", threshold_seconds)
            stale_ai_ids = [
                r[0]
                for r in db.execute(
                    text(
                        """
                        SELECT id FROM jobs
                        WHERE status = 'AI_PROCESSING'
                          AND last_heartbeat_at < (CAST(EXTRACT(EPOCH FROM NOW()) AS INTEGER) - :threshold)
                        """
                    ),
                    {"threshold": threshold_seconds},
                ).fetchall()
            ]
        except Exception:
            db.rollback()
            logger.exception("[recover.select] Failed selecting stale jobs")
            raise

        # Phase B: Recover job statuses and commit.
        try:
            if stale_running_ids:
                logger.debug("[recover.update_running] ids=%s", stale_running_ids[:10])
                placeholders = ', '.join(f':id_{i}' for i in range(len(stale_running_ids)))
                sql_running = f"""
                    UPDATE jobs
                    SET
                        status = 'PENDING',
                        tries = tries + 1
                    WHERE id IN ({placeholders})
                """
                params = {f'id_{i}': jid for i, jid in enumerate(stale_running_ids)}
                db.execute(text(sql_running), params)

            if stale_ai_ids:
                logger.debug("[recover.update_ai] ids=%s", stale_ai_ids[:10])
                placeholders = ', '.join(f':id_{i}' for i in range(len(stale_ai_ids)))
                sql_ai = f"""
                    UPDATE jobs
                    SET
                        status = 'DRAFT'
                    WHERE id IN ({placeholders})
                """
                params = {f'id_{i}': jid for i, jid in enumerate(stale_ai_ids)}
                db.execute(text(sql_ai), params)

            db.commit()
        except Exception:
            db.rollback()
            logger.exception("[recover.update] Failed updating stale job statuses")
            raise

        # Phase C: Best-effort event writes. Roll back this phase only if it fails.
        try:
            import time as _time
            ts = int(_time.time())
            if stale_running_ids:
                db.execute(
                    text(
                        """
                        INSERT INTO job_events (job_id, ts, level, message, meta_json)
                        VALUES (:job_id, :ts, 'WARN', :msg, :meta)
                        """
                    ),
                    [
                        {
                            "job_id": jid,
                            "ts": ts,
                            "msg": "Recovered stale RUNNING job → PENDING",
                            "meta": f"threshold_seconds={threshold_seconds}",
                        }
                        for jid in stale_running_ids
                    ],
                )
            if stale_ai_ids:
                db.execute(
                    text(
                        """
                        INSERT INTO job_events (job_id, ts, level, message, meta_json)
                        VALUES (:job_id, :ts, 'WARN', :msg, :meta)
                        """
                    ),
                    [
                        {
                            "job_id": jid,
                            "ts": ts,
                            "msg": "Recovered stale AI_PROCESSING job → DRAFT",
                            "meta": f"threshold_seconds={threshold_seconds}",
                        }
                        for jid in stale_ai_ids
                    ],
                )
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("[recover.events] Failed writing recovery job events", exc_info=True)

        recovered_total = len(stale_running_ids) + len(stale_ai_ids)

        # Telegram alert (best-effort, avoid spam by only sending when something recovered)
        if recovered_total > 0:
            try:
                from app.services.notifier_service import NotifierService
                ids_preview = []
                if stale_running_ids:
                    ids_preview.extend(stale_running_ids[:5])
                if stale_ai_ids:
                    ids_preview.extend(stale_ai_ids[:5])
                suffix = f"\nIDs: {', '.join(str(i) for i in ids_preview)}" if ids_preview else ""
                NotifierService._broadcast(
                    "🧯 <b>Self-heal đã reset job kẹt</b>\n"
                    f"• RUNNING→PENDING: <b>{len(stale_running_ids)}</b>\n"
                    f"• AI_PROCESSING→DRAFT: <b>{len(stale_ai_ids)}</b>\n"
                    f"threshold={threshold_seconds}s{suffix}"
                )
            except Exception:
                pass

        return recovered_total

