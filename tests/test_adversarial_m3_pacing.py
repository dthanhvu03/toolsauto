"""Adversarial test suite for Milestone 3: Story Pacing Boundary & Quota Rollover.

Targets boundary conditions, calendar transitions, exact hour/minute boundaries,
and quota state hygiene under adversarial scenarios.
"""
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
    """In-memory SQLite session isolated per test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


# =====================================================================
# 1. Year/Month Boundary Transitions
# =====================================================================
class TestYearMonthBoundaryTransitions:
    """Adversarial tests for calendar transitions across year/month boundaries."""

    def test_cross_year_week_boundary_dec_to_jan(self):
        """
        Verify ISO week calculation when Monday is in December (previous year)
        and Sunday is in January (next year).
        2024-12-30 is Monday; 2025-01-05 is Sunday.
        Every single day of this week must produce identical week boundaries:
        Start: 2024-12-30 00:00:00 ICT
        End:   2025-01-06 00:00:00 ICT
        Duration: exactly 7 * 86400 = 604,800 seconds.
        """
        expected_start = datetime(2024, 12, 30, 0, 0, 0, tzinfo=ICT)
        expected_end = datetime(2025, 1, 6, 0, 0, 0, tzinfo=ICT)
        expected_start_ts = int(expected_start.timestamp())
        expected_end_ts = int(expected_end.timestamp())

        # Test all 7 days of the cross-year week
        for day_offset in range(7):
            curr_date = datetime(2024, 12, 30, tzinfo=ICT) + timedelta(days=day_offset)
            # Test at multiple times: morning, noon, evening, last second of day
            for h, m, s in [(0, 0, 0), (11, 30, 0), (12, 0, 0), (20, 0, 0), (23, 59, 59)]:
                moment = curr_date.replace(hour=h, minute=m, second=s)
                start_ts, end_ts = StoryPacingScheduler.get_week_bounds(moment)

                assert start_ts == expected_start_ts, (
                    f"Failed start for moment {moment}: got {start_ts}, expected {expected_start_ts}"
                )
                assert end_ts == expected_end_ts, (
                    f"Failed end for moment {moment}: got {end_ts}, expected {expected_end_ts}"
                )
                assert end_ts - start_ts == 7 * 86400, "Week duration is not 7 days"

    def test_cross_year_scheduling_transition(self, db_session):
        """
        Scheduling on New Year's Eve (2024-12-31 20:00:00 ICT) must cleanly
        allocate New Year's Day (2025-01-01 11:30:00 ICT).
        """
        page = "cross_year_page"
        t_nye_2000 = int(datetime(2024, 12, 31, 20, 0, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=t_nye_2000)
        dt = datetime.fromtimestamp(slot, tz=ICT)

        assert dt == datetime(2025, 1, 1, 11, 30, 0, tzinfo=ICT)

    def test_leap_year_february_29(self, db_session):
        """
        Test leap year boundary on February 29th (2024 is leap year, Feb 29 is Thursday).
        - Week bounds containing Feb 29: [2024-02-26 00:00:00 ICT, 2024-03-04 00:00:00 ICT).
        - Scheduling from Feb 28 20:00:00 ICT -> lands on Feb 29 11:30:00 ICT.
        - Scheduling from Feb 29 11:30:00 ICT -> lands on Feb 29 20:00:00 ICT.
        - Scheduling from Feb 29 20:00:00 ICT -> lands on Mar 01 11:30:00 ICT.
        """
        dt_leap = datetime(2024, 2, 29, 15, 0, 0, tzinfo=ICT)
        start_ts, end_ts = StoryPacingScheduler.get_week_bounds(dt_leap)
        assert datetime.fromtimestamp(start_ts, tz=ICT) == datetime(2024, 2, 26, 0, 0, 0, tzinfo=ICT)
        assert datetime.fromtimestamp(end_ts, tz=ICT) == datetime(2024, 3, 4, 0, 0, 0, tzinfo=ICT)

        page = "leap_year_page"
        # 1. From Feb 28 20:00:00 -> lands on Feb 29 11:30:00
        t_feb28_2000 = int(datetime(2024, 2, 28, 20, 0, 0, tzinfo=ICT).timestamp())
        slot1 = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=t_feb28_2000)
        assert datetime.fromtimestamp(slot1, tz=ICT) == datetime(2024, 2, 29, 11, 30, 0, tzinfo=ICT)

        # 2. From Feb 29 11:30:00 -> lands on Feb 29 20:00:00
        t_feb29_1130 = int(datetime(2024, 2, 29, 11, 30, 0, tzinfo=ICT).timestamp())
        slot2 = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=t_feb29_1130)
        assert datetime.fromtimestamp(slot2, tz=ICT) == datetime(2024, 2, 29, 20, 0, 0, tzinfo=ICT)

        # 3. From Feb 29 20:00:00 -> lands on March 01 11:30:00
        t_feb29_2000 = int(datetime(2024, 2, 29, 20, 0, 0, tzinfo=ICT).timestamp())
        slot3 = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=t_feb29_2000)
        assert datetime.fromtimestamp(slot3, tz=ICT) == datetime(2024, 3, 1, 11, 30, 0, tzinfo=ICT)

    def test_non_leap_year_february_transition(self, db_session):
        """
        2023 is non-leap year (Feb 28 is Tuesday).
        Scheduling at Feb 28 20:00:00 ICT must immediately advance to March 01 11:30:00 ICT.
        """
        page = "non_leap_page"
        t_feb28_2000 = int(datetime(2023, 2, 28, 20, 0, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=t_feb28_2000)
        assert datetime.fromtimestamp(slot, tz=ICT) == datetime(2023, 3, 1, 11, 30, 0, tzinfo=ICT)

    def test_dst_invariance_vietnam_ict(self):
        """
        Vietnam (ICT, Asia/Ho_Chi_Minh) does not observe Daylight Saving Time.
        Verify that across global DST shifts, ICT maintains fixed UTC+7 offset (25200s),
        zero DST offset, and strictly 604,800s week durations.
        """
        dst_check_dates = [
            datetime(2024, 3, 10, 12, 0, tzinfo=ICT),  # US Spring Forward
            datetime(2024, 3, 31, 12, 0, tzinfo=ICT),  # EU Spring Forward
            datetime(2024, 10, 27, 12, 0, tzinfo=ICT),  # EU Fall Back
            datetime(2024, 11, 3, 12, 0, tzinfo=ICT),   # US Fall Back
            datetime(2026, 6, 21, 12, 0, tzinfo=ICT),   # Midsummer solstice
            datetime(2026, 12, 21, 12, 0, tzinfo=ICT),  # Midwinter solstice
        ]
        for dt in dst_check_dates:
            offset = dt.utcoffset()
            assert offset == timedelta(hours=7), f"Offset mismatch at {dt}: {offset}"
            assert dt.dst() == timedelta(0), f"DST detected at {dt}: {dt.dst()}"

            start_ts, end_ts = StoryPacingScheduler.get_week_bounds(dt)
            duration = end_ts - start_ts
            assert duration == 7 * 86400, f"Duration changed during DST shift at {dt}: {duration}"

    def test_utc_and_naive_datetime_inputs(self):
        """
        Adversarial test for datetime inputs:
        - UTC datetime: 2026-10-18 17:30:00 UTC is 2026-10-19 00:30:00 ICT (Monday).
          Must yield Monday Oct 19 week bounds, not Sunday Oct 18!
        - Naive datetime: assumed ICT local time.
        - Float epoch timestamp: handled without precision loss.
        """
        # UTC 17:30 on Sunday Oct 18 == ICT 00:30 on Monday Oct 19
        utc_dt = datetime(2026, 10, 18, 17, 30, 0, tzinfo=timezone.utc)
        start_ts, end_ts = StoryPacingScheduler.get_week_bounds(utc_dt)
        start_dt = datetime.fromtimestamp(start_ts, tz=ICT)
        assert start_dt == datetime(2026, 10, 19, 0, 0, 0, tzinfo=ICT)

        # Naive datetime
        naive_dt = datetime(2026, 10, 19, 14, 0, 0)
        s_naive, e_naive = StoryPacingScheduler.get_week_bounds(naive_dt)
        assert s_naive == start_ts

        # Float timestamp
        float_ts = float(start_ts + 3600.789)
        s_float, e_float = StoryPacingScheduler.get_week_bounds(float_ts)
        assert s_float == start_ts


# =====================================================================
# 2. Exact Hour/Minute Edge Cases
# =====================================================================
class TestExactHourMinuteEdgeCases:
    """Adversarial precision tests on exact hour/minute/second boundary conditions."""

    @pytest.mark.parametrize(
        ("input_hour", "input_minute", "input_second", "expected_day_offset", "expected_hour", "expected_minute"),
        [
            # 11:29:59 -> same day 11:30:00
            (11, 29, 59, 0, 11, 30),
            # 11:30:00 -> same day 20:00:00 (since slot_ts <= after_ts)
            (11, 30, 0, 0, 20, 0),
            # 11:30:01 -> same day 20:00:00
            (11, 30, 1, 0, 20, 0),
            # 19:59:59 -> same day 20:00:00
            (19, 59, 59, 0, 20, 0),
            # 20:00:00 -> tomorrow 11:30:00
            (20, 0, 0, 1, 11, 30),
            # 20:00:01 -> tomorrow 11:30:00
            (20, 0, 1, 1, 11, 30),
            # 23:59:59 -> tomorrow 11:30:00
            (23, 59, 59, 1, 11, 30),
            # 00:00:00 -> same day 11:30:00
            (0, 0, 0, 0, 11, 30),
        ],
    )
    def test_midweek_exact_boundaries(
        self,
        db_session,
        input_hour,
        input_minute,
        input_second,
        expected_day_offset,
        expected_hour,
        expected_minute,
    ):
        page = f"page_boundary_{input_hour}_{input_minute}_{input_second}"
        # Start at Tuesday 2026-10-20
        base_date = datetime(2026, 10, 20, input_hour, input_minute, input_second, tzinfo=ICT)
        after_ts = int(base_date.timestamp())

        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=after_ts)
        result_dt = datetime.fromtimestamp(slot, tz=ICT)

        expected_dt = datetime(2026, 10, 20, tzinfo=ICT) + timedelta(
            days=expected_day_offset, hours=expected_hour, minutes=expected_minute
        )
        assert result_dt == expected_dt, (
            f"At {input_hour:02d}:{input_minute:02d}:{input_second:02d}: "
            f"expected {expected_dt.isoformat()}, got {result_dt.isoformat()}"
        )

    def test_sunday_night_exact_boundary_transitions(self, db_session):
        """
        Adversarial tests on Sunday exact boundaries:
        - Sunday 20:00:00 ICT -> next Monday 11:30:00 ICT
        - Sunday 20:00:01 ICT -> next Monday 11:30:00 ICT
        - Sunday 23:59:59 ICT -> next Monday 11:30:00 ICT
        """
        page = "sunday_boundaries"
        sunday_base = datetime(2026, 10, 25, tzinfo=ICT)  # Sunday
        next_monday_1130 = datetime(2026, 10, 26, 11, 30, 0, tzinfo=ICT)

        for h, m, s in [(20, 0, 0), (20, 0, 1), (23, 59, 59)]:
            sun_ts = int(sunday_base.replace(hour=h, minute=m, second=s).timestamp())
            slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=sun_ts)
            dt = datetime.fromtimestamp(slot, tz=ICT)
            assert dt == next_monday_1130, f"Sunday {h:02d}:{m:02d}:{s:02d} failed to leap to Monday 11:30"


# =====================================================================
# 3. Quota Saturation Stress
# =====================================================================
class TestQuotaSaturationStress:
    """Adversarial stress harness for rapid scheduling and multi-week quota saturation."""

    def test_rapid_schedule_10_stories_and_verify_11th_lands_on_next_monday(self, db_session):
        """
        Stress test: Rapidly schedule 10 stories in a single week starting Monday 08:00 ICT.
        Stories 1-10 must allocate Monday-Friday golden slots (2/day).
        The 11th story MUST leap over Saturday and Sunday to next Monday 11:30 ICT!
        """
        from unittest.mock import patch

        page = "saturation_page_week1"
        account_id = 42
        base_monday = datetime(2026, 10, 19, 8, 0, 0, tzinfo=ICT)
        monday_8am_ts = int(base_monday.timestamp())

        scheduled_jobs = []
        with patch("time.time", return_value=monday_8am_ts):
            for i in range(10):
                # Rapidly schedule with alternating media modes
                mode = StoryPacingScheduler.get_next_media_mode(db_session, page)
                media = f"/tmp/viral_{i}.mp4" if mode == "video" else f"/tmp/viral_{i}.jpg"
                job = StoryPacingScheduler.schedule_story(
                    db_session,
                    account_id=account_id,
                    target_page=page,
                    media_path=media,
                    caption=f"Story {i + 1}",
                )
                scheduled_jobs.append(job)

            # Now schedule the 11th story
            job_11 = StoryPacingScheduler.schedule_story(
                db_session,
                account_id=account_id,
                target_page=page,
                media_path="/tmp/story_11.mp4",
            )

        # Verify DB week count is exactly 10
        count = StoryPacingScheduler.count_stories_in_week(db_session, page, base_monday)
        assert count == 10

        # Verify exact slot assignments for stories 1-10
        expected_slots = [
            datetime(2026, 10, 19, 11, 30, tzinfo=ICT),
            datetime(2026, 10, 19, 20, 0, tzinfo=ICT),
            datetime(2026, 10, 20, 11, 30, tzinfo=ICT),
            datetime(2026, 10, 20, 20, 0, tzinfo=ICT),
            datetime(2026, 10, 21, 11, 30, tzinfo=ICT),
            datetime(2026, 10, 21, 20, 0, tzinfo=ICT),
            datetime(2026, 10, 22, 11, 30, tzinfo=ICT),
            datetime(2026, 10, 22, 20, 0, tzinfo=ICT),
            datetime(2026, 10, 23, 11, 30, tzinfo=ICT),
            datetime(2026, 10, 23, 20, 0, tzinfo=ICT),
        ]
        for idx, (job, expected_dt) in enumerate(zip(scheduled_jobs, expected_slots)):
            job_dt = datetime.fromtimestamp(job.schedule_ts, tz=ICT)
            assert job_dt == expected_dt, f"Job {idx + 1} allocated wrong slot: {job_dt} vs {expected_dt}"

        dt_11 = datetime.fromtimestamp(job_11.schedule_ts, tz=ICT)
        next_monday_1130 = datetime(2026, 10, 26, 11, 30, 0, tzinfo=ICT)
        assert dt_11 == next_monday_1130, f"11th story did not land on next Monday 11:30 ICT: got {dt_11}"

    def test_rapid_schedule_20_stories_and_verify_21st_lands_on_week3_monday(self, db_session):
        """
        Adversarial multi-week quota stress test:
        Schedule 20 stories rapidly across Week 1 and Week 2.
        Verify that the 21st story leaps completely across Week 2 to Week 3 Monday 11:30 ICT!
        """
        page = "multi_week_saturation_page"
        account_id = 99

        # Schedule 20 stories sequentially
        for i in range(20):
            StoryPacingScheduler.schedule_story(
                db_session,
                account_id=account_id,
                target_page=page,
                media_path=f"/tmp/multi_{i}.mp4",
                caption=f"Multi story {i + 1}",
            )

        # Check total jobs in DB for page
        total = db_session.query(Job).filter(Job.target_page == page).count()
        assert total == 20

        # Week 1 count = 10
        w1_dt = datetime(2026, 10, 19, 12, 0, tzinfo=ICT)
        assert StoryPacingScheduler.count_stories_in_week(db_session, page, w1_dt) == 10

        # Week 2 count = 10
        w2_dt = datetime(2026, 10, 26, 12, 0, tzinfo=ICT)
        assert StoryPacingScheduler.count_stories_in_week(db_session, page, w2_dt) == 10

        # 21st story must leap to Week 3 Monday 11:30 ICT
        job_21 = StoryPacingScheduler.schedule_story(
            db_session,
            account_id=account_id,
            target_page=page,
            media_path="/tmp/multi_21.jpg",
        )
        dt_21 = datetime.fromtimestamp(job_21.schedule_ts, tz=ICT)
        week3_monday_1130 = datetime(2026, 11, 2, 11, 30, 0, tzinfo=ICT)
        assert dt_21 == week3_monday_1130, f"21st story landed on {dt_21}, expected {week3_monday_1130}"

    def test_alternating_media_mode_under_saturation(self, db_session):
        """
        Verify that get_next_media_mode strictly alternates video and photo
        through 10 consecutive story creations.
        """
        page = "alternating_saturation_page"
        account_id = 101

        expected_sequence = [
            "video",  # initial empty -> video
            "photo",  # after video -> photo
            "video",  # after photo -> video
            "photo",
            "video",
            "photo",
            "video",
            "photo",
            "video",
            "photo",
        ]

        for i, expected_mode in enumerate(expected_sequence):
            mode = StoryPacingScheduler.get_next_media_mode(db_session, page)
            assert mode == expected_mode, f"Step {i + 1}: expected {expected_mode}, got {mode}"

            ext = ".mp4" if mode == "video" else ".jpg"
            StoryPacingScheduler.schedule_story(
                db_session,
                account_id=account_id,
                target_page=page,
                media_path=f"/tmp/media_{i}{ext}",
            )


# =====================================================================
# 4. Quota State Hygiene
# =====================================================================
class TestQuotaStateHygiene:
    """Adversarial tests for state hygiene: CANCELLED, FAILED, and non-STORY jobs."""

    def test_cancelled_and_failed_jobs_do_not_count_toward_weekly_quota(self, db_session):
        """
        Adversarial test:
        Insert 10 CANCELLED story jobs and 10 FAILED story jobs in the current week.
        count_stories_in_week must return 0!
        get_next_golden_slot must NOT leap to next Monday, but return current Monday 11:30.
        """
        page = "hygiene_page"
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)

        # 10 CANCELLED + 10 FAILED = 20 dead jobs
        dead_jobs = []
        for i in range(10):
            t_c = int((base_monday + timedelta(hours=i)).timestamp())
            t_f = int((base_monday + timedelta(hours=i + 10)).timestamp())
            dead_jobs.append(
                Job(
                    account_id=1,
                    target_page=page,
                    job_type=JobType.STORY,
                    status=JobStatus.CANCELLED,
                    schedule_ts=t_c,
                )
            )
            dead_jobs.append(
                Job(
                    account_id=1,
                    target_page=page,
                    job_type=JobType.STORY,
                    status=JobStatus.FAILED,
                    schedule_ts=t_f,
                )
            )
        db_session.add_all(dead_jobs)
        db_session.commit()

        # Quota count must strictly be 0
        assert StoryPacingScheduler.count_stories_in_week(db_session, page, base_monday) == 0

        # Golden slot must assign Monday 11:30 ICT
        monday_8am = int(datetime(2026, 10, 19, 8, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=monday_8am)
        dt = datetime.fromtimestamp(slot, tz=ICT)
        assert dt == datetime(2026, 10, 19, 11, 30, tzinfo=ICT)

    def test_cancelling_story_immediately_frees_quota_slot(self, db_session):
        """
        Saturation hygiene transition:
        - Populate 10 stories (9 DONE, 1 PENDING).
        - Quota is full (10 stories).
        - Verify next slot jumps to next Monday.
        - Transition the PENDING job to CANCELLED.
        - Quota count immediately drops to 9.
        - Verify next golden slot is now reclaimed within the current week!
        """
        page = "reclaim_quota_page"
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)

        jobs = []
        # 9 DONE jobs (Monday through Thursday)
        for day in range(4):
            for h, m in ((11, 30), (20, 0)):
                ts = int((base_monday + timedelta(days=day, hours=h, minutes=m)).timestamp())
                jobs.append(
                    Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=ts)
                )
        # 9th job on Friday 11:30 DONE
        ts_fri_1130 = int((base_monday + timedelta(days=4, hours=11, minutes=30)).timestamp())
        jobs.append(
            Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=ts_fri_1130)
        )
        # 10th job on Friday 20:00 PENDING
        ts_fri_2000 = int((base_monday + timedelta(days=4, hours=20, minutes=0)).timestamp())
        pending_job = Job(
            account_id=1,
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.PENDING,
            schedule_ts=ts_fri_2000,
        )
        jobs.append(pending_job)
        db_session.add_all(jobs)
        db_session.commit()

        # Quota is 10
        assert StoryPacingScheduler.count_stories_in_week(db_session, page, base_monday) == 10

        fri_noon = int((base_monday + timedelta(days=4, hours=12, minutes=0)).timestamp())
        # While saturated, next slot must be next Monday
        slot_saturated = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=fri_noon)
        assert datetime.fromtimestamp(slot_saturated, tz=ICT) == datetime(2026, 10, 26, 11, 30, tzinfo=ICT)

        # Cancel the 10th job
        pending_job.status = JobStatus.CANCELLED
        db_session.commit()

        # Quota is now 9!
        assert StoryPacingScheduler.count_stories_in_week(db_session, page, base_monday) == 9

        # Now slot should be Friday 20:00 (which was freed!) or Saturday 11:30
        slot_reclaimed = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=fri_noon)
        dt_reclaimed = datetime.fromtimestamp(slot_reclaimed, tz=ICT)
        # Friday 20:00 is freed because CANCELLED job is excluded from occupied_ts!
        assert dt_reclaimed == datetime(2026, 10, 23, 20, 0, tzinfo=ICT)

    def test_runtime_gate_hygiene_with_cancelled_and_failed_jobs(self, db_session):
        """
        Verify publisher_runtime.postpone_if_weekly_story_limit:
        - When DB contains 10 CANCELLED or FAILED jobs, candidate story job is NOT postponed (returns False).
        - When DB contains 10 DONE jobs, candidate story job is postponed (returns True) and deferred to next Monday 11:30.
        """
        page = "runtime_hygiene_page"
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)
        now_ts = int((base_monday + timedelta(days=1, hours=10, minutes=0)).timestamp())

        # 1. Add 10 CANCELLED jobs
        for i in range(10):
            ts = int((base_monday + timedelta(hours=i)).timestamp())
            db_session.add(
                Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.CANCELLED, schedule_ts=ts)
            )
        db_session.commit()

        candidate_job = Job(
            id=999,
            account_id=1,
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.PENDING,
            schedule_ts=now_ts,
        )
        db_session.add(candidate_job)
        db_session.commit()

        # Must not postpone because CANCELLED jobs do not count
        postponed = postpone_if_weekly_story_limit(db_session, candidate_job, now_ts=now_ts)
        assert postponed is False
        assert candidate_job.schedule_ts == now_ts

        # 2. Add 10 DONE jobs
        for i in range(10):
            ts = int((base_monday + timedelta(hours=i + 1)).timestamp())
            db_session.add(
                Job(account_id=1, target_page=page, job_type=JobType.STORY, status=JobStatus.DONE, schedule_ts=ts)
            )
        db_session.commit()

        # Now quota is saturated (10 DONE jobs). Candidate must be postponed!
        postponed = postpone_if_weekly_story_limit(db_session, candidate_job, now_ts=now_ts)
        assert postponed is True
        expected_deferred_dt = datetime(2026, 10, 26, 11, 30, tzinfo=ICT)
        assert candidate_job.schedule_ts == int(expected_deferred_dt.timestamp())
        assert candidate_job.status == JobStatus.PENDING

    def test_non_story_jobs_never_affect_story_quota(self, db_session):
        """
        Adversarial test: Non-STORY jobs (e.g. JobType.REEL, JobType.POST) must never
        exhaust or alter the story quota.
        """
        page = "mixed_jobtype_page"
        base_monday = datetime(2026, 10, 19, 0, 0, tzinfo=ICT)

        # 50 REEL jobs in the current week
        reel_jobs = []
        for i in range(50):
            ts = int((base_monday + timedelta(hours=i % 100)).timestamp())
            reel_jobs.append(
                Job(
                    account_id=1,
                    target_page=page,
                    job_type=getattr(JobType, "REEL", "reel"),
                    status=JobStatus.DONE,
                    schedule_ts=ts,
                )
            )
        db_session.add_all(reel_jobs)
        db_session.commit()

        # Story count is still 0
        assert StoryPacingScheduler.count_stories_in_week(db_session, page, base_monday) == 0

        # Golden slot is still Monday 11:30
        monday_8am = int(datetime(2026, 10, 19, 8, 0, tzinfo=ICT).timestamp())
        slot = StoryPacingScheduler.get_next_golden_slot(db_session, page, after_ts=monday_8am)
        assert datetime.fromtimestamp(slot, tz=ICT) == datetime(2026, 10, 19, 11, 30, tzinfo=ICT)
