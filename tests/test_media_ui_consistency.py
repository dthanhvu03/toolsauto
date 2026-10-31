"""
The upload UI and the backend policy must tell the operator the same thing:
Facebook POST/Reels is video-only.
"""
from __future__ import annotations

from pathlib import Path

from app.core.queue.job import JobService

FRAGMENTS = Path(__file__).resolve().parents[1] / "app" / "templates" / "fragments"
CREATE_FORM = FRAGMENTS / "create_job_form.html"
DISPATCHER = Path(__file__).resolve().parents[1] / "app" / "adapters" / "dispatcher.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_bulk_reels_form_is_video_only():
    """
    Bulk upload chỉ tạo job Reels nên ô media vẫn tuyệt đối video-only.

    Từ PLAN-055 form có thêm một input ảnh — nhưng là ảnh *kèm comment*, không
    phải media của bài. Test tách bạch hai thứ đó thay vì cấm chữ "image".
    """
    src = _read(CREATE_FORM)
    assert 'accept="video/*"' in src
    assert "image/*" not in src, "ô media của bài không được nhận ảnh"
    # Input ảnh duy nhất được phép là ảnh comment, và phải liệt kê đuôi cụ thể.
    assert 'id="bulk-comment-image"' in src
    assert 'accept="image/jpeg,image/png"' in src


def test_story_media_is_mandatory_in_form_and_backend():
    """Tin không có ảnh/video thì không đăng được (form tạo job FB đã gỡ — PLAN-108)."""
    import pytest

    with pytest.raises(ValueError):
        JobService.assert_story_media(None)


def test_upload_labels_do_not_invite_images():
    create = _read(CREATE_FORM)
    assert "video/ảnh" not in create
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


def test_label_does_not_promise_formats_the_backend_rejects():
    """
    Chữ hiển thị cho người dùng phải khớp với định dạng thật sự nhận được.

    Đã lệch một lần: nhãn kéo-thả quảng cáo `.webp` trong khi
    `accept="image/jpeg,image/png"` và `JobService.IMAGE_EXTENSIONS` đều không có
    `.webp` — người dùng chọn file webp rồi bị chặn oan mà không hiểu vì sao.

    Nhãn nói dối không làm test nào đỏ, nên phải có test riêng canh nó.
    """
    from app.core.queue.job import JobService

    for name in ("create_job_form.html",):
        src = (FRAGMENTS / name).read_text(encoding="utf-8")
        for ext in (".webp", ".gif", ".bmp", ".heic", ".avif"):
            assert ext not in JobService.IMAGE_EXTENSIONS, (
                f"{ext} nay da duoc ho tro — cap nhat test nay va nhan hien thi"
            )
            assert ext not in src, (
                f"{name} nhac toi {ext} nhung JobService.IMAGE_EXTENSIONS khong nhan "
                f"({JobService.IMAGE_EXTENSIONS}) — nguoi dung se bi chan oan"
            )
