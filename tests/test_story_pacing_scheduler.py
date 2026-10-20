"""Unit tests for Milestone 3: Story Pacing Scheduler, Weekly Quota, Runtime Gate, and Buffer Story Wiring."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import JobStatus, JobType
from app.core.database.core import Base
from app.core.database.models import Account, Job
from app.core.queue.publisher_runtime import (
    claim_next_job_respecting_daily,
    postpone_if_daily_limit,
    postpone_if_weekly_story_limit,
)
from app.features.buffer.adapter import BufferAdapter
from app.features.story.scheduler import ICT, StoryPacingScheduler


@pytest.fixture
def db_session():
    """In-memory SQLite session with all models created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class TestWeekBoundsAndConstants:
    """Tests for ISO week bounds calculations and scheduler constants."""

    def test_constants_values(self):
        assert StoryPacingScheduler.WEEKLY_QUOTA == 10
        assert StoryPacingScheduler.DAILY_LIMIT == 2
        assert StoryPacingScheduler.GOLDEN_HOURS == ((11, 30), (20, 0))
        assert ICT.key == "Asia/Ho_Chi_Minh"

    def test_get_week_bounds_from_monday(self):
        # 2026-10-19 is a Monday
        dt = datetime(2026, 10, 19, 11, 30, tzinfo=ICT)
        start_ts, end_ts = StoryPacingScheduler.get_week_bounds(dt)

        start_dt = datetime.fromtimestamp(start_ts, tz=ICT)
        end_dt = datetime.fromtimestamp(end_ts, tz=ICT)

        assert start_dt == datetime(2026, 10, 19, 0, 0, 0, tzinfo=ICT)
        assert end_dt == datetime(2026, 10, 26, 0, 0, 0, tzinfo=ICT)
        assert end_ts - start_ts == 7 * 86400

    def test_get_week_bounds_from_sunday_boundary(self):
        # 2026-10-25 is Sunday
        dt_sunday = datetime(2026, 10, 25, 23, 59, 59, tzinfo=ICT)
        start_ts, end_ts = StoryPacingScheduler.get_week_bounds(dt_sunday)

        start_dt = datetime.fromtimestamp(start_ts, tz=ICT)
        end_dt = datetime.fromtimestamp(end_ts, tz=ICT)

        assert start_dt == datetime(2026, 10, 19, 0, 0, 0, tzinfo=ICT)
        assert end_dt == datetime(2026, 10, 26, 0, 0, 0, tzinfo=ICT)

    def test_get_week_bounds_from_timestamp_and_none(self):
        dt = datetime(2026, 10, 21, 15, 0, tzinfo=ICT)
        start_ts, end_ts = StoryPacingScheduler.get_week_bounds(dt.timestamp())
        assert datetime.fromtimestamp(start_ts, tz=ICT).weekday() == 0

        # None uses current time
        s_now, e_now = StoryPacingScheduler.get_week_bounds(None)
        assert e_now - s_now == 7 * 86400


class TestGoldenSlotAllocation:
    """Tests for golden hours slot allocation (11:30 and 20:00 ICT)."""

    def test_allocates_11_30_and_20_00_slots(self, db_session):
        page = "test_fanpage_slots"
        # Start at Monday morning 08:00 ICT
        monday_8am = int(datetime(2026, 10, 19, 8, 0, tzinfo=ICT).timestamp())
        slot1 = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=monday_8am)
        dt1 = datetime.fromtimestamp(slot1, tz=ICT)
        assert dt1 == datetime(2026, 10, 19, 11, 30, tzinfo=ICT)

        # After 11:30, slot should be 20:00 of same day
        slot2 = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=slot1)
        dt2 = datetime.fromtimestamp(slot2, tz=ICT)
        assert dt2 == datetime(2026, 10, 19, 20, 0, tzinfo=ICT)

        # After 20:00, slot should be next day 11:30
        slot3 = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=slot2)
        dt3 = datetime.fromtimestamp(slot3, tz=ICT)
        assert dt3 == datetime(2026, 10, 20, 11, 30, tzinfo=ICT)

    def test_daily_limit_advances_to_next_day(self, db_session):
        page = "test_fanpage_daily"
        # Populate Monday with 2 stories (11:30 and 20:00)
        t_mon_1130 = int(datetime(2026, 10, 19, 11, 30, tzinfo=ICT).timestamp())
        t_mon_2000 = int(datetime(2026, 10, 19, 20, 0, tzinfo=ICT).timestamp())

        db_session.add_all([
            Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=t_mon_1130),
            Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.PENDING, schedule_ts=t_mon_2000),
        ])
        db_session.commit()

        # Asking for a slot on Monday at 08:00 must skip Monday and return Tuesday 11:30
        monday_8am = int(datetime(2026, 10, 19, 8, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=monday_8am)
        dt = datetime.fromtimestamp(slot, tz=ICT)
        assert dt == datetime(2026, 10, 20, 11, 30, tzinfo=ICT)

    def test_weekly_quota_rollover_to_next_monday(self, db_session):
        page = "test_fanpage_weekly_rollover"
        # Schedule 10 stories from Monday to Friday (2 per day)
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)
        jobs = []
        for day in range(5):
            for h, m in ((11, 30), (20, 0)):
                ts = int((base_monday + timedelta(days=day, hours=h, minutes=m)).timestamp())
                jobs.append(
                    Job(
                        account_id=1,
                        target_page=page,
                        job_type=JobType.STORY,
                        status=JobStatus.PENDING,
                        schedule_ts=ts,
                    )
                )
        db_session.add_all(jobs)
        db_session.commit()

        assert StoryPacingScheduler.count_stories_in_week(db_session, page, base_monday) == 10

        # Now requesting slot on Wednesday 15:00 should roll over to next Monday 11:30!
        wed_1500 = int(datetime(2026, 10, 21, 15, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=wed_1500)
        dt = datetime.fromtimestamp(slot, tz=ICT)

        next_monday_1130 = datetime(2026, 10, 26, 11, 30, tzinfo=ICT)
        assert dt == next_monday_1130

    def test_page_isolation_for_weekly_quota(self, db_session):
        page_a = "page_alpha"
        page_b = "page_beta"

        # Page A fills all 10 slots
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)
        jobs_a = []
        for day in range(5):
            for h, m in ((11, 30), (20, 0)):
                ts = int((base_monday + timedelta(days=day, hours=h, minutes=m)).timestamp())
                jobs_a.append(
                    Job(account_id=1, target_page=page_a, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=ts)
                )
        db_session.add_all(jobs_a)
        db_session.commit()

        start_ts = int(datetime(2026, 10, 19, 8, 0, tzinfo=ICT).timestamp())

        # Page A gets rolled over to next Monday
        slot_a = StoryPacingScheduler.get_next_golden_slot(db_session, page_a, after_ts=start_ts)
        assert datetime.fromtimestamp(slot_a, tz=ICT) == datetime(2026, 10, 26, 11, 30, tzinfo=ICT)

        # Page B has 0 slots used, so it receives Monday 11:30 of current week!
        slot_b = StoryPacingScheduler.get_next_golden_slot(db_session, page_b, after_ts=start_ts)
        assert datetime.fromtimestamp(slot_b, tz=ICT) == datetime(2026, 10, 19, 11, 30, tzinfo=ICT)

    def test_sunday_night_advances_to_next_monday(self, db_session):
        page = "page_sunday_night"
        # Sunday 20:00 ICT
        sunday_2000 = int(datetime(2026, 10, 25, 20, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=sunday_2000)
        dt = datetime.fromtimestamp(slot, tz=ICT)
        assert dt == datetime(2026, 10, 26, 11, 30, tzinfo=ICT)

    def test_failed_or_cancelled_jobs_do_not_exhaust_quota(self, db_session):
        page = "page_failed_jobs"
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)

        # 10 FAILED and CANCELLED jobs
        failed_jobs = []
        for i in range(10):
            ts = int((base_monday + timedelta(hours=i)).timestamp())
            failed_jobs.append(
                Job(
                    account_id=1,
                    target_page=page,
                    job_type=JobType.STORY,
                    status=JobStatus.FAILED if i % 2 == 0 else JobStatus.CANCELLED,
                    schedule_ts=ts,
                )
            )
        db_session.add_all(failed_jobs)
        db_session.commit()

        # Count in week should be 0 because status is FAILED/CANCELLED
        assert StoryPacingScheduler.count_stories_in_week(db_session, page, base_monday) == 0

        # Slot should still be allocated in current week
        start_ts = int(datetime(2026, 10, 19, 8, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=start_ts)
        assert datetime.fromtimestamp(slot, tz=ICT) == datetime(2026, 10, 19, 11, 30, tzinfo=ICT)


class TestMediaCadenceAndScheduleStory:
    """Tests for alternating media cadence (video -> photo) and schedule_story."""

    def test_alternating_media_cadence(self, db_session):
        page = "cadence_page"

        # Empty history defaults to video
        assert StoryPacingScheduler.get_next_media_mode(db_session, page) == "video"

        # Add video story
        j1 = Job(
            account_id=1,
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.DONE,
            media_path="/storage/media/stories/highlight_1.mp4",
        )
        db_session.add(j1)
        db_session.commit()
        assert StoryPacingScheduler.get_next_media_mode(db_session, page) == "photo"

        # Add photo story
        j2 = Job(
            account_id=1,
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.DONE,
            media_path="/storage/media/stories/cover_2.jpg",
        )
        db_session.add(j2)
        db_session.commit()
        assert StoryPacingScheduler.get_next_media_mode(db_session, page) == "video"

        # Add another photo with .png
        j3 = Job(
            account_id=1,
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.PENDING,
            processed_media_path="/storage/media/stories/cover_3.png",
        )
        db_session.add(j3)
        db_session.commit()
        assert StoryPacingScheduler.get_next_media_mode(db_session, page) == "video"

        # Add video with .mp4
        j4 = Job(
            account_id=1,
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.PENDING,
            media_path="/storage/media/stories/highlight_4.mp4",
        )
        db_session.add(j4)
        db_session.commit()
        assert StoryPacingScheduler.get_next_media_mode(db_session, page) == "photo"

    def test_schedule_story_creates_and_commits_job(self, db_session):
        page = "page_scheduled"
        account = Account(id=1, name="Acc1", platform="facebook", is_active=True, login_status="ACTIVE")
        db_session.add(account)
        db_session.commit()

        job = StoryPacingScheduler.schedule_story(
            db_session,
            account_id=1,
            target_page=page,
            media_path="/storage/media/stories/story_video.mp4",
            caption="Story Caption Test",
            viral_material_id=42,
        )

        assert job.id is not None
        assert job.job_type == JobType.STORY
        assert job.status == JobStatus.PENDING
        assert job.target_page == page
        assert job.media_path == "/storage/media/stories/story_video.mp4"
        assert job.caption == "Story Caption Test"
        assert job.viral_material_id == 42
        assert job.schedule_ts > 0

        # Verify golden slot hour/minute
        slot_dt = datetime.fromtimestamp(job.schedule_ts, tz=ICT)
        assert (slot_dt.hour, slot_dt.minute) in ((11, 30), (20, 0))

    def test_schedule_story_honors_explicit_schedule_ts(self, db_session):
        page = "page_explicit_ts"
        explicit_ts = 1799999999
        job = StoryPacingScheduler.schedule_story(
            db_session,
            account_id=1,
            target_page=page,
            media_path="/storage/media/stories/photo.jpg",
            schedule_ts=explicit_ts,
        )
        assert job.schedule_ts == explicit_ts


class TestPublisherRuntimeWeeklyStoryLimit:
    """Tests for postpone_if_weekly_story_limit runtime gate in publisher_runtime.py."""

    def test_postpone_ignores_non_story_jobs(self, db_session):
        job = Job(id=1, target_page="page1", job_type=JobType.POST, status=JobStatus.RUNNING)
        db_session.add(job)
        db_session.commit()

        assert postpone_if_weekly_story_limit(db_session, job) is False

    def test_postpone_ignores_story_when_under_quota(self, db_session):
        job = Job(id=1, target_page="page1", job_type=JobType.STORY, status=JobStatus.RUNNING)
        db_session.add(job)
        db_session.commit()

        # 0 stories done/scheduled
        assert postpone_if_weekly_story_limit(db_session, job) is False

    def test_postpone_defers_when_quota_exhausted(self, db_session):
        page = "page_over_quota"
        # Current week Monday 2026-10-19
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)
        now_ts = int(datetime(2026, 10, 22, 14, 0, tzinfo=ICT).timestamp())

        # Insert 10 DONE stories in current week
        done_jobs = []
        for i in range(10):
            ts = int((base_monday + timedelta(hours=i * 2 + 10)).timestamp())
            done_jobs.append(
                Job(
                    account_id=1,
                    target_page=page,
                    job_type=JobType.STORY,
                    status=JobStatus.DONE,
                    schedule_ts=ts,
                    finished_at=ts,
                )
            )
        db_session.add_all(done_jobs)
        db_session.commit()

        # The claimed 11th story
        eleventh_job = Job(
            account_id=1,
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.RUNNING,
            schedule_ts=now_ts,
            locked_at=now_ts,
            started_at=now_ts,
        )
        db_session.add(eleventh_job)
        db_session.commit()

        result = postpone_if_weekly_story_limit(db_session, eleventh_job, now_ts=now_ts)
        assert result is True

        # Check postponed attributes
        db_session.refresh(eleventh_job)
        assert eleventh_job.status == JobStatus.PENDING
        assert eleventh_job.locked_at is None
        assert eleventh_job.started_at is None

        # Defers to next Monday 11:30 ICT
        next_monday_1130 = int(datetime(2026, 10, 26, 11, 30, tzinfo=ICT).timestamp())
        assert eleventh_job.schedule_ts == next_monday_1130

    def test_postpone_page_isolation(self, db_session):
        page_a = "page_full"
        page_b = "page_free"
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)
        now_ts = int(datetime(2026, 10, 21, 12, 0, tzinfo=ICT).timestamp())

        # Page A has 10 DONE jobs
        for i in range(10):
            ts = int((base_monday + timedelta(hours=i * 2)).timestamp())
            db_session.add(
                Job(account_id=1, target_page=page_a, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=ts)
            )
        db_session.commit()

        job_a = Job(account_id=1, target_page=page_a, job_type=JobType.STORY, status=JobStatus.RUNNING, schedule_ts=now_ts)
        job_b = Job(account_id=1, target_page=page_b, job_type=JobType.STORY, status=JobStatus.RUNNING, schedule_ts=now_ts)
        db_session.add_all([job_a, job_b])
        db_session.commit()

        # Page A job postponed
        assert postpone_if_weekly_story_limit(db_session, job_a, now_ts=now_ts) is True
        # Page B job NOT postponed
        assert postpone_if_weekly_story_limit(db_session, job_b, now_ts=now_ts) is False

    def test_claim_next_job_respecting_daily_skips_postponed_story(self, db_session):
        logger = logging.getLogger("test_runtime")
        # Setup: Page A story exceeds limit, Page B story is eligible
        page_a = "page_quota_met"
        page_b = "page_normal"
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)
        now_ts = int(datetime(2026, 10, 20, 10, 0, tzinfo=ICT).timestamp())

        # 10 stories for Page A
        for i in range(10):
            ts = int((base_monday + timedelta(hours=i)).timestamp())
            db_session.add(
                Job(account_id=1, target_page=page_a, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=ts)
            )
        db_session.commit()

        job_a = Job(id=101, account_id=1, platform="facebook", target_page=page_a, job_type=JobType.STORY, status=JobStatus.PENDING, schedule_ts=now_ts - 100)
        job_b = Job(id=102, account_id=2, platform="facebook", target_page=page_b, job_type=JobType.STORY, status=JobStatus.PENDING, schedule_ts=now_ts - 50)
        db_session.add_all([job_a, job_b])
        db_session.commit()

        # Mock QueueService.claim_next_job to return job_a first, then job_b
        with patch("app.core.queue.queue.QueueService.claim_next_job", side_effect=[job_a, job_b]):
            with patch("time.time", return_value=now_ts):
                claimed, status = claim_next_job_respecting_daily(
                    db_session,
                    platform="facebook",
                    logger=logger,
                )
                # Job A should have been postponed, and Job B successfully claimed!
                assert claimed is not None
                assert claimed.id == 102
                assert status is None
                assert job_a.status == JobStatus.PENDING

    def test_postpone_if_daily_limit_ignores_story_jobs(self, db_session, monkeypatch):
        """Verify that general feed daily limits never block or postpone JobType.STORY jobs."""
        import time
        from app.core import settings as runtime_settings
        logger = logging.getLogger("test_runtime")

        # Set page-level daily post cap to 1
        monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: 1 if "posts_per_page_per_day" in key else default)

        page = "page_story_not_blocked_by_feed_daily"
        account = Account(id=99, name="Acc99", platform="facebook", is_active=True, login_status="ACTIVE", daily_limit=1)
        db_session.add(account)

        # 1 DONE post today for this page
        done_post = Job(
            account_id=99,
            platform="facebook",
            target_page=page,
            job_type=JobType.POST,
            status=JobStatus.DONE,
            finished_at=int(time.time()),
        )
        # STORY job for this page
        story_job = Job(
            account_id=99,
            platform="facebook",
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.RUNNING,
            schedule_ts=int(time.time()),
        )
        db_session.add_all([done_post, story_job])
        db_session.commit()

        # Feed daily limit should ignore story job
        assert postpone_if_daily_limit(db_session, story_job, logger) is False


class TestBufferAdapterStoryPublishing:
    """Tests for BufferAdapter.publish_story wiring and behavior."""

    def test_buffer_adapter_publish_story_calls_create_post_with_fb_type_story(self):
        import time
        from datetime import timezone

        mock_client = MagicMock()
        mock_client.create_post.return_value = {"id": "buf_post_story_123", "dueAt": "2026-10-20T11:30:00.000Z"}
        mock_client.infer_channel_service.return_value = "facebook"

        future_ts = int(time.time()) + 7200
        due_expected = datetime.fromtimestamp(future_ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        adapter = BufferAdapter(client=mock_client)
        job = MagicMock()
        job.id = 55
        job.target_page = "chan_fb_story_456"
        job.caption = "Awesome Story Caption"
        job.media_path = "https://cdn.example.com/stories/story_video.mp4"
        job.processed_media_path = None
        job.resolved_processed_media_path = None
        job.resolved_media_path = None
        job.schedule_ts = future_ts
        job.service = "facebook"

        result = adapter.publish_story(job)

        assert result.ok is True
        assert result.external_post_id == "buf_post_story_123"
        assert result.details["fb_type"] == "story"

        mock_client.create_post.assert_called_once_with(
            text="Awesome Story Caption",
            channel_id="chan_fb_story_456",
            mode="customScheduled",
            media_url="https://cdn.example.com/stories/story_video.mp4",
            due_at=due_expected,
            service="facebook",
            fb_type="story",
        )

    def test_buffer_adapter_publish_routes_job_type_story(self):
        mock_client = MagicMock()
        mock_client.create_post.return_value = {"id": "buf_routed_story", "dueAt": None}
        mock_client.infer_channel_service.return_value = "facebook"

        adapter = BufferAdapter(client=mock_client)
        job = MagicMock()
        job.id = 56
        job.job_type = JobType.STORY
        job.target_page = "chan_fb_story_routed"
        job.caption = "Routed Story"
        job.media_path = "https://cdn.example.com/stories/photo.jpg"
        job.processed_media_path = None
        job.resolved_processed_media_path = None
        job.resolved_media_path = None
        job.schedule_ts = 0
        job.service = "facebook"

        result = adapter.publish(job)

        assert result.ok is True
        assert result.details["fb_type"] == "story"
        mock_client.create_post.assert_called_once()
        assert mock_client.create_post.call_args.kwargs["fb_type"] == "story"

    def test_buffer_adapter_publish_story_safe_mode(self):
        with patch("app.features.buffer.adapter.SAFE_MODE", True):
            adapter = BufferAdapter()
            job = MagicMock()
            job.id = 99
            result = adapter.publish_story(job)
            assert result.ok is True
            assert result.external_post_id == "safe_mode_dry_run"
            assert result.details["fb_type"] == "story"

    def test_buffer_adapter_publish_story_missing_channel(self):
        adapter = BufferAdapter(client=MagicMock())
        job = MagicMock()
        job.id = 100
        job.target_page = None
        job.account = None

        result = adapter.publish_story(job)
        assert result.ok is False
        assert result.is_fatal is True
        assert "channel id Buffer" in result.error
