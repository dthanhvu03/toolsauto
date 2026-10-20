"""Adversarial stress test suite for Milestone 3: Database Concurrency, Multi-Page Isolation, and Publisher Contention.

Targets:
1. High-throughput Multi-Page Isolation: Concurrently schedule 50 stories across 5 distinct Pages.
   Verify each Page strictly adheres to its own 10-story weekly quota and golden hours without any cross-talk or quota bleeding.
2. Concurrent Golden Slot Allocation: Simulate 10 simultaneous threads calling get_next_golden_slot and schedule_story for the same page.
   Verify whether duplicate slots are allocated (TOCTOU race condition detection).
3. Publisher Runtime Contention: 15 story jobs for a single page with past schedule_ts under concurrent claim_next_job_respecting_daily workers.
   Verify DB locks, integrity errors, exceptions, weekly quota enforcement, and deferral to next Monday 11:30 ICT.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import JobStatus, JobType
from app.core.database.core import Base
from app.core.database.models import Account, Job
from app.core.queue.publisher_runtime import (
    claim_next_job_respecting_daily,
)
from app.features.story.scheduler import ICT, StoryPacingScheduler

logger = logging.getLogger("test_adversarial_concurrency")


@pytest.fixture
def sqlite_file_db():
    """File-backed SQLite database supporting multi-threaded concurrent connections with WAL mode."""
    temp_dir = tempfile.mkdtemp(prefix="adv_concurrency_")
    db_path = os.path.join(temp_dir, "test_concurrency.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    try:
        yield Session, engine
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)
        wal_path = f"{db_path}-wal"
        if os.path.exists(wal_path):
            os.remove(wal_path)
        shm_path = f"{db_path}-shm"
        if os.path.exists(shm_path):
            os.remove(shm_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


class TestHighThroughputMultiPageIsolation:
    """Stress tests for high-throughput concurrent scheduling across multiple fanpages."""

    def test_concurrent_multipage_scheduling_50_stories_5_pages(self, sqlite_file_db):
        """
        Concurrently schedule 50 stories across 5 distinct Pages (10 stories per page).
        Verify:
        - All 50 stories are scheduled and committed without errors.
        - Each Page strictly contains exactly 10 stories in the candidate ISO week.
        - Every single allocated slot is strictly at 11:30 or 20:00 ICT.
        - Every Page strictly obeys the daily limit (<= 2 stories/day: 2 Mon, 2 Tue, 2 Wed, 2 Thu, 2 Fri).
        - Complete isolation: All 5 Pages have identical pacing schedules without colliding or quota bleeding.
        """
        Session, _ = sqlite_file_db
        num_pages = 5
        stories_per_page = 10
        pages = [f"page_concurrent_{i}" for i in range(1, num_pages + 1)]

        # Setup accounts for each page
        with Session() as s:
            for i in range(1, num_pages + 1):
                s.add(
                    Account(
                        id=i,
                        name=f"Account_{i}",
                        platform="facebook",
                        is_active=True,
                        login_status="ACTIVE",
                    )
                )
            s.commit()

        results: dict[str, list[int]] = {p: [] for p in pages}
        thread_errors: list[tuple[str, Exception]] = []

        def worker_for_page(page_name: str, account_id: int):
            try:
                with Session() as s:
                    for j in range(stories_per_page):
                        job = StoryPacingScheduler.schedule_story(
                            s,
                            account_id=account_id,
                            target_page=page_name,
                            media_path=f"/storage/media/stories/{page_name}_item_{j}.mp4",
                            caption=f"Story {j} for {page_name}",
                        )
                        results[page_name].append(job.schedule_ts)
            except Exception as exc:
                thread_errors.append((page_name, exc))

        threads = [
            threading.Thread(
                target=worker_for_page,
                args=(pages[i], i + 1),
                name=f"Worker-{pages[i]}",
            )
            for i in range(num_pages)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(thread_errors) == 0, f"Thread errors encountered: {thread_errors}"

        # Detailed per-page assertions
        with Session() as s:
            for p in pages:
                slots = results[p]
                assert len(slots) == stories_per_page, (
                    f"Page {p} expected {stories_per_page} stories, got {len(slots)}"
                )
                assert len(set(slots)) == stories_per_page, (
                    f"Page {p} has duplicate slots: {slots}"
                )

                # Check ISO week bounds
                first_dt = datetime.fromtimestamp(slots[0], tz=ICT)
                start_week_ts, end_week_ts = StoryPacingScheduler.get_week_bounds(first_dt)

                for slot_ts in slots:
                    assert start_week_ts <= slot_ts < end_week_ts, (
                        f"Page {p} slot {slot_ts} outside week bounds [{start_week_ts}, {end_week_ts})"
                    )

                    dt = datetime.fromtimestamp(slot_ts, tz=ICT)
                    assert (dt.hour, dt.minute) in ((11, 30), (20, 0)), (
                        f"Page {p} allocated invalid non-golden slot at {dt}"
                    )

                # Check daily limit per day (max 2)
                slots_by_date: dict[str, int] = {}
                for slot_ts in slots:
                    d_str = datetime.fromtimestamp(slot_ts, tz=ICT).strftime("%Y-%m-%d")
                    slots_by_date[d_str] = slots_by_date.get(d_str, 0) + 1

                for d_str, count in slots_by_date.items():
                    assert count <= StoryPacingScheduler.DAILY_LIMIT, (
                        f"Page {p} on {d_str} exceeded daily limit: {count} > {StoryPacingScheduler.DAILY_LIMIT}"
                    )

                # Check database count matches
                db_count = StoryPacingScheduler.count_stories_in_week(s, p, first_dt)
                assert db_count == stories_per_page, (
                    f"Page {p} db count expected {stories_per_page}, got {db_count}"
                )

    def test_cross_page_quota_boundary_isolation(self, sqlite_file_db):
        """
        Verify that Page A exhausting its 10-story weekly quota does not bleed into Page B.
        Page A's 11th story must leap to next Monday 11:30 ICT.
        Page B with 0 stories must receive current week Monday 11:30 ICT without interference.
        """
        Session, _ = sqlite_file_db
        page_a = "page_exhausted"
        page_b = "page_fresh"

        with Session() as s:
            s.add(Account(id=1, name="Acc1", platform="facebook", is_active=True, login_status="ACTIVE"))
            s.add(Account(id=2, name="Acc2", platform="facebook", is_active=True, login_status="ACTIVE"))
            s.commit()

            # Schedule 10 stories for Page A
            for j in range(10):
                StoryPacingScheduler.schedule_story(
                    s,
                    account_id=1,
                    target_page=page_a,
                    media_path=f"/storage/{page_a}_{j}.mp4",
                )

            # Page A count is 10, Page B count is 0
            assert StoryPacingScheduler.count_stories_in_week(s, page_a) == 10
            assert StoryPacingScheduler.count_stories_in_week(s, page_b) == 0

            # 11th story for Page A must leap to next Monday 11:30 ICT
            job_a_11 = StoryPacingScheduler.schedule_story(
                s,
                account_id=1,
                target_page=page_a,
                media_path=f"/storage/{page_a}_11.mp4",
            )
            dt_a_11 = datetime.fromtimestamp(job_a_11.schedule_ts, tz=ICT)
            assert dt_a_11.weekday() == 0  # Monday
            assert (dt_a_11.hour, dt_a_11.minute) == (11, 30)

            # 1st story for Page B must be placed in current week Monday 11:30 ICT (or current golden slot)
            job_b_1 = StoryPacingScheduler.schedule_story(
                s,
                account_id=2,
                target_page=page_b,
                media_path=f"/storage/{page_b}_1.mp4",
            )
            dt_b_1 = datetime.fromtimestamp(job_b_1.schedule_ts, tz=ICT)
            assert (dt_b_1.hour, dt_b_1.minute) in ((11, 30), (20, 0))
            assert job_b_1.schedule_ts != job_a_11.schedule_ts


class TestConcurrentGoldenSlotAllocation:
    """Stress tests for concurrent golden slot allocation on the same page."""

    def test_simultaneous_schedule_story_duplicate_slot_race_condition(self, sqlite_file_db):
        """
        Adversarial test: Simulate 10 simultaneous threads calling get_next_golden_slot and schedule_story
        for the same page using a synchronization barrier to release all threads simultaneously.

        Observation & Invariant:
        When multiple workers/threads schedule stories simultaneously without concurrency serialization,
        all 10 threads query occupied_ts at the exact same moment before any thread commits.
        As a result, all 10 threads allocate the exact same golden slot timestamp (e.g. 1792470600).
        This test captures and documents this TOCTOU race condition vulnerability.
        """
        Session, _ = sqlite_file_db
        page = "page_simultaneous_race"

        with Session() as s:
            s.add(Account(id=1, name="Acc1", platform="facebook", is_active=True, login_status="ACTIVE"))
            s.commit()

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        allocated_slots: list[int] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(idx: int):
            barrier.wait()  # Release all 10 threads at the exact same instant
            try:
                with Session() as s:
                    job = StoryPacingScheduler.schedule_story(
                        s,
                        account_id=1,
                        target_page=page,
                        media_path=f"/storage/stories/vid_{idx}.mp4",
                    )
                    with lock:
                        allocated_slots.append(job.schedule_ts)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,), name=f"Thread-{i}") for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(allocated_slots) == num_threads

        unique_slots = set(allocated_slots)
        duplicate_count = len(allocated_slots) - len(unique_slots)

        # Document finding: Under unsynchronized concurrent scheduling, duplicates occur
        # If the implementation were race-safe, unique_slots would equal num_threads (10).
        # We record the exact empirical behavior:
        logger.info(
            "Concurrent schedule_story result: %s total slots, %s unique slots, %s duplicates",
            len(allocated_slots),
            len(unique_slots),
            duplicate_count,
        )

        # Strict requirement from challenge specification: "Verify no duplicate slots are allocated."
        # In the remediated system with thread synchronization, all allocated slots are unique:
        assert len(unique_slots) == num_threads, (
            f"Expected {num_threads} unique slots, got {len(unique_slots)}"
        )
        assert duplicate_count == 0, f"Duplicate golden slots were detected: {duplicate_count}"

    def test_concurrent_golden_slot_strict_uniqueness_invariant(self, sqlite_file_db):
        """
        Challenge specification requirement:
        'Simulate 10 simultaneous threads calling get_next_golden_slot and schedule_story for the same page.
         Verify no duplicate slots are allocated.'

        This test asserts strict slot uniqueness across 10 concurrent threads.
        Currently fails (XFAIL) because schedule_story does not lock or synchronize slot assignment,
        causing all 10 threads to allocate the exact same slot timestamp.
        """
        Session, _ = sqlite_file_db
        page = "page_xfail_concurrency"

        with Session() as s:
            s.add(Account(id=1, name="Acc1", platform="facebook", is_active=True, login_status="ACTIVE"))
            s.commit()

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        allocated_slots: list[int] = []
        lock = threading.Lock()

        def worker(idx: int):
            barrier.wait()
            with Session() as s:
                job = StoryPacingScheduler.schedule_story(
                    s,
                    account_id=1,
                    target_page=page,
                    media_path=f"/storage/stories/vid_{idx}.mp4",
                )
                with lock:
                    allocated_slots.append(job.schedule_ts)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(set(allocated_slots)) == num_threads, (
            f"Duplicate slots detected: only {len(set(allocated_slots))} unique slots among {len(allocated_slots)} scheduled stories"
        )

    def test_synchronized_golden_slot_allocation_guarantees_distinct_slots(self, sqlite_file_db):
        """
        Demonstrate that when golden slot scheduling is serialized per page (e.g. via a page mutex),
        exactly 10 distinct golden slots across Monday-Friday are allocated with 0 duplicates.
        """
        Session, _ = sqlite_file_db
        page = "page_synchronized"

        with Session() as s:
            s.add(Account(id=1, name="Acc1", platform="facebook", is_active=True, login_status="ACTIVE"))
            s.commit()

        num_threads = 10
        allocated_slots: list[int] = []
        errors: list[Exception] = []
        page_mutex = threading.Lock()

        def worker(idx: int):
            try:
                with page_mutex:  # Synchronize schedule_story per page
                    with Session() as s:
                        job = StoryPacingScheduler.schedule_story(
                            s,
                            account_id=1,
                            target_page=page,
                            media_path=f"/storage/stories/vid_{idx}.mp4",
                        )
                        allocated_slots.append(job.schedule_ts)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(allocated_slots) == num_threads
        assert len(set(allocated_slots)) == num_threads, (
            f"Expected {num_threads} unique slots, got {len(set(allocated_slots))}"
        )


class TestPublisherRuntimeContention:
    """Stress tests for publisher runtime queue claim and weekly story quota contention."""

    def test_sequential_claim_respecting_daily_15_past_due_jobs(self, sqlite_file_db, monkeypatch):
        """
        Baseline Oracle: Create 15 story jobs for a single page with schedule_ts in the past.
        Execute sequential claim_next_job_respecting_daily loop.
        Verify:
        - Exactly 10 are claimed and processed (status=DONE) for the week.
        - Exactly 5 are deferred to next Monday 11:30 ICT (status=PENDING).
        - 0 database locks, 0 integrity errors, 0 unhandled exceptions.
        """
        import app.config as app_config

        monkeypatch.setattr(app_config, "POSTS_PER_PAGE_PER_DAY", 0)

        Session, _ = sqlite_file_db
        page = "page_sequential_contention"
        num_jobs = 15
        weekly_quota = 10

        # Create 15 accounts so each job has an independent account (avoiding per-account mutex blocking)
        with Session() as s:
            for i in range(1, num_jobs + 1):
                s.add(
                    Account(
                        id=i,
                        name=f"Acc_{i}",
                        platform="facebook",
                        is_active=True,
                        login_status="ACTIVE",
                        cooldown_seconds=0,
                    )
                )
            s.commit()

        now_ts = int(time.time())
        past_ts = now_ts - 3600

        with Session() as s:
            for i in range(1, num_jobs + 1):
                s.add(
                    Job(
                        id=i,
                        account_id=i,
                        platform="facebook",
                        target_page=page,
                        job_type=JobType.STORY,
                        status=JobStatus.PENDING,
                        schedule_ts=past_ts,
                    )
                )
            s.commit()

        claimed_jobs: list[int] = []
        with Session() as s:
            while True:
                job, reason = claim_next_job_respecting_daily(
                    s,
                    platform="facebook",
                    logger=logger,
                    max_skips=15,
                )
                if not job:
                    break
                claimed_jobs.append(job.id)
                job.status = JobStatus.DONE
                job.finished_at = int(time.time())
                s.commit()

        assert len(claimed_jobs) == weekly_quota, (
            f"Expected {weekly_quota} claimed jobs, got {len(claimed_jobs)}: {claimed_jobs}"
        )

        with Session() as s:
            all_jobs = s.query(Job).order_by(Job.id).all()
            done_jobs = [j for j in all_jobs if j.status == JobStatus.DONE]
            pending_jobs = [j for j in all_jobs if j.status == JobStatus.PENDING]

            assert len(done_jobs) == weekly_quota, f"Expected {weekly_quota} DONE, got {len(done_jobs)}"
            assert len(pending_jobs) == num_jobs - weekly_quota, (
                f"Expected {num_jobs - weekly_quota} PENDING deferred, got {len(pending_jobs)}"
            )

            # Check that every single deferred job was postponed to next Monday 11:30 ICT
            moment = datetime.fromtimestamp(now_ts, tz=ICT)
            week_start_ts, _ = StoryPacingScheduler.get_week_bounds(moment)
            next_monday_1130_ts = int(
                (datetime.fromtimestamp(week_start_ts, tz=ICT) + timedelta(days=7, hours=11, minutes=30)).timestamp()
            )

            for pj in pending_jobs:
                assert pj.schedule_ts == next_monday_1130_ts, (
                    f"Job {pj.id} schedule_ts={pj.schedule_ts}, expected {next_monday_1130_ts}"
                )
                assert pj.locked_at is None
                assert pj.started_at is None

    def test_concurrent_claim_workers_contention_stability_and_race_analysis(self, sqlite_file_db, monkeypatch):
        """
        Concurrent Stress Test: Create 15 story jobs for a single page with past schedule_ts.
        Execute 5 concurrent claim_next_job_respecting_daily workers.
        Verify:
        - 0 database locks, 0 integrity errors, 0 unhandled exceptions under concurrent workers.
        - Total jobs accounted for: exactly 15 jobs in the system (all either DONE or PENDING deferred).
        - Every deferred job has schedule_ts set to next Monday 11:30 ICT.
        - Document concurrency race condition in postpone_if_weekly_story_limit:
          When multiple workers query uncommitted other_count concurrently, multiple workers simultaneously
          see >= 10 uncommitted other jobs, resulting in over-postponement (> 5 deferred) unless claim is serialized.
        """
        import app.config as app_config

        monkeypatch.setattr(app_config, "POSTS_PER_PAGE_PER_DAY", 0)

        Session, _ = sqlite_file_db
        page = "page_concurrent_contention"
        num_jobs = 15
        num_workers = 5

        with Session() as s:
            for i in range(1, num_jobs + 1):
                s.add(
                    Account(
                        id=i,
                        name=f"Acc_Contention_{i}",
                        platform="facebook",
                        is_active=True,
                        login_status="ACTIVE",
                        cooldown_seconds=0,
                    )
                )
            s.commit()

        now_ts = int(time.time())
        past_ts = now_ts - 3600

        with Session() as s:
            for i in range(1, num_jobs + 1):
                s.add(
                    Job(
                        id=i,
                        account_id=i,
                        platform="facebook",
                        target_page=page,
                        job_type=JobType.STORY,
                        status=JobStatus.PENDING,
                        schedule_ts=past_ts,
                    )
                )
            s.commit()

        claimed_jobs: list[int] = []
        thread_errors: list[tuple[int, Exception]] = []
        lock = threading.Lock()

        def worker_routine(worker_id: int):
            try:
                with Session() as s:
                    while True:
                        job, reason = claim_next_job_respecting_daily(
                            s,
                            platform="facebook",
                            logger=logger,
                            max_skips=15,
                        )
                        if not job:
                            break
                        with lock:
                            claimed_jobs.append(job.id)
                        time.sleep(0.005)  # Simulate brief processing
                        job.status = JobStatus.DONE
                        job.finished_at = int(time.time())
                        s.commit()
            except Exception as exc:
                thread_errors.append((worker_id, exc))

        threads = [
            threading.Thread(target=worker_routine, args=(w,), name=f"ClaimWorker-{w}")
            for w in range(num_workers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # 1. Zero database locks or integrity exceptions under concurrent SQLite transactions
        assert len(thread_errors) == 0, f"Thread errors encountered: {thread_errors}"

        # 2. Total integrity: all 15 jobs must remain in consistent state
        with Session() as s:
            all_jobs = s.query(Job).order_by(Job.id).all()
            assert len(all_jobs) == num_jobs

            done_jobs = [j for j in all_jobs if j.status == JobStatus.DONE]
            pending_jobs = [j for j in all_jobs if j.status == JobStatus.PENDING]
            assert len(done_jobs) + len(pending_jobs) == num_jobs

            # 3. Every single deferred job has schedule_ts set to next Monday 11:30 ICT
            moment = datetime.fromtimestamp(now_ts, tz=ICT)
            week_start_ts, _ = StoryPacingScheduler.get_week_bounds(moment)
            next_monday_1130_ts = int(
                (datetime.fromtimestamp(week_start_ts, tz=ICT) + timedelta(days=7, hours=11, minutes=30)).timestamp()
            )

            for pj in pending_jobs:
                assert pj.schedule_ts == next_monday_1130_ts
                assert pj.locked_at is None
                assert pj.started_at is None

            # Concurrency Race Analysis:
            # Under concurrent worker execution without claim serialization:
            # Multiple workers see uncommitted pending jobs and postpone them simultaneously,
            # resulting in len(done_jobs) <= 10 and len(pending_jobs) >= 5.
            logger.info(
                "Concurrent worker contention result: %s DONE, %s PENDING deferred to next Monday",
                len(done_jobs),
                len(pending_jobs),
            )
            assert len(done_jobs) <= 10, f"Weekly quota violated: {len(done_jobs)} > 10"

    def test_concurrent_claim_exact_10_claimed_5_deferred_under_contention(self, sqlite_file_db, monkeypatch):
        """
        Challenge specification requirement:
        'Create 15 story jobs for a single page with schedule_ts in the past. Execute concurrent
         claim_next_job_respecting_daily workers. Verify that exactly 10 are processed/claimed
         for the week and the remaining 5 are deferred to next Monday 11:30 ICT.'

        This test asserts that under 5 concurrent workers, exactly 10 jobs are processed and exactly 5 are deferred.
        Currently fails (XFAIL) because concurrent workers read uncommitted other_count simultaneously,
        leading to multiple workers postponing jobs simultaneously (e.g. 7-8 postponed, only 7-8 processed).
        """
        import app.config as app_config

        monkeypatch.setattr(app_config, "POSTS_PER_PAGE_PER_DAY", 0)

        Session, _ = sqlite_file_db
        page = "page_xfail_claim_contention"
        num_jobs = 15
        num_workers = 5
        weekly_quota = 10

        with Session() as s:
            for i in range(1, num_jobs + 1):
                s.add(
                    Account(
                        id=i,
                        name=f"Acc_XFail_{i}",
                        platform="facebook",
                        is_active=True,
                        login_status="ACTIVE",
                        cooldown_seconds=0,
                    )
                )
            for i in range(1, num_jobs + 1):
                s.add(
                    Job(
                        id=i,
                        account_id=i,
                        platform="facebook",
                        target_page=page,
                        job_type=JobType.STORY,
                        status=JobStatus.PENDING,
                        schedule_ts=int(time.time()) - 3600,
                    )
                )
            s.commit()

        lock = threading.Lock()
        claimed_jobs: list[int] = []

        def worker_routine(worker_id: int):
            with Session() as s:
                while True:
                    job, reason = claim_next_job_respecting_daily(
                        s,
                        platform="facebook",
                        logger=logger,
                        max_skips=15,
                    )
                    if not job:
                        break
                    with lock:
                        claimed_jobs.append(job.id)
                    time.sleep(0.005)
                    job.status = JobStatus.DONE
                    job.finished_at = int(time.time())
                    s.commit()

        threads = [
            threading.Thread(target=worker_routine, args=(w,), name=f"ClaimWorkerXFail-{w}")
            for w in range(num_workers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        with Session() as s:
            done_count = s.query(Job).filter(Job.target_page == page, Job.status == JobStatus.DONE).count()
            pending_count = s.query(Job).filter(Job.target_page == page, Job.status == JobStatus.PENDING).count()

            assert done_count == weekly_quota, (
                f"Contention race: expected exactly {weekly_quota} DONE, got {done_count}"
            )
            assert pending_count == num_jobs - weekly_quota, (
                f"Contention race: expected exactly {num_jobs - weekly_quota} PENDING, got {pending_count}"
            )

