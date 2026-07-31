"""
Luồng đăng bài feed Facebook (chữ thuần / chữ + ảnh) — JobType.FEED.

Reels (POST) vẫn bắt buộc video; FEED thì media là tùy chọn và nhận cả ảnh.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import JobType
from app.core.database.models.accounts import Account
from app.core.database.models.jobs import Job, JobEvent
from app.core.database.models.viral import ViralMaterial
from app.core.queue.job import JobService
from app.features.facebook.pages.feed_composer import FacebookFeedComposer


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'feed.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    JobEvent.__table__.create(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _account(db, name="acc1"):
    acc = Account(
        name=name, platform="facebook", is_active=True, login_status="ACTIVE",
        profile_path=f"/tmp/{name}", consecutive_fatal_failures=0,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


class _Upload:
    def __init__(self, filename: str, data: bytes = b"x" * 16):
        self.filename = filename
        self.file = io.BytesIO(data)


# ── validation ────────────────────────────────────────────────────────────────


def test_feed_accepts_image():
    JobService.assert_facebook_post_media("facebook", "anh.png", job_type="FEED")
    JobService.assert_facebook_post_media("facebook", "anh.jpg", job_type="FEED")
    JobService.assert_facebook_post_media("facebook", "clip.mp4", job_type="FEED")


def test_feed_accepts_no_media_at_all():
    """Bài chữ thuần — đây là điểm khác Reels."""
    JobService.assert_facebook_post_media("facebook", None, job_type="FEED")
    JobService.assert_facebook_post_media("facebook", "", job_type="FEED", require_media=True)


def test_feed_rejects_junk_file():
    with pytest.raises(ValueError, match="chỉ nhận ảnh hoặc video"):
        JobService.assert_facebook_post_media("facebook", "virus.exe", job_type="FEED")


def test_reels_still_requires_video():
    """Không được nới lỏng nhầm sang Reels."""
    with pytest.raises(ValueError, match="chỉ nhận video"):
        JobService.assert_facebook_post_media("facebook", "anh.png", job_type="POST")
    with pytest.raises(ValueError, match="Thiếu media"):
        JobService.assert_facebook_post_media("facebook", None, job_type="POST", require_media=True)


# ── tạo job ───────────────────────────────────────────────────────────────────


def test_create_text_only_feed_job(db):
    account = _account(db)
    job = JobService.create_high_priority_manual_job(
        db, account.id, "https://fb.com/page", caption="bài chữ thuần",
        media_path=None, job_type=JobType.FEED,
    )
    assert job.job_type == JobType.FEED
    assert job.media_path is None
    assert job.caption == "bài chữ thuần"


def test_create_feed_job_with_image(db, tmp_path, monkeypatch):
    account = _account(db)
    monkeypatch.setattr("app.config.CONTENT_DIR", tmp_path)
    job = JobService.create_manual_job_with_file(
        db, account.id, "https://fb.com/page", "caption", _Upload("anh.png"),
        job_type=JobType.FEED,
    )
    assert job.job_type == JobType.FEED
    assert job.media_path.endswith(".png")


def test_reels_job_still_rejects_image_upload(db, tmp_path, monkeypatch):
    account = _account(db)
    monkeypatch.setattr("app.config.CONTENT_DIR", tmp_path)
    with pytest.raises(ValueError, match="chỉ nhận video"):
        JobService.create_manual_job_with_file(
            db, account.id, "https://fb.com/page", "caption", _Upload("anh.png"),
            job_type=JobType.POST,
        )
    manual_dir = tmp_path / "manual"
    assert not manual_dir.exists() or list(manual_dir.glob("*")) == []


def test_default_job_type_is_reels(db):
    """Không truyền job_type thì phải giữ nguyên hành vi cũ."""
    account = _account(db)
    job = JobService.create_high_priority_manual_job(
        db, account.id, "https://fb.com/page", caption="chỉ caption", media_path=None
    )
    assert job.job_type == JobType.POST


# ── composer ──────────────────────────────────────────────────────────────────


def test_composer_media_type_detection():
    assert FacebookFeedComposer.is_image("a.PNG")
    assert FacebookFeedComposer.is_image("a.webp")
    assert not FacebookFeedComposer.is_image("a.mp4")
    assert FacebookFeedComposer.is_video("a.mp4")
    assert not FacebookFeedComposer.is_video(None)


def test_composer_labels_cover_vietnamese_and_english():
    from app.features.facebook.pages import feed_composer as fc

    joined = " ".join(fc.COMPOSER_ENTRY_LABELS).lower()
    assert "bạn đang nghĩ gì" in joined
    assert "what's on your mind" in joined
    assert "Đăng" in fc.POST_BUTTON_LABELS and "Post" in fc.POST_BUTTON_LABELS
    # Nút dễ bấm nhầm phải nằm trong danh sách loại trừ
    for bad in ("đăng nhập", "đăng ký", "lên lịch"):
        assert bad in fc.POST_BUTTON_DENY


# ── dispatcher / adapter ──────────────────────────────────────────────────────


def test_adapter_exposes_publish_feed():
    from app.features.facebook.adapter import FacebookAdapter

    assert hasattr(FacebookAdapter, "publish_feed")


def test_composer_handles_page_next_step():
    """Composer của Page có bước 'Tiếp' trước 'Đăng' — đã gặp thật khi chạy live."""
    from app.features.facebook.pages import feed_composer as fc

    assert "Tiếp" in fc.NEXT_BUTTON_LABELS
    assert "Next" in fc.NEXT_BUTTON_LABELS
    assert hasattr(fc.FacebookFeedComposer, "advance_to_post_button")


def test_post_url_walker_picks_permalinks():
    from app.features.facebook.adapter import FacebookAdapter

    payload = {
        "data": {
            "story_create": {
                "story": {
                    "url": "https://www.facebook.com/kids0810/posts/pfbid123?ref=x",
                    "id": "12345",
                }
            }
        }
    }
    urls = FacebookAdapter._walk_for_post_urls(payload)
    assert urls == ["https://www.facebook.com/kids0810/posts/pfbid123"]


def test_post_url_walker_ignores_unrelated_strings():
    from app.features.facebook.adapter import FacebookAdapter

    assert FacebookAdapter._walk_for_post_urls({"a": "https://www.facebook.com/kids0810"}) == []
    assert FacebookAdapter._walk_for_post_urls({"a": 1, "b": None}) == []


def test_dispatcher_routes_feed_before_reels_flow():
    src = (ROOT / "app" / "adapters" / "dispatcher.py").read_text(encoding="utf-8")
    assert "if job_type == JobType.FEED:" in src
    assert "adapter.publish_feed(job)" in src
    # Gate video-only phải bỏ qua FEED
    assert "not in (str(JobType.COMMENT), str(JobType.FEED))" in src


def test_form_offers_both_job_types():
    src = (ROOT / "app" / "templates" / "fragments" / "manual_job_form.html").read_text(encoding="utf-8")
    assert 'name="job_type" value="POST"' in src
    assert 'name="job_type" value="FEED"' in src
    assert "syncManualJobType" in src
