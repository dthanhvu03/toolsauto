"""
Chờ upload theo dung lượng thật — PLAN-056.

Bug gốc: `attach_media` chờ cứng 20s cho mọi video. Video dài chưa upload xong đã
bấm Đăng. Test khoá lại quan hệ "file càng nặng, ngân sách càng lớn" và cái trần.
"""
from __future__ import annotations

from pathlib import Path

from app.features.facebook.pages.feed_composer import (
    IMAGE_UPLOAD_WAIT_MS,
    VIDEO_UPLOAD_BASE_MS,
    VIDEO_UPLOAD_MAX_MS,
    FacebookFeedComposer,
)

ROOT = Path(__file__).resolve().parents[1]


def _make_file(tmp_path: Path, name: str, size_mb: float) -> str:
    path = tmp_path / name
    with open(path, "wb") as f:
        f.write(b"\0" * int(size_mb * 1024 * 1024))
    return str(path)


def test_anh_van_cho_ngan_nhu_cu(tmp_path):
    """Không được làm chậm luồng ảnh vốn đang chạy tốt."""
    anh = _make_file(tmp_path, "a.jpg", 0.5)
    assert FacebookFeedComposer.upload_budget_ms([anh]) == IMAGE_UPLOAD_WAIT_MS


def test_bai_chu_thuan_khong_cho_gi_them(tmp_path):
    assert FacebookFeedComposer.upload_budget_ms([]) == IMAGE_UPLOAD_WAIT_MS


def test_video_cang_nang_ngan_sach_cang_lon(tmp_path):
    nho = _make_file(tmp_path, "ngan.mp4", 2)
    to = _make_file(tmp_path, "dai.mp4", 60)

    ngan_sach_nho = FacebookFeedComposer.upload_budget_ms([nho])
    ngan_sach_to = FacebookFeedComposer.upload_budget_ms([to])

    assert ngan_sach_nho >= VIDEO_UPLOAD_BASE_MS
    assert ngan_sach_to > ngan_sach_nho
    # Video 60MB phải được chờ lâu hơn hằng số 20s cũ — đúng chỗ bug nằm.
    assert ngan_sach_to > 20_000


def test_co_tran_de_khong_treo_vo_han(tmp_path):
    khong_lo = _make_file(tmp_path, "khong-lo.mp4", 120)
    # Giả lập file rất lớn mà không phải ghi 5GB xuống đĩa
    budget = FacebookFeedComposer.upload_budget_ms([khong_lo] * 40)
    assert budget == VIDEO_UPLOAD_MAX_MS


def test_khong_doc_duoc_dung_luong_van_co_ngan_sach_mac_dinh():
    """File biến mất giữa chừng thì vẫn phải chờ, không được rơi về 0."""
    budget = FacebookFeedComposer.upload_budget_ms(["D:/khong/co/that.mp4"])
    assert budget > VIDEO_UPLOAD_BASE_MS


def test_anh_lan_video_thi_tinh_theo_video(tmp_path):
    anh = _make_file(tmp_path, "a.png", 1)
    video = _make_file(tmp_path, "v.mp4", 30)
    assert FacebookFeedComposer.upload_budget_ms([anh, video]) > IMAGE_UPLOAD_WAIT_MS


# ── vòng chờ dừng sớm khi có preview ─────────────────────────────────────────

class _FakePage:
    """Page giả: đếm số lần chờ, báo có preview sau N vòng."""

    def __init__(self, ready_after_polls: int):
        self.ready_after_polls = ready_after_polls
        self.polls = 0
        self.total_waited = 0

    def wait_for_timeout(self, ms):
        self.total_waited += ms
        self.polls += 1


class _Composer(FacebookFeedComposer):
    def __init__(self, page, ready_after_polls):
        super().__init__(page)
        self._ready_after = ready_after_polls

    def media_preview_ready(self) -> bool:
        return self.page.polls >= self._ready_after


def test_thay_preview_thi_di_tiep_ngay_khong_cho_het_ngan_sach(tmp_path):
    video = _make_file(tmp_path, "v.mp4", 40)
    page = _FakePage(ready_after_polls=3)
    composer = _Composer(page, ready_after_polls=3)

    assert composer.wait_for_media_ready([video]) is True
    # Dừng sớm: tổng thời gian chờ phải nhỏ hơn hẳn ngân sách của file 40MB
    assert page.total_waited < FacebookFeedComposer.upload_budget_ms([video])


def test_khong_bao_gio_thay_preview_thi_het_ngan_sach_moi_thoi(tmp_path):
    anh = _make_file(tmp_path, "a.jpg", 1)
    page = _FakePage(ready_after_polls=10**9)
    composer = _Composer(page, ready_after_polls=10**9)

    assert composer.wait_for_media_ready([anh]) is False
    assert page.total_waited >= IMAGE_UPLOAD_WAIT_MS


def test_khong_con_cho_cung_20_giay():
    src = (ROOT / "app" / "features" / "facebook" / "pages" / "feed_composer.py").read_text(
        encoding="utf-8"
    )
    assert "wait_ms = 20000" not in src
    assert "self.wait_for_media_ready(existing)" in src
