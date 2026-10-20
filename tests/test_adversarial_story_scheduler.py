"""Adversarial stress-tests and edge-case challenge suite for Milestone 3 (Story Pacing Scheduler)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import JobStatus, JobType
from app.core.database.core import Base
from app.core.database.models import Job
from app.core.queue.publisher_runtime import postpone_if_weekly_story_limit
from app.features.story.scheduler import ICT, StoryPacingScheduler


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class TestAdversarialTimezoneAndCalendarEdges:
    """Stress-tests for timezone robustness, environment TZ changes, and calendar boundaries."""

    @pytest.mark.parametrize("fake_tz", ["UTC", "America/New_York", "Europe/London", "Asia/Tokyo"])
    def test_timezone_independence_under_foreign_env_tz(self, monkeypatch, fake_tz):
        """Scheduler must strictly use ICT (+07:00) regardless of the host machine's TZ."""
        monkeypatch.setenv("TZ", fake_tz)

        # 2026-10-19 11:30 ICT
        dt = datetime(2026, 10, 19, 11, 30, tzinfo=ICT)
        start_ts, end_ts = StoryPacingScheduler.get_week_bounds(dt)

        dt_start = datetime.fromtimestamp(start_ts, tz=ICT)
        dt_end = datetime.fromtimestamp(end_ts, tz=ICT)

        assert dt_start.strftime("%Y-%m-%d %H:%M:%S") == "2026-10-19 00:00:00"
        assert dt_end.strftime("%Y-%m-%d %H:%M:%S") == "2026-10-26 00:00:00"
        assert dt_start.utcoffset() == timedelta(hours=7)
        assert dt_end.utcoffset() == timedelta(hours=7)

    def test_naive_datetime_handling(self):
        """Naive datetime passed to get_week_bounds should be assumed ICT without raising."""
        naive_dt = datetime(2026, 10, 21, 14, 0, 0)
        start_ts, end_ts = StoryPacingScheduler.get_week_bounds(naive_dt)

        dt_start = datetime.fromtimestamp(start_ts, tz=ICT)
        assert dt_start.weekday() == 0  # Monday
        assert dt_start == datetime(2026, 10, 19, 0, 0, 0, tzinfo=ICT)

    def test_utc_aware_datetime_handling(self):
        """UTC datetime should be correctly converted to ICT before computing week bounds."""
        # 2026-10-18 20:00 UTC = 2026-10-19 03:00 ICT (Monday morning in ICT!)
        utc_dt = datetime(2026, 10, 18, 20, 0, 0, tzinfo=timezone.utc)
        start_ts, end_ts = StoryPacingScheduler.get_week_bounds(utc_dt)

        dt_start = datetime.fromtimestamp(start_ts, tz=ICT)
        assert dt_start.strftime("%Y-%m-%d") == "2026-10-19"
        assert dt_start.weekday() == 0

    def test_year_boundary_crossover(self):
        """ISO week crossing year boundary (e.g. 2026-12-31 to 2027-01-01) must have identical bounds."""
        # 2026-12-31 is Thursday
        dt_thu = datetime(2026, 12, 31, 15, 0, tzinfo=ICT)
        # 2027-01-01 is Friday
        dt_fri = datetime(2027, 1, 1, 10, 0, tzinfo=ICT)

        s_thu, e_thu = StoryPacingScheduler.get_week_bounds(dt_thu)
        s_fri, e_fri = StoryPacingScheduler.get_week_bounds(dt_fri)

        assert s_thu == s_fri
        assert e_thu == e_fri
        assert datetime.fromtimestamp(s_thu, tz=ICT) == datetime(2026, 12, 28, 0, 0, 0, tzinfo=ICT)
        assert datetime.fromtimestamp(e_thu, tz=ICT) == datetime(2027, 1, 4, 0, 0, 0, tzinfo=ICT)

    def test_leap_year_boundary(self):
        """Leap year February 29 (e.g. 2024-02-29 Thursday) bounds calculation."""
        dt_leap = datetime(2024, 2, 29, 11, 30, tzinfo=ICT)
        s_ts, e_ts = StoryPacingScheduler.get_week_bounds(dt_leap)

        assert datetime.fromtimestamp(s_ts, tz=ICT) == datetime(2024, 2, 26, 0, 0, 0, tzinfo=ICT)
        assert datetime.fromtimestamp(e_ts, tz=ICT) == datetime(2024, 3, 4, 0, 0, 0, tzinfo=ICT)


class TestAdversarialPacingAndSlotExhaustion:
    """Stress-tests for slot allocation under heavy saturation, multi-week rollovers, and boundary times."""

    def test_multi_week_consecutive_rollover(self, db_session):
        """When week 1 AND week 2 are both at full quota (10 stories each), allocation jumps to week 3."""
        page = "heavy_saturated_page"
        w1_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)
        jobs = []

        # Fill Week 1 (10 stories: Mon-Fri 11:30 & 20:00)
        for day in range(5):
            for h, m in ((11, 30), (20, 0)):
                ts = int((w1_monday + timedelta(days=day, hours=h, minutes=m)).timestamp())
                jobs.append(Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=ts))

        # Fill Week 2 (10 stories: Mon-Fri 11:30 & 20:00)
        w2_monday = w1_monday + timedelta(days=7)
        for day in range(5):
            for h, m in ((11, 30), (20, 0)):
                ts = int((w2_monday + timedelta(days=day, hours=h, minutes=m)).timestamp())
                jobs.append(Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.PENDING, schedule_ts=ts))

        db_session.add_all(jobs)
        db_session.commit()

        # Query slot starting at week 1 Monday 08:00
        start_ts = int((w1_monday + timedelta(hours=8)).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=start_ts)
        slot_dt = datetime.fromtimestamp(slot, tz=ICT)

        # Expected: Week 3 Monday 11:30 ICT (2026-11-02 11:30)
        w3_monday_1130 = datetime(2026, 11, 2, 11, 30, tzinfo=ICT)
        assert slot_dt == w3_monday_1130

    def test_exact_boundary_times(self, db_session):
        """Test after_ts landing exactly on a golden slot timestamp."""
        page = "page_boundary_exact"
        # Exactly 11:30:00 on Monday
        exact_1130 = int(datetime(2026, 10, 19, 11, 30, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=exact_1130)
        # Should allocate 20:00 of the same day (since 11:30 is not strictly > after_ts)
        assert datetime.fromtimestamp(slot, tz=ICT) == datetime(2026, 10, 19, 20, 0, 0, tzinfo=ICT)

        # Exactly 20:00:00 on Monday
        exact_2000 = int(datetime(2026, 10, 19, 20, 0, 0, tzinfo=ICT).timestamp())
        slot2 = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=exact_2000)
        # Should advance to Tuesday 11:30
        assert datetime.fromtimestamp(slot2, tz=ICT) == datetime(2026, 10, 20, 11, 30, 0, tzinfo=ICT)

    def test_partial_daily_occupation(self, db_session):
        """When 20:00 slot is occupied but 11:30 is free, request at 08:00 gets 11:30."""
        page = "page_partial_day"
        mon_2000 = int(datetime(2026, 10, 19, 20, 0, tzinfo=ICT).timestamp())
        db_session.add(Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.PENDING, schedule_ts=mon_2000))
        db_session.commit()

        mon_8am = int(datetime(2026, 10, 19, 8, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=mon_8am)
        assert datetime.fromtimestamp(slot, tz=ICT) == datetime(2026, 10, 19, 11, 30, tzinfo=ICT)

    def test_non_golden_hour_external_job_consumes_daily_limit(self, db_session):
        """If an external or manual job was scheduled at 14:00 and another at 18:00, that day has 2 jobs and is full."""
        page = "page_external_jobs"
        t1 = int(datetime(2026, 10, 19, 14, 0, tzinfo=ICT).timestamp())
        t2 = int(datetime(2026, 10, 19, 18, 0, tzinfo=ICT).timestamp())

        db_session.add_all([
            Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=t1),
            Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.PENDING, schedule_ts=t2),
        ])
        db_session.commit()

        mon_8am = int(datetime(2026, 10, 19, 8, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=mon_8am)
        # Monday already has 2 stories! Must skip to Tuesday 11:30
        assert datetime.fromtimestamp(slot, tz=ICT) == datetime(2026, 10, 20, 11, 30, tzinfo=ICT)


class TestAdversarialMediaCadence:
    """Stress-tests for alternating media cadence."""

    def test_query_params_and_complex_urls(self, db_session):
        """Media URLs with query parameters or mixed extensions."""
        page = "page_url_cadence"

        # MP4 with presigned URL parameters
        j1 = Job(
            account_id=1,
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.DONE,
            media_path="https://s3.amazonaws.com/bucket/highlight.mp4?X-Amz-Signature=abcd123",
        )
        db_session.add(j1)
        db_session.commit()

        # Last was mp4, next should be photo
        assert StoryPacingScheduler.get_next_media_mode(db_session, page) == "photo"

    def test_non_story_jobs_ignored_in_cadence(self, db_session):
        """POST and REEL jobs should NOT affect Story alternating cadence."""
        page = "page_mixed_types"

        # Story 1: Video
        j1 = Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.DONE, media_path="vid.mp4")
        # Post: Image
        j2 = Job(account_id=1, target_page=page, job_type=JobType.POST, status=JobStatus.DONE, media_path="post.jpg")
        # Feed: Video
        j3 = Job(account_id=1, target_page=page, job_type=JobType.FEED, status=JobStatus.DONE, media_path="feed.mp4")
        db_session.add_all([j1, j2, j3])
        db_session.commit()

        # Cadence must only look at JobType.STORY: last story was vid.mp4 -> should be photo!
        assert StoryPacingScheduler.get_next_media_mode(db_session, page) == "photo"


class TestAdversarialRuntimeGateAndClaim:
    """Stress-tests for publisher_runtime weekly gate under edge scenarios."""

    def test_postpone_preserves_unrelated_pending_jobs(self, db_session):
        """Verifies clear_claim_locks and atomic deferral without side effects."""
        page = "postpone_target"
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)
        now_ts = int(datetime(2026, 10, 23, 10, 0, tzinfo=ICT).timestamp())

        # 10 completed stories
        for i in range(10):
            ts = int((base_monday + timedelta(hours=i * 3)).timestamp())
            db_session.add(Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=ts))
        db_session.commit()

        # Claimed 11th job
        job11 = Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.RUNNING, schedule_ts=now_ts, locked_at=now_ts)
        db_session.add(job11)
        db_session.commit()

        assert postpone_if_weekly_story_limit(db_session, job11, now_ts=now_ts) is True
        db_session.refresh(job11)
        assert job11.status == JobStatus.PENDING
        assert job11.locked_at is None
        assert job11.schedule_ts == int(datetime(2026, 10, 26, 11, 30, tzinfo=ICT).timestamp())

    def test_postpone_empty_target_page_safe(self, db_session):
        """Jobs with empty or None target_page should be ignored gracefully without error."""
        job = Job(account_id=1, target_page=None, job_type=JobType.STORY, status=JobStatus.RUNNING)
        assert postpone_if_weekly_story_limit(db_session, job) is False

        job.target_page = "   "
        assert postpone_if_weekly_story_limit(db_session, job) is False
