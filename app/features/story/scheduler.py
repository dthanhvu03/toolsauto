"""Story pacing scheduler: golden hours allocation, weekly quota tracking, and alternating cadence."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as time_cls, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.constants import JobStatus, JobType
from app.core.database.models import Job

logger = logging.getLogger(__name__)

ICT = ZoneInfo("Asia/Ho_Chi_Minh")


class StoryPacingScheduler:
    WEEKLY_QUOTA: int = 10
    DAILY_LIMIT: int = 2
    GOLDEN_HOURS: tuple[tuple[int, int], ...] = ((11, 30), (20, 0))
    _schedule_lock: threading.RLock = threading.RLock()

    @classmethod
    def get_week_bounds(cls, moment: datetime | int | float | None = None) -> tuple[int, int]:
        """
        Returns (week_start_ts, week_end_ts) as unix epoch timestamps for the ISO calendar week
        (Monday 00:00:00 to Sunday 23:59:59 ICT; end timestamp is start of following Monday 00:00:00 ICT).
        """
        if moment is None:
            now = datetime.now(ICT)
        elif isinstance(moment, (int, float)):
            now = datetime.fromtimestamp(moment, tz=ICT)
        elif isinstance(moment, datetime):
            now = moment if moment.tzinfo is not None else moment.replace(tzinfo=ICT)
            now = now.astimezone(ICT)
        else:
            now = datetime.now(ICT)

        monday_date = now.date() - timedelta(days=now.weekday())
        week_start_dt = datetime.combine(monday_date, time_cls.min, tzinfo=ICT)
        following_monday_dt = week_start_dt + timedelta(days=7)
        return int(week_start_dt.timestamp()), int(following_monday_dt.timestamp())

    @classmethod
    def count_stories_in_week(
        cls,
        db: Session,
        target_page: str,
        moment: datetime | int | float | None = None,
    ) -> int:
        """
        Queries Job table in SQLite/SQLAlchemy for target_page, job_type == JobType.STORY,
        status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.DONE]),
        within current ISO week timestamps.
        """
        if not target_page:
            return 0
        start_ts, end_ts = cls.get_week_bounds(moment)
        return (
            db.query(Job)
            .filter(
                Job.target_page == target_page,
                Job.job_type == JobType.STORY,
                Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.DONE]),
                Job.schedule_ts.isnot(None),
                Job.schedule_ts >= start_ts,
                Job.schedule_ts < end_ts,
            )
            .count()
        )

    @classmethod
    def get_next_golden_slot(
        cls,
        db: Session,
        target_page: str,
        after_ts: int | None = None,
    ) -> int:
        """
        Finds the next valid unix epoch timestamp for a golden slot (11:30 or 20:00 ICT).
        - Default after_ts is current unix epoch timestamp (int(time.time())).
        - Finds existing story job timestamps for target_page.
        - Scans candidate calendar days starting from after_ts.
        - If a candidate day's ISO week already has 10 stories for target_page,
          jumps directly to the following Monday!
        - For a candidate day, checks golden slots (11:30 and 20:00 ICT):
          * Candidate slot timestamp T > after_ts.
          * Candidate slot T is not already taken by another scheduled/running/done story for this page.
          * The candidate day does not exceed DAILY_LIMIT (2 stories/day).
        - Returns the first valid unix epoch timestamp for the next golden slot.
        """
        with cls._schedule_lock:
            try:
                db.expire_all()
            except Exception:
                pass

            if after_ts is None:
                after_ts = int(time.time())

            # Existing occupied story timestamps for target_page
            existing_jobs = (
                db.query(Job.schedule_ts)
                .filter(
                    Job.target_page == target_page,
                    Job.job_type == JobType.STORY,
                    Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.DONE]),
                    Job.schedule_ts.isnot(None),
                )
                .all()
            )
            occupied_ts = {j[0] for j in existing_jobs}

            after_dt = datetime.fromtimestamp(after_ts, tz=ICT)
            current_date = after_dt.date()

            max_scan_days = 365
            days_scanned = 0

            while days_scanned < max_scan_days:
                # Check ISO week quota for candidate day
                candidate_moment = datetime.combine(current_date, time_cls(12, 0), tzinfo=ICT)
                week_count = cls.count_stories_in_week(db, target_page, candidate_moment)
                if week_count >= cls.WEEKLY_QUOTA:
                    # Jump directly to the following Monday
                    days_to_monday = 7 - current_date.weekday()
                    current_date = current_date + timedelta(days=days_to_monday)
                    days_scanned += days_to_monday
                    continue

                # Check daily limit for candidate day
                day_start = datetime.combine(current_date, time_cls.min, tzinfo=ICT)
                day_end = day_start + timedelta(days=1)
                day_start_ts = int(day_start.timestamp())
                day_end_ts = int(day_end.timestamp())

                day_count = sum(1 for ts in occupied_ts if day_start_ts <= ts < day_end_ts)
                if day_count >= cls.DAILY_LIMIT:
                    current_date += timedelta(days=1)
                    days_scanned += 1
                    continue

                # Check golden slots (11:30, 20:00)
                for hour, minute in cls.GOLDEN_HOURS:
                    slot_dt = datetime.combine(current_date, time_cls(hour, minute), tzinfo=ICT)
                    slot_ts = int(slot_dt.timestamp())
                    if slot_ts <= after_ts:
                        continue
                    if slot_ts in occupied_ts:
                        continue
                    return slot_ts

                current_date += timedelta(days=1)
                days_scanned += 1

            raise RuntimeError(f"Could not find available golden slot within {max_scan_days} days for page {target_page}")

    @classmethod
    def schedule_story(
        cls,
        db: Session,
        *,
        account_id: int,
        target_page: str,
        media_path: str,
        caption: str = "",
        viral_material_id: int | None = None,
        schedule_ts: int | None = None,
        platform: str = "facebook",
    ) -> Job:
        """
        Schedules a story job:
        - If schedule_ts is None, calls get_next_golden_slot(db, target_page).
        - Creates and adds Job(platform=platform, account_id=account_id, target_page=target_page,
          media_path=media_path, caption=caption, viral_material_id=viral_material_id,
          job_type=JobType.STORY, schedule_ts=schedule_ts, status=JobStatus.PENDING).
        - Commits, refreshes, and returns the created Job.
        """
        with cls._schedule_lock:
            try:
                db.expire_all()
            except Exception:
                pass

            if schedule_ts is None:
                schedule_ts = cls.get_next_golden_slot(db, target_page)

            job = Job(
                platform=platform,
                account_id=account_id,
                target_page=target_page,
                media_path=media_path,
                caption=caption,
                viral_material_id=viral_material_id,
                job_type=JobType.STORY,
                schedule_ts=schedule_ts,
                status=JobStatus.PENDING,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job

    @classmethod
    def get_next_media_mode(cls, db: Session, target_page: str) -> str:
        """
        Queries the most recent Story job for target_page.
        If the last story was video (.mp4), returns 'photo'.
        If photo (.jpg, .jpeg, .png, .webp), returns 'video'.
        If none found, returns 'video'.
        """
        last_job = (
            db.query(Job)
            .filter(
                Job.target_page == target_page,
                Job.job_type == JobType.STORY,
            )
            .order_by(Job.id.desc())
            .first()
        )
        if not last_job:
            return "video"

        media = (
            getattr(last_job, "processed_media_path", None)
            or getattr(last_job, "media_path", None)
            or ""
        ).strip().lower()

        if media.endswith(".mp4") or ".mp4" in media:
            return "photo"
        if any(media.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
            return "video"
        return "video"
