"""
ADR-040 — hai khối tách khỏi `_process_viral_materials`: dựng caption metadata và chọn Page đích.

Logic chọn Page (round-robin vs chấm điểm từ khoá) nằm trong hàm 770 dòng suốt từ ADR-020 và
**chưa từng có test nào**. Đây là chỗ quyết định video đi vào Page nào — sai thì Page câu cá
nhận video nấu ăn, mà không có lỗi nào báo. Tách ra rồi thì khoá luôn.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.features.viral_intake.processor import _caption_metadata_for, _resolve_target_page


def _mat(**over):
    base = dict(title=None, platform="tiktok", views=0, target_page=None)
    base.update(over)
    return SimpleNamespace(**base)


class _Account:
    """Tài khoản giả — `pick_next_target_page` đếm số lần bị gọi để phân biệt round-robin thật."""

    def __init__(self, pages=None, niches=None, target_page=""):
        self.name = "acc"
        self.target_pages_list = pages or []
        self.page_niches_map = niches
        self.target_page = target_page
        self.picks = 0

    def pick_next_target_page(self, db):
        self.picks += 1
        return f"rr-{self.picks}"


# ── caption metadata ────────────────────────────────────────────────────────


def test_khong_co_tieu_de_thi_dung_ngu_canh_thay_the():
    meta, boost = _caption_metadata_for(_mat(views=12400))

    assert meta == "[AI_GENERATE] Context: Video tiktok 12400 views."
    assert boost is None


def test_dau_ngoac_kep_trong_tieu_de_bi_doi_thanh_nhay_don():
    """Chuỗi này đi vào prompt AI — ngoặc kép lọt vào là vỡ ngữ cảnh."""
    meta, _ = _caption_metadata_for(_mat(title='Câu cá "khủng" ở hồ'))

    assert '"' not in meta
    assert "Câu cá 'khủng' ở hồ" in meta


def test_boc_marker_boost_va_lam_sach_tieu_de():
    meta, boost = _caption_metadata_for(
        _mat(title="Câu cá đêm ### BOOST_CONTEXT: niche=cauca ### thu hoạch")
    )

    assert boost == "niche=cauca"
    assert "ORIGINAL_VIRAL_TITLE: Câu cá đêm thu hoạch ###" in meta, "marker phải bị bóc khỏi tiêu đề"
    assert meta.endswith("### BOOST_CONTEXT: niche=cauca ###"), "và nối lại ở cuối, đúng một lần"


def test_marker_bi_boc_khong_de_lai_hai_dau_cach_dinh_nhau():
    """Bản regex để XOÁ ăn cả khoảng trắng hai bên — gộp chung với bản để ĐỌC là hỏng chỗ này."""
    meta, _ = _caption_metadata_for(_mat(title="A ### BOOST_CONTEXT: x ### B"))

    assert "ORIGINAL_VIRAL_TITLE: A B ###" in meta


def test_tieu_de_chi_co_moi_marker_thi_giu_nguyen_chuoi_dau():
    """Bóc xong còn rỗng ⇒ không có gì để thay, giữ chuỗi dựng ban đầu (hành vi sẵn có)."""
    meta, boost = _caption_metadata_for(_mat(title="### BOOST_CONTEXT: niche=abc ###"))

    assert boost == "niche=abc"
    assert meta.count("BOOST_CONTEXT") == 2, "một trong tiêu đề chưa bóc được, một nối ở cuối"


# ── chọn Page đích ──────────────────────────────────────────────────────────


def test_page_dat_san_tren_material_thang_tat_ca():
    acc = _Account(pages=["p1", "p2"], niches={"p1": ["a"], "p2": ["b"]})

    assert _resolve_target_page(None, _mat(target_page="chon-tay"), acc) == "chon-tay"
    assert acc.picks == 0, "đã chốt Page thì không được đụng round-robin"


def test_tai_khoan_khong_co_page_nao_thi_ve_page_mac_dinh():
    acc = _Account(pages=[], target_page="mac-dinh")

    assert _resolve_target_page(None, _mat(), acc) == "mac-dinh"


def test_mot_page_duy_nhat_thi_lay_luon():
    acc = _Account(pages=["chi-mot"])

    assert _resolve_target_page(None, _mat(), acc) == "chi-mot"
    assert acc.picks == 0


def test_cac_page_cung_niche_thi_chia_deu():
    acc = _Account(pages=["p1", "p2"], niches={"p1": ["cauca"], "p2": ["cauca"]})

    assert _resolve_target_page(None, _mat(title="gì đó"), acc) == "rr-1"
    assert acc.picks == 1


def test_khong_khai_niche_thi_van_coi_la_cung_niche():
    acc = _Account(pages=["p1", "p2"], niches=None)

    assert _resolve_target_page(None, _mat(), acc) == "rr-1"


def test_niche_khac_nhau_thi_KHONG_chia_deu_ma_cham_diem_tu_khoa():
    """Đây là lý do tồn tại của cả khối: chia đều giữa các Page khác niche là đẩy video sai chỗ."""
    acc = _Account(pages=["p-nauan", "p-cauca"], niches={"p-nauan": ["nấu ăn"], "p-cauca": ["câu cá"]})

    assert _resolve_target_page(None, _mat(title="Đi câu cá đêm"), acc) == "p-cauca"
    assert acc.picks == 0, "khác niche mà vẫn gọi round-robin là hỏng"


def test_cham_diem_theo_tung_tu_khi_khong_khop_ca_cum():
    acc = _Account(pages=["p1", "p2"], niches={"p1": ["ẩm thực"], "p2": ["câu cá biển"]})

    assert _resolve_target_page(None, _mat(title="Ra biển bắt cá"), acc) == "p2"


@pytest.mark.parametrize("title", ["Chuyện lạ đó đây", "", None])
def test_khac_niche_ma_khong_khop_gi_thi_khoa_ve_page_dau(title):
    acc = _Account(pages=["p-chinh", "p-phu"], niches={"p-chinh": ["nấu ăn"], "p-phu": ["câu cá"]})

    assert _resolve_target_page(None, _mat(title=title), acc) == "p-chinh"
    assert acc.picks == 0


def test_tu_ngan_khong_duoc_tinh_diem():
    """
    Chỉ từ dài hơn 3 ký tự mới cộng điểm. Nếu tính cả từ ngắn thì "ăn" và "to" khớp gần như
    mọi tiêu đề, và Page nào có niche nhiều từ ngắn sẽ hút hết video.

    Đặt bẫy hẳn hoi: `p-ngan` có HAI từ ngắn cùng xuất hiện trong tiêu đề (2 điểm nếu tính),
    `p-dai` chỉ có MỘT từ dài (1 điểm). Tính sai là chọn `p-ngan`.
    """
    acc = _Account(pages=["p-dai", "p-ngan"], niches={"p-dai": ["thuyền lớn"], "p-ngan": ["ăn to"]})

    assert _resolve_target_page(None, _mat(title="Thuyền ra khơi, ăn cá to"), acc) == "p-dai"


def test_khop_ca_cum_an_dut_hai_tu_dai_le_te():
    """Cụm nguyên vẹn = 3 điểm, mỗi từ dài = 1 điểm."""
    acc = _Account(pages=["p-le", "p-cum"], niches={"p-le": ["thuyền chài"], "p-cum": ["câu cá"]})

    assert _resolve_target_page(None, _mat(title="Thuyền ra khơi, chài lưới rồi câu cá"), acc) == "p-cum"


def test_hoa_diem_thi_page_dung_TRUOC_thang():
    """
    Ba từ dài lẻ tẻ cũng được 3 điểm, đúng bằng một cụm khớp — và so sánh là `>` chứ không
    phải `>=`, nên Page duyệt trước giữ ngôi. Ghi lại vì đây là hành vi thật, không phải chủ ý
    thiết kế: thứ tự Page trong tài khoản đang là một phần của cách chọn.
    """
    niches = {"p-le": ["thuyền chài lưới"], "p-cum": ["câu cá"]}
    title = "Thuyền chài buông lưới rồi câu cá"

    assert _resolve_target_page(None, _mat(title=title), _Account(pages=["p-le", "p-cum"], niches=niches)) == "p-le"
    assert _resolve_target_page(None, _mat(title=title), _Account(pages=["p-cum", "p-le"], niches=niches)) == "p-cum"
