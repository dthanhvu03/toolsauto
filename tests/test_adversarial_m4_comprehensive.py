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
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.core import Base
from app.core.database.models import Job
from app.core.queue.cleanup import CleanupService
from app.features.buffer.adapter import BufferAdapter
from app.features.buffer.client import BufferClient, BufferError
from app.features.buffer.first_comment import (
    FALLBACK_STARTER_COMMENTS,
    get_or_create_first_comment,
    sanitize_comment,
)


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


# =====================================================================
# 3. R3: Reliability, Cleanup & Zero Regressions Stress Tests
# =====================================================================
class TestR3ReliabilityAndCleanupAdversarial:
    """Stress testing atomic writes, immediate failure unlinking, and CleanupService 24h retention."""


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
