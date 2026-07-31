"""
The upload UI and the backend policy must tell the operator the same thing:
Facebook POST/Reels is video-only.
"""
from __future__ import annotations

from pathlib import Path

from app.core.queue.job import JobService

FRAGMENTS = Path(__file__).resolve().parents[1] / "app" / "templates" / "fragments"
CREATE_FORM = FRAGMENTS / "create_job_form.html"
MANUAL_FORM = FRAGMENTS / "manual_job_form.html"
DISPATCHER = Path(__file__).resolve().parents[1] / "app" / "adapters" / "dispatcher.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_bulk_reels_form_is_video_only():
    """Bulk upload chỉ tạo job Reels nên vẫn tuyệt đối video-only."""
    src = _read(CREATE_FORM)
    assert 'accept="video/*"' in src
    assert "image/*" not in src


def test_manual_form_defaults_to_video_and_only_allows_images_for_feed():
    """
    Form thủ công có 2 loại bài: Reels (video-only) và Feed (ảnh/video).
    Mặc định phải là video-only; ảnh chỉ được mở khi chọn FEED.
    """
    src = _read(MANUAL_FORM)
    assert 'accept="video/*"' in src, "mặc định phải là video-only"
    assert "'image/*,video/*'" in src, "chỉ FEED mới nới sang ảnh"
    # Việc nới lỏng phải nằm trong nhánh FEED, không phải mặc định
    feed_branch = src.split("if (isFeed)", 1)
    assert len(feed_branch) == 2
    assert "image/*,video/*" in feed_branch[1].split("} else {", 1)[0]


def test_upload_labels_do_not_invite_images():
    create = _read(CREATE_FORM)
    manual = _read(MANUAL_FORM)
    assert "video/ảnh" not in create
    assert "ảnh / video" not in manual
    assert "Kéo thả video hoặc thư mục" in create


def test_drag_and_drop_filters_to_video_extensions():
    src = _read(CREATE_FORM)
    assert "isAcceptedVideo" in src
    for ext in JobService.VIDEO_EXTENSIONS:
        assert f"'{ext}'" in src, ext
    # The old MIME-based image passthrough is gone.
    assert "file.type.startsWith('image/')" not in src


def test_dispatcher_marks_media_gate_as_validation():
    src = _read(DISPATCHER)
    assert "ERROR_TYPE_VALIDATION" in src
    assert "require_media=True" in src
