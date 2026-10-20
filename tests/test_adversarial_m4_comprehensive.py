"""Milestone 4 Final Comprehensive Adversarial Verifier Suite.

Adversarially validates:
1. R1: Automated Gemini AI FirstComment & Buffer Integration:
   - Vietnamese conversational nuance, unicode safety, length clamping <= 150 chars.
   - Multi-pass quote, markdown, codeblock, and prefix stripping.
   - Catastrophic failure recovery (timeout, rate limit 429, 500, empty, whitespace, stripped-to-empty).
   - Buffer GraphQL mutation schema compliance: strict TikTok metadata omission (preventing 422),
     and proper injection for Facebook (metadata.facebook.firstComment) and Instagram (metadata.instagram.firstComment).
2. R2: Media Extraction & Story Pacing Scheduler:
   - Canvas specs (1080x1920 9:16 vertical), duration clamping (10-15s), CPU throttling (nice -n 19, -threads 2),
     silent video audio fallback (-map 0:a?).
   - Photo Story cover frame extraction (-q:v 2, 1080x1920 9:16 vertical).
   - Golden hours distribution (11:30 and 20:00 ICT = Asia/Ho_Chi_Minh).
   - Weekly quota (max 10 stories/week per Page) with automatic rollover to next Monday 11:30 ICT.
   - 50/50 alternating cadence between video and photo stories.
   - Multi-page isolation and concurrent scheduling thread safety (no duplicate slots, no cross-talk).
3. R3: Reliability, Cleanup & Zero Regressions:
   - Atomic .tmp media writes and immediate unlinking on failure.
   - CleanupService 24h stale story file retention sweep.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import JobStatus, JobType
from app.core.database.core import Base
from app.core.database.models import Job
from app.core.queue.cleanup import CleanupService
from app.core.queue.publisher_runtime import postpone_if_weekly_story_limit
from app.features.buffer.adapter import BufferAdapter
from app.features.buffer.client import BufferClient, BufferError
from app.features.buffer.first_comment import (
    FALLBACK_STARTER_COMMENTS,
    get_or_create_first_comment,
    sanitize_comment,
)
from app.features.story.media_extractor import StoryMediaExtractor, classify_story_mode
from app.features.story.scheduler import ICT, StoryPacingScheduler


# =====================================================================
# Fixtures
# =====================================================================
@pytest.fixture
def mem_db():
    """Isolated in-memory SQLite session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def file_db():
    """File-backed SQLite session for multi-threaded testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_file.db")
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            yield session, Session
        finally:
            session.close()
            engine.dispose()


# =====================================================================
# 1. R1: Automated FirstComment & Buffer Integration Stress Tests
# =====================================================================
class TestR1FirstCommentAdversarial:
    """Stress testing FirstComment sanitization, fallback, and GraphQL schema compliance."""

    @pytest.mark.parametrize(
        "raw_input,expected_fragment",
        [
            (
                '“First comment: ***Bình luận:*** \\"Video này làm mình nhớ tuổi thơ ghê!\\""',
                "Video này làm mình nhớ tuổi thơ ghê!",
            ),
            (
                "«‘`Bình luận đầu tiên: Clip hay quá, mọi người thả tim ủng hộ kênh nhé!`’»",
                "Clip hay quá, mọi người thả tim ủng hộ kênh nhé!",
            ),
            (
                "```markdown\nBình luận: Đố cả nhà tìm được điểm đặc biệt trong video này? 🎯\n```",
                "Đố cả nhà tìm được điểm đặc biệt trong video này? 🎯",
            ),
            (
                "First Comment: Xem xong nhớ bấm [lưu video](https://facebook.com) và Follow kênh nha! #reels #viral",
                "Xem xong nhớ bấm lưu video và Follow kênh nha!",
            ),
            (
                "   **BÌNH LUẬN:**   Các bác có kinh nghiệm cho em xin ít review nhé?   ",
                "Các bác có kinh nghiệm cho em xin ít review nhé?",
            ),
        ],
    )
    def test_sanitize_comment_variations(self, raw_input, expected_fragment):
        cleaned = sanitize_comment(raw_input)
        assert cleaned == expected_fragment
        assert len(cleaned) <= 150
        assert not cleaned.startswith(("First comment:", "Bình luận:", "“", '"', "'", "`", "«"))
        assert not cleaned.endswith(("”", '"', "'", "`", "»"))
        assert "#" not in cleaned
        assert "http" not in cleaned

    def test_sanitize_comment_length_clamping(self):
        """String over 150 chars must be cleanly clamped to <= 150 chars ending with '...'."""
        long_vietnamese = (
            "Chào cả nhà, đây là một câu bình luận rất dài bằng tiếng Việt có dấu "
            "với đầy đủ các thanh điệu như huyền, sắc, hỏi, ngã, nặng và cả các ký tự đặc biệt "
            "nhằm kiểm tra khả năng cắt chuỗi chính xác tuyệt đối không bị lỗi mã hóa hoặc tràn ký tự."
        )
        assert len(long_vietnamese) > 150
        cleaned = sanitize_comment(long_vietnamese)
        assert len(cleaned) <= 150
        assert cleaned.endswith("...")

    def test_all_fallback_comments_conform_to_spec(self):
        """Every single fallback comment must be non-empty, Vietnamese, and <= 150 chars."""
        assert len(FALLBACK_STARTER_COMMENTS) >= 8
        for comment in FALLBACK_STARTER_COMMENTS:
            assert isinstance(comment, str)
            assert len(comment) <= 150
            assert len(comment) > 10
            assert not comment.startswith(("First comment", "Bình luận"))

    @patch("app.core.ai.use_cases.AIUseCases.generate_first_comment")
    def test_get_or_create_first_comment_catastrophic_failures(self, mock_gen):
        """On any AI exception (timeout, 429 rate limit, 500, ValueError), fallback is returned."""
        exceptions_to_test = [
            TimeoutError("Gemini API timed out after 30s"),
            ConnectionError("Failed to connect to AI gateway"),
            BufferError("429 Rate limit exceeded"),
            ValueError("Malformed response structure"),
            RuntimeError("Unexpected memory crash"),
        ]
        for exc in exceptions_to_test:
            mock_gen.side_effect = exc
            comment = get_or_create_first_comment("Caption test", topic="review")
            assert comment in FALLBACK_STARTER_COMMENTS
            assert len(comment) <= 150

    @patch("app.core.ai.use_cases.AIUseCases.generate_first_comment")
    def test_get_or_create_first_comment_empty_or_stripped_to_empty(self, mock_gen):
        """If AI returns empty string or text that sanitizes to empty, fallback must be used."""
        empty_responses = [
            ("", {}),
            (None, {}),
            ("   \n\t  ", {}),
            ("“First comment: #tag #viral”", {}),  # Sanitizes to empty string
            ("```\n```", {}),
        ]
        for resp in empty_responses:
            mock_gen.side_effect = None
            mock_gen.return_value = resp
            comment = get_or_create_first_comment("Caption test", topic="general")
            assert comment in FALLBACK_STARTER_COMMENTS
            assert len(comment) <= 150

    def test_buffer_client_tiktok_strict_omission(self):
        """TikTok channels must NEVER include metadata or firstComment (Buffer GraphQL 422 defense)."""
        client = BufferClient("valid_test_api_key")
        client.execute = MagicMock(
            return_value={
                "createPost": {
                    "post": {"id": "tiktok_post_1", "text": "tt", "dueAt": None}
                }
            }
        )

        client.create_post(
            text="TikTok viral clip caption",
            channel_id="tiktok_channel_999",
            service="tiktok",
            first_comment="Thả tim và follow kênh nha!",
        )

        sent_query = client.execute.call_args[0][0]
        assert isinstance(sent_query, str)
        assert "metadata" not in sent_query
        assert "firstComment" not in sent_query
        assert "facebook" not in sent_query
        assert "instagram" not in sent_query

    def test_buffer_client_facebook_injection(self):
        """Facebook posts must inject metadata.facebook with type and firstComment."""
        client = BufferClient("valid_test_api_key")
        client.execute = MagicMock(
            return_value={
                "createPost": {
                    "post": {"id": "fb_post_1", "text": "fb", "dueAt": None}
                }
            }
        )

        client.create_post(
            text="Facebook reel caption",
            channel_id="fb_channel_123",
            service="facebook",
            first_comment="Có ai cùng chung cảm nhận với mình không nhỉ?",
            fb_type="post",
        )

        sent_query = client.execute.call_args[0][0]
        assert "metadata: { facebook: { type: post, firstComment: " in sent_query
        assert "Có ai cùng chung cảm nhận với mình không nhỉ?" in sent_query

    def test_buffer_client_instagram_injection(self):
        """Instagram posts must inject metadata.instagram.firstComment."""
        client = BufferClient("valid_test_api_key")
        client.execute = MagicMock(
            return_value={
                "createPost": {
                    "post": {"id": "ig_post_1", "text": "ig", "dueAt": None}
                }
            }
        )

        client.create_post(
            text="Instagram post caption",
            channel_id="ig_channel_456",
            service="instagram",
            first_comment="Thả tim và lưu lại kẻo quên nha cả nhà! ❤️",
        )

        sent_query = client.execute.call_args[0][0]
        assert "metadata: { instagram: { firstComment: " in sent_query
        assert "Thả tim và lưu lại kẻo quên nha cả nhà! ❤️" in sent_query
        assert "facebook" not in sent_query

    def test_buffer_adapter_e2e_first_comment_integration(self):
        """BufferAdapter attaching firstComment to Facebook jobs and returning in result details."""
        client = MagicMock(spec=BufferClient)
        client.create_post.return_value = {
            "id": "ext_buf_fb_1",
            "dueAt": "2026-10-25T11:30:00.000Z",
        }
        client.infer_channel_service.return_value = "facebook"

        adapter = BufferAdapter(client=client)

        job = Job(
            id=101,
            target_page="fb_channel_page_1",
            caption="Bài viết test Facebook Reels",
            auto_comment_text="Bình luận sẵn có trong DB",
            platform="facebook",
        )

        res = adapter.publish(job)
        assert res.ok is True
        assert res.external_post_id == "ext_buf_fb_1"
        assert res.details.get("firstComment") == "Bình luận sẵn có trong DB"
        client.create_post.assert_called_once()
        call_kwargs = client.create_post.call_args[1]
        assert call_kwargs["first_comment"] == "Bình luận sẵn có trong DB"
        assert call_kwargs["service"] == "facebook"


# =====================================================================
# 2. R2: Media Extraction & Story Pacing Scheduler Stress Tests
# =====================================================================
class TestR2StoryExtractionAndSchedulerAdversarial:
    """Stress testing media extraction parameters, golden hours, weekly quota, and multi-page isolation."""

    def test_classify_story_mode_boundaries(self):
        """Verify duration boundary classification rules."""
        # >30.0s -> video
        assert classify_story_mode(30.1) == "video"
        assert classify_story_mode(60.0) == "video"
        # <=30.0s -> photo
        assert classify_story_mode(30.0) == "photo"
        assert classify_story_mode(29.9) == "photo"
        assert classify_story_mode(5.0) == "photo"

        # Preferred mode video with duration >= 10.0s -> video
        assert classify_story_mode(12.0, preferred_mode="video") == "video"
        assert classify_story_mode(10.0, preferred_mode="video") == "video"
        # Preferred mode video with duration < 10.0s -> falls back to photo!
        assert classify_story_mode(9.9, preferred_mode="video") == "photo"

        # Preferred mode photo -> always photo
        assert classify_story_mode(45.0, preferred_mode="photo") == "photo"

    @patch("subprocess.run")
    def test_extract_video_story_command_parameters(self, mock_subproc):
        """Verify video story extraction enforces: 1080x1920 9:16, clamped duration, -threads 2, nice -n 19, -map 0:a?."""
        mock_subproc.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "input.mp4"
            input_file.write_bytes(b"dummy_mp4_bytes")
            output_file = Path(tmp_dir) / "output_story.mp4"

            with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=1024), patch("os.replace"):
                StoryMediaExtractor.extract_video_story(
                    str(input_file),
                    output_path=str(output_file),
                    duration=25.0,
                )

            assert mock_subproc.called
            cmd = mock_subproc.call_args[0][0]

            assert cmd[:3] == ["nice", "-n", "19"]
            assert "-threads" in cmd
            assert cmd[cmd.index("-threads") + 1] == "2"

            assert "-t" in cmd
            assert cmd[cmd.index("-t") + 1] == "15.000"

            assert "-vf" in cmd
            assert cmd[cmd.index("-vf") + 1] == (
                "scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
            )

            assert "-map" in cmd
            assert "0:a?" in cmd
            assert "-movflags" in cmd
            assert "+faststart" in cmd

    @patch("subprocess.run")
    def test_extract_photo_story_command_parameters(self, mock_subproc):
        """Verify photo story extraction enforces: sharp 9:16 JPEG (-q:v 2, 1080x1920)."""
        mock_subproc.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "input.mp4"
            input_file.write_bytes(b"dummy_mp4_bytes")
            output_file = Path(tmp_dir) / "output_story.jpg"

            with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=1024), patch("os.replace"):
                StoryMediaExtractor.extract_photo_story(
                    str(input_file),
                    output_path=str(output_file),
                    seek_sec=3.5,
                )

            assert mock_subproc.called
            cmd = mock_subproc.call_args[0][0]

            assert "-frames:v" in cmd
            assert cmd[cmd.index("-frames:v") + 1] == "1"
            assert "-q:v" in cmd
            assert cmd[cmd.index("-q:v") + 1] == "2"
            assert "-f" in cmd
            assert cmd[cmd.index("-f") + 1] == "image2"
            assert "-vf" in cmd
            assert "scale=1080:1920" in cmd[cmd.index("-vf") + 1]

    def test_pacing_scheduler_strict_golden_hours_and_weekly_quota(self, mem_db):
        """
        Verify:
        - Exactly 11:30 or 20:00 ICT timestamps.
        - Strict weekly quota: max 10 stories/week.
        - Rollover: the 11th story leaps directly to next Monday 11:30 ICT.
        - 50/50 alternating cadence between video and photo stories.
        """
        page = "pacing_test_page_1"

        # Baseline start: Monday 2026-10-26 08:00 ICT
        base_dt = datetime(2026, 10, 26, 8, 0, 0, tzinfo=ICT)
        curr_after_ts = int(base_dt.timestamp())

        scheduled_jobs: list[Job] = []

        for i in range(12):
            media_mode = StoryMediaExtractor.generate_story_filename(
                mode="video" if i % 2 == 0 else "photo", material_id=i
            )
            # Find next golden slot explicitly advancing after_ts
            slot = StoryPacingScheduler.get_next_golden_slot(mem_db, page, after_ts=curr_after_ts)
            curr_after_ts = slot

            job = StoryPacingScheduler.schedule_story(
                mem_db,
                account_id=1,
                target_page=page,
                media_path=f"/storage/media/stories/{media_mode}",
                caption=f"Story number {i+1}",
                schedule_ts=slot,
            )
            scheduled_jobs.append(job)

        # 1. Verify first 10 stories are in Week 1 (Oct 26 - Nov 01)
        w1_start, w1_end = StoryPacingScheduler.get_week_bounds(base_dt)
        for i in range(10):
            job = scheduled_jobs[i]
            assert w1_start <= job.schedule_ts < w1_end, f"Job {i+1} not in week 1"
            dt = datetime.fromtimestamp(job.schedule_ts, tz=ICT)
            assert (dt.hour, dt.minute) in ((11, 30), (20, 0))
            assert dt.second == 0

        # Verify daily pacing (2 per day: Mon, Tue, Wed, Thu, Fri)
        days = [datetime.fromtimestamp(j.schedule_ts, tz=ICT).date() for j in scheduled_jobs[:10]]
        for d in set(days):
            assert days.count(d) == 2

        # 2. Verify 11th and 12th stories rolled over to Week 2 starting Monday 2026-11-02 11:30 ICT
        w2_start = datetime(2026, 11, 2, 0, 0, 0, tzinfo=ICT)
        w2_start_ts, w2_end_ts = StoryPacingScheduler.get_week_bounds(w2_start)

        job_11 = scheduled_jobs[10]
        dt_11 = datetime.fromtimestamp(job_11.schedule_ts, tz=ICT)
        assert w2_start_ts <= job_11.schedule_ts < w2_end_ts
        assert dt_11.weekday() == 0  # Monday
        assert (dt_11.hour, dt_11.minute) == (11, 30)

        job_12 = scheduled_jobs[11]
        dt_12 = datetime.fromtimestamp(job_12.schedule_ts, tz=ICT)
        assert dt_12.weekday() == 0  # Monday evening
        assert (dt_12.hour, dt_12.minute) == (20, 0)

        # 3. Verify alternating media mode helper
        # Last job was photo (index 11 is photo) -> next mode is video
        next_mode = StoryPacingScheduler.get_next_media_mode(mem_db, page)
        expected_mode = "video" if scheduled_jobs[-1].media_path.endswith((".jpg", ".png")) else "photo"
        assert next_mode == expected_mode

    def test_multi_page_isolation_under_concurrency(self, file_db):
        """Concurrently schedule stories across 3 different pages using file-backed DB. Quotas must not bleed."""
        main_db, SessionFactory = file_db
        pages = ["page_alpha", "page_beta", "page_gamma"]
        errors = []

        # Baseline start: Monday 2026-10-26 08:00 ICT
        base_dt = datetime(2026, 10, 26, 8, 0, 0, tzinfo=ICT)
        initial_ts = int(base_dt.timestamp())

        def worker_task(target_page: str):
            thread_db = SessionFactory()
            try:
                curr_ts = initial_ts
                for i in range(10):
                    slot = StoryPacingScheduler.get_next_golden_slot(thread_db, target_page, after_ts=curr_ts)
                    curr_ts = slot
                    StoryPacingScheduler.schedule_story(
                        thread_db,
                        account_id=1,
                        target_page=target_page,
                        media_path=f"/storage/{target_page}_{i}.mp4",
                        schedule_ts=slot,
                    )
            except Exception as e:
                errors.append(e)
            finally:
                thread_db.close()

        threads = [threading.Thread(target=worker_task, args=(p,)) for p in pages]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Threading errors encountered: {errors}"

        # Verify each page has exactly 10 stories and no slot collisions within the same page
        for p in pages:
            jobs = (
                main_db.query(Job)
                .filter(Job.target_page == p, Job.job_type == JobType.STORY)
                .all()
            )
            assert len(jobs) == 10
            slots = [j.schedule_ts for j in jobs]
            assert len(slots) == len(set(slots)), f"Duplicate slots detected for page {p}"

    def test_postpone_if_weekly_story_limit_runtime_gate(self, mem_db):
        """Runtime gate postpones 11th job if page has 10 completed/active stories in ISO week."""
        page = "runtime_gate_page"
        now_dt = datetime(2026, 10, 26, 12, 0, 0, tzinfo=ICT)
        now_ts = int(now_dt.timestamp())

        # Seed 10 DONE jobs in current week
        for i in range(10):
            job = Job(
                platform="facebook",
                target_page=page,
                job_type=JobType.STORY,
                status=JobStatus.DONE,
                schedule_ts=now_ts - (i * 3600),
                finished_at=now_ts - (i * 3600),
            )
            mem_db.add(job)
        mem_db.commit()

        # Create candidate 11th job that wants to run now
        candidate_job = Job(
            id=999,
            platform="facebook",
            target_page=page,
            job_type=JobType.STORY,
            status=JobStatus.RUNNING,
            schedule_ts=now_ts,
            started_at=now_ts,
            locked_at=now_ts,
        )
        mem_db.add(candidate_job)
        mem_db.commit()

        postponed = postpone_if_weekly_story_limit(mem_db, candidate_job, now_ts=now_ts)
        assert postponed is True
        assert candidate_job.status == JobStatus.PENDING
        assert candidate_job.locked_at is None
        assert candidate_job.started_at is None

        dt_postponed = datetime.fromtimestamp(candidate_job.schedule_ts, tz=ICT)
        assert dt_postponed.weekday() == 0  # Monday
        assert (dt_postponed.hour, dt_postponed.minute) == (11, 30)


# =====================================================================
# 3. R3: Reliability, Cleanup & Zero Regressions Stress Tests
# =====================================================================
class TestR3ReliabilityAndCleanupAdversarial:
    """Stress testing atomic writes, immediate failure unlinking, and CleanupService 24h retention."""

    def test_atomic_tmp_unlinking_on_ffmpeg_exception(self):
        """When ffmpeg fails or raises an error, .tmp file is guaranteed to be unlinked immediately."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "corrupt_input.mp4"
            input_file.write_bytes(b"invalid_corrupt_data")
            output_file = Path(tmp_dir) / "output.mp4"
            tmp_file = Path(f"{output_file}.tmp")

            def mock_failing_subprocess(*args, **kwargs):
                tmp_file.write_bytes(b"partial_bytes_left_by_crash")
                return MagicMock(returncode=1, stderr="Invalid data found when processing input")

            with patch("subprocess.run", side_effect=mock_failing_subprocess):
                with pytest.raises(RuntimeError, match="FFmpeg video story extraction failed"):
                    StoryMediaExtractor.extract_video_story(
                        str(input_file),
                        output_path=str(output_file),
                    )

            assert not tmp_file.exists(), "Temporary .tmp file was NOT unlinked after ffmpeg error!"
            assert not output_file.exists()

    def test_cleanup_service_24h_story_retention_sweep(self):
        """CleanupService._cleanup_stale_story_files deletes files >24h old, preserves files <=24h."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            stories_dir = Path(tmp_dir)
            now = time.time()

            # 1. Stale story file (30 hours old)
            stale_file = stories_dir / "story_v_stale_1.mp4"
            stale_file.write_bytes(b"stale video")
            os.utime(str(stale_file), (now - 30 * 3600, now - 30 * 3600))

            # 2. Another stale photo story (25 hours old)
            stale_photo = stories_dir / "story_p_stale_2.jpg"
            stale_photo.write_bytes(b"stale photo")
            os.utime(str(stale_photo), (now - 25 * 3600, now - 25 * 3600))

            # 3. Fresh story file (2 hours old)
            fresh_file = stories_dir / "story_v_fresh_3.mp4"
            fresh_file.write_bytes(b"fresh video")
            os.utime(str(fresh_file), (now - 2 * 3600, now - 2 * 3600))

            # 4. Fresh photo story (12 hours old)
            fresh_photo = stories_dir / "story_p_fresh_4.jpg"
            fresh_photo.write_bytes(b"fresh photo")
            os.utime(str(fresh_photo), (now - 12 * 3600, now - 12 * 3600))

            deleted_count = CleanupService._cleanup_stale_story_files(ttl_hours=24, stories_dir=stories_dir)

            assert deleted_count == 2
            assert not stale_file.exists()
            assert not stale_photo.exists()
            assert fresh_file.exists()
            assert fresh_photo.exists()
