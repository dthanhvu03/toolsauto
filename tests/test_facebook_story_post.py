"""
Luồng đăng tin (story) Facebook — JobType.STORY (PLAN-054).

Tin khác cả Reels lẫn bài feed: bắt buộc có media, nhận cả ảnh lẫn video, và
không sinh COMMENT job. Selector của hộp tạo tin chỉ kiểm chứng được khi chạy
live — ở đây khoá phần logic thuần và phần nối dây.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.constants import JobType
from app.core.queue.job import JobService
from app.features.facebook.adapter import FacebookAdapter
from app.features.facebook.pages.story_composer import (
    SHARE_BUTTON_DENY,
    SHARE_BUTTON_LABELS,
    STORY_ENTRY_LABELS,
    FacebookStoryComposer,
)

ROOT = Path(__file__).resolve().parents[1]


# ── cổng media của tin ────────────────────────────────────────────────────────

def test_tin_bat_buoc_co_media():
    with pytest.raises(ValueError) as e:
        JobService.assert_story_media(None)
    assert "bắt buộc" in str(e.value).lower() or "thiếu media" in str(e.value).lower()

    with pytest.raises(ValueError):
        JobService.assert_story_media("   ")


def test_tin_nhan_ca_anh_lan_video():
    JobService.assert_story_media("tin.jpg")
    JobService.assert_story_media("tin.png")
    JobService.assert_story_media("tin.mp4")
    JobService.assert_story_media("tin.mov")


def test_tin_tu_choi_file_la():
    with pytest.raises(ValueError):
        JobService.assert_story_media("tin.exe")
    with pytest.raises(ValueError):
        JobService.assert_story_media("tin.pdf")


def test_cong_reels_khong_ep_video_len_tin():
    """Tin ảnh không được rơi vào cổng video-only của Reels."""
    JobService.assert_facebook_post_media("facebook", "tin.jpg", job_type="STORY")
    with pytest.raises(ValueError):
        JobService.assert_facebook_post_media("facebook", None, job_type="STORY")


def test_story_nam_trong_nhom_khong_qua_composer_reels():
    assert "STORY" in JobService.NON_REELS_JOB_TYPES


def test_tao_job_tin_khong_media_bi_chan_ngay_luc_tao():
    """Chặn từ lúc tạo, không để job chết ở bước đăng (db không bị đụng tới)."""
    with pytest.raises(ValueError):
        JobService.create_manual_job_with_file(
            None, 1, "https://www.facebook.com/kids0810", "cap", None, job_type=JobType.STORY
        )


# ── chữ phủ lên tin (link affiliate) ──────────────────────────────────────────

class _Job:
    def __init__(self, tracking_url=None, affiliate_url=None, caption=None):
        self.tracking_url = tracking_url
        self.affiliate_url = affiliate_url
        self.caption = caption


def test_uu_tien_link_co_dem_click():
    job = _Job(tracking_url="https://t.io/r/ab12", affiliate_url="https://shp.ee/x", caption="cap")
    assert FacebookAdapter.story_overlay_text(job) == "https://t.io/r/ab12"


def test_khong_co_tracking_thi_dung_link_aff_goc():
    job = _Job(tracking_url=None, affiliate_url="https://shp.ee/x", caption="cap")
    assert FacebookAdapter.story_overlay_text(job) == "https://shp.ee/x"


def test_khong_co_link_nao_thi_dung_caption():
    assert FacebookAdapter.story_overlay_text(_Job(caption="  giảm giá hôm nay  ")) == "giảm giá hôm nay"


def test_khong_co_gi_thi_tin_van_dang_duoc_khong_chu():
    assert FacebookAdapter.story_overlay_text(_Job()) == ""


# ── chặn đăng nhầm danh nghĩa ─────────────────────────────────────────────────

def _adapter():
    return FacebookAdapter()


def test_chan_khi_chip_tac_gia_la_nguoi_khac():
    assert _adapter()._story_author_mismatch("Chia sẻ dưới tên Nguyen Van A", "Kids 0810") is True


def test_khong_chan_khi_chip_tac_gia_dung_page():
    a = _adapter()
    assert a._story_author_mismatch("Chia sẻ dưới tên Kids 0810", "Kids 0810") is False
    # dấu tiếng Việt và hoa/thường không được làm lệch kết quả
    assert a._story_author_mismatch("Đăng dưới tên SHOP ĐỒ CHƠI", "shop do choi") is False


def test_khong_doc_duoc_ten_thi_khong_chan():
    """DOM tin đổi liên tục — không đọc được tên mà chặn cứng là khoá luôn tính năng."""
    a = _adapter()
    assert a._story_author_mismatch(None, "Kids 0810") is False
    assert a._story_author_mismatch("", "Kids 0810") is False
    assert a._story_author_mismatch("Chia sẻ dưới tên ai đó", None) is False


# ── bắt link tin từ GraphQL ───────────────────────────────────────────────────

def test_bat_link_tin_theo_marker_rieng():
    payload = {"d": {"story": {"url": "https://www.facebook.com/stories/1234567890/"}}}
    urls = FacebookAdapter._walk_for_post_urls(payload, markers=FacebookAdapter.STORY_URL_MARKERS)
    assert urls == ["https://www.facebook.com/stories/1234567890/"]


def test_link_bai_viet_khong_bi_nham_thanh_link_tin():
    payload = {"d": {"url": "https://www.facebook.com/kids0810/posts/123456789012"}}
    assert FacebookAdapter._walk_for_post_urls(payload, markers=FacebookAdapter.STORY_URL_MARKERS) == []


# ── page object ───────────────────────────────────────────────────────────────

def test_composer_phan_biet_anh_va_video():
    assert FacebookStoryComposer.is_image("a.jpg") and FacebookStoryComposer.is_image("a.webp")
    assert FacebookStoryComposer.is_video("a.mp4") and FacebookStoryComposer.is_video("a.mov")
    assert not FacebookStoryComposer.is_image("a.mp4")
    assert not FacebookStoryComposer.is_video("a.jpg")


def test_nhan_co_ca_tieng_viet_lan_tieng_anh():
    """Profile có thể ở locale nào — thiếu một bên là hỏng ở máy khách."""
    assert any("Tạo tin" == label for label in STORY_ENTRY_LABELS)
    assert any("Create story" == label for label in STORY_ENTRY_LABELS)
    assert any("Chia sẻ lên tin" == label for label in SHARE_BUTTON_LABELS)
    assert any("Share to story" == label for label in SHARE_BUTTON_LABELS)


def test_khong_bam_nham_nut_chia_se_len_feed():
    """Bấm nhầm 'Chia sẻ lên bảng feed' là đăng bài chứ không phải đăng tin."""
    assert "chia sẻ lên bảng feed" in SHARE_BUTTON_DENY
    assert "share to feed" in SHARE_BUTTON_DENY


# ── nối dây ───────────────────────────────────────────────────────────────────

def test_dispatcher_re_nhanh_story():
    src = (ROOT / "app" / "adapters" / "dispatcher.py").read_text(encoding="utf-8")
    assert "if job_type == JobType.STORY:" in src
    assert "adapter.publish_story(job)" in src


def test_dispatcher_tra_lai_media_path_goc_sau_khi_dang_tin():
    """Đổi media_path để đưa cho adapter thì phải trả lại, không rò sang job sau."""
    src = (ROOT / "app" / "adapters" / "dispatcher.py").read_text(encoding="utf-8")
    story_block = src.split("if job_type == JobType.STORY:", 1)[1].split("# POST job", 1)[0]
    assert "finally:" in story_block
    assert "job.media_path = original_path" in story_block


def test_adapter_co_publish_story():
    assert hasattr(FacebookAdapter, "publish_story")


def test_form_co_lua_chon_tin():
    src = (ROOT / "app" / "templates" / "fragments" / "manual_job_form.html").read_text(encoding="utf-8")
    assert 'name="job_type" value="STORY"' in src


def test_router_bao_dung_loai_bai():
    src = (ROOT / "app" / "features" / "facebook" / "manual_job_router.py").read_text(encoding="utf-8")
    assert '"STORY": "Tin"' in src
