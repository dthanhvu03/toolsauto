"""
ADR-040 — test cho `app/core/account.py` (936 dòng, trước bản này KHÔNG có test nào).

Đây là file quyết định: video đi vào Page nào, link TikTok dán vào được hiểu ra sao, và
tài khoản nào còn sống. Nó ngồi giữa mọi luồng mà không ai canh.

Ưu tiên phần thuần logic (chuẩn hoá URL, bóc handle, gom đối thủ) và phần đụng DB nhưng
không đụng trình duyệt. Phần `start_login` / `confirm_login` cần Playwright thật — để ngoài.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.account import AccountService, get_discovery_keywords


# ── chuẩn hoá link nguồn TikTok ─────────────────────────────────────────────


@pytest.mark.parametrize("raw", [
    "https://www.tiktok.com/@thacaukechuyen",
    "https://www.tiktok.com/@thacaukechuyen/",
    "www.tiktok.com/@thacaukechuyen",
    "tiktok.com/@thacaukechuyen",
    "@thacaukechuyen",
    "thacaukechuyen",
    "https://www.tiktok.com/@thacaukechuyen?lang=vi",
    "https://www.tiktok.com/@thacaukechuyen#gi-do",
])
def test_moi_kieu_dan_vao_deu_ve_mot_dang(raw):
    """Owner dán kiểu gì cũng phải ra cùng một nguồn — không thì thêm trùng mà không biết."""
    assert AccountService.normalize_tiktok_source_url(raw) == "https://www.tiktok.com/@thacaukechuyen"


def test_link_video_cung_ve_trang_kenh():
    """ADR-034: dán link MỘT video để thêm cả kênh làm nguồn."""
    got = AccountService.normalize_tiktok_source_url(
        "https://www.tiktok.com/@littlebow4/video/7682702870826749192"
    )

    assert got == "https://www.tiktok.com/@littlebow4"


@pytest.mark.parametrize("raw", ["", None, "   "])
def test_rong_thi_tra_rong(raw):
    assert AccountService.normalize_tiktok_source_url(raw) == ""


def test_khong_phai_tiktok_thi_tra_nguyen_van():
    """Không đoán bừa: link lạ giữ nguyên để chỗ gọi tự từ chối."""
    assert AccountService.normalize_tiktok_source_url("https://youtube.com/@abc") == "https://youtube.com/@abc"


def test_link_rut_gon_KHONG_phai_handle():
    """
    `vt.tiktok.com/ZS8Kx/` là link rút gọn, phần đuôi là mã chuyển hướng chứ không phải tên
    kênh. Hàm hiện coi nó là handle ⇒ ra một nguồn không tồn tại.

    Ghi lại làm bằng chứng, KHÔNG vá ở ADR-040: sửa đúng thì phải gọi mạng để giải link rút
    gọn — việc riêng, cần quyết định riêng.
    """
    got = AccountService.normalize_tiktok_source_url("https://vt.tiktok.com/ZS8Kx/")

    assert got == "https://www.tiktok.com/@ZS8Kx", "hành vi hiện tại — sai, đã biết"


# ── bóc handle ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("url,expect", [
    ("https://www.tiktok.com/@ThaCauKeChuyen/video/123", "thacaukechuyen"),
    ("https://www.tiktok.com/@thacaukechuyen", "thacaukechuyen"),
    ("@thacaukechuyen", "thacaukechuyen"),
    ("", ""),
    (None, ""),
])
def test_boc_handle_ve_chu_thuong(url, expect):
    """Dùng để gom nhóm ở cảnh báo 'một kênh chiếm hết' — hoa/thường lẫn lộn là đếm sai."""
    assert AccountService.extract_tiktok_handle(url) == expect


# ── danh sách kênh đối thủ ──────────────────────────────────────────────────


def _acc(**over):
    base = dict(competitor_urls=None, page_niches_map=None, niche_topics=None, name="acc")
    base.update(over)
    return SimpleNamespace(**base)


def test_doc_duoc_dang_JSON_chuan():
    acc = _acc(competitor_urls='[{"url": "@a", "target_page": "https://fb.com/p1"}]')

    assert AccountService.extract_tiktok_competitors(acc) == [
        {"url": "https://www.tiktok.com/@a", "target_page": "https://fb.com/p1"}
    ]


def test_doc_duoc_ca_dang_cu_ngan_cach_bang_dau_phay():
    """Dữ liệu cũ trong DB là chuỗi phẩy — không được rơi mất khi đọc."""
    acc = _acc(competitor_urls="@a, @b")

    assert [x["url"] for x in AccountService.extract_tiktok_competitors(acc)] == [
        "https://www.tiktok.com/@a",
        "https://www.tiktok.com/@b",
    ]


def test_loai_link_khong_phai_tiktok():
    acc = _acc(competitor_urls='["@a", "https://youtube.com/@b"]')

    assert [x["url"] for x in AccountService.extract_tiktok_competitors(acc)] == ["https://www.tiktok.com/@a"]


@pytest.mark.parametrize("raw", [None, "", "[]", "khong phai json {{{"])
def test_du_lieu_hong_thi_tra_danh_sach_rong_chu_khong_no(raw):
    assert AccountService.extract_tiktok_competitors(_acc(competitor_urls=raw)) == []


def test_mot_tu_tron_van_duoc_coi_la_handle():
    """
    Ngã ba cố ý: dữ liệu cũ là chuỗi phẩy gồm handle trần, nên "abc" PHẢI hiểu là `@abc`.
    Cái giá là rác không dấu cách cũng thành nguồn — chỗ gọi phải tự kiểm, không dựa vào đây.
    """
    acc = _acc(competitor_urls="rac-khong-dau-cach")

    assert AccountService.extract_tiktok_competitors(acc)[0]["url"] == "https://www.tiktok.com/@rac-khong-dau-cach"


# ── thêm kênh đối thủ ───────────────────────────────────────────────────────


def test_them_kenh_moi():
    acc = _acc(competitor_urls=None)

    AccountService.append_competitor_url_if_missing(acc, "https://www.tiktok.com/@a", "https://fb.com/p1")

    assert AccountService.extract_tiktok_competitors(acc) == [
        {"url": "https://www.tiktok.com/@a", "target_page": "https://fb.com/p1"}
    ]


def test_them_lai_dung_link_cu_thi_khong_nhan_doi():
    acc = _acc(competitor_urls='[{"url": "https://www.tiktok.com/@a", "target_page": null}]')

    AccountService.append_competitor_url_if_missing(acc, "https://www.tiktok.com/@a", None)

    assert len(AccountService.extract_tiktok_competitors(acc)) == 1


def test_page_dich_rong_thi_luu_None_chu_khong_luu_chuoi_rong():
    """Chuỗi rỗng lọt xuống sẽ thành một Page đích tên rỗng ở màn gom nhóm."""
    acc = _acc(competitor_urls=None)

    AccountService.append_competitor_url_if_missing(acc, "https://www.tiktok.com/@a", "")

    assert AccountService.extract_tiktok_competitors(acc)[0]["target_page"] is None


# ── từ khoá discovery ───────────────────────────────────────────────────────


def test_uu_tien_niche_theo_tung_page():
    acc = _acc(page_niches_map={"p1": ["câu cá"], "p2": ["câu đài"]}, niche_topics="bỏ qua tôi")

    assert get_discovery_keywords(acc) == ["câu cá", "câu đài"]


def test_trung_nhau_giua_cac_page_thi_gop_lai_mot_lan():
    acc = _acc(page_niches_map={"p1": ["câu cá"], "p2": ["câu cá", "mồi"]})

    assert get_discovery_keywords(acc) == ["câu cá", "mồi"]


@pytest.mark.parametrize("raw,expect", [
    ('["câu cá", "mồi"]', ["câu cá", "mồi"]),
    ("câu cá, mồi", ["câu cá", "mồi"]),
    ("", []),
    (None, []),
])
def test_khong_co_niche_theo_page_thi_lui_ve_cap_tai_khoan(raw, expect):
    assert get_discovery_keywords(_acc(niche_topics=raw)) == expect


# ── phần đụng DB ────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database.models import Base

    monkeypatch.setattr(AccountService, "BASE_PROFILE_DIR", str(tmp_path / "profiles"))
    engine = create_engine(f"sqlite:///{tmp_path / 'a.sqlite'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_tao_tai_khoan_thi_tao_luon_thu_muc_ho_so(db, tmp_path):
    """Thiếu thư mục là Playwright ngã lúc đăng nhập — tạo ngay ở đây chứ không đợi."""
    import os

    acc = AccountService.create_account(db, "facebook", "Mê Câu Cá")

    assert acc.id and acc.name == "Mê Câu Cá"
    assert acc.profile_path.endswith(f"facebook_{acc.id}")
    assert os.path.isdir(acc.profile_path)


def test_bat_tat_tai_khoan(db):
    acc = AccountService.create_account(db, "facebook", "a")

    assert AccountService.toggle_account(db, acc.id).is_active is False
    assert AccountService.toggle_account(db, acc.id).is_active is True


def test_bat_tat_tai_khoan_khong_co_thi_bao_loi(db):
    with pytest.raises(ValueError):
        AccountService.toggle_account(db, 999)


def test_doi_ten_bo_khoang_trang_thua(db):
    acc = AccountService.create_account(db, "facebook", "a")

    assert AccountService.rename_account(db, acc.id, "  Mê Câu Cá  ").name == "Mê Câu Cá"


def test_doi_ten_bang_chuoi_rong_thi_GIU_NGUYEN(db):
    acc = AccountService.create_account(db, "facebook", "a")

    assert AccountService.rename_account(db, acc.id, "   ").name == "a"


def test_go_cuu_ho_xoa_sach_dau_vet_loi(db):
    from app.constants import AccountStatus

    acc = AccountService.create_account(db, "facebook", "a")
    acc.consecutive_fatal_failures = 5
    acc.login_error = "cookie hỏng"
    acc.is_active = False
    db.commit()

    got = AccountService.reset_failures(db, acc.id)

    assert (got.consecutive_fatal_failures, got.login_error, got.is_active) == (0, None, True)
    assert got.login_status == AccountStatus.ACTIVE


def test_copy_niche_chung_chi_dap_vao_page_CHUA_co_niche(db):
    acc = AccountService.create_account(db, "facebook", "a")
    acc.niche_topics = "câu cá, mồi"
    acc.managed_pages_list = [{"url": "p1", "name": "P1"}, {"url": "p2", "name": "P2"}]
    acc.page_niches_map = {"p1": ["đã có riêng"]}
    db.commit()

    got, updated = AccountService.apply_global_niches_to_empty_pages(db, acc.id)

    assert updated == 1
    assert got.page_niches_map == {"p1": ["đã có riêng"], "p2": ["câu cá", "mồi"]}


def test_khong_co_niche_chung_thi_bao_ro_chu_khong_lam_im(db):
    acc = AccountService.create_account(db, "facebook", "a")

    with pytest.raises(ValueError, match="Global Categories"):
        AccountService.apply_global_niches_to_empty_pages(db, acc.id)


def test_xoa_page_thi_GIU_NGUYEN_THU_TU_cac_page_con_lai(db):
    """
    Thứ tự Page không phải chuyện thẩm mỹ: setter `target_pages_list` lấy phần tử ĐẦU làm
    `target_page` — tức Page chính. Xoá một Page phụ mà danh sách bị xáo thì Page chính đổi
    theo, và video generic đi thẳng vào Page khác mà không có lỗi nào báo (xem
    `_resolve_target_page` ở processor: không khớp từ khoá thì khoá về `acc_pages[0]`).
    """
    acc = AccountService.create_account(db, "facebook", "a")
    # Đúng bộ bốn URL này tái hiện được lỗi cũ: `set()` đẩy "phu" lên đầu.
    acc.target_pages_list = [
        "https://fb.com/mecauca", "https://fb.com/tet", "https://fb.com/phu", "https://fb.com/x",
    ]
    db.commit()

    AccountService.delete_page_config(db, acc.id, "https://fb.com/tet")
    db.refresh(acc)

    assert acc.target_pages_list == ["https://fb.com/mecauca", "https://fb.com/phu", "https://fb.com/x"]
    assert acc.target_page == "https://fb.com/mecauca", "Page chính không được đổi vì xoá một Page phụ"


def test_luu_cau_hinh_MOT_page_khong_duoc_xao_ca_danh_sach(db):
    """Nặng hơn cả xoá: chỉ sửa niche của một Page phụ cũng đủ đổi Page chính."""
    acc = AccountService.create_account(db, "facebook", "a")
    acc.target_pages_list = [
        "https://fb.com/mecauca", "https://fb.com/tet", "https://fb.com/phu", "https://fb.com/x",
    ]
    db.commit()

    AccountService.update_page_config(db, acc.id, "https://fb.com/phu", True, "câu cá", "")
    db.refresh(acc)

    assert acc.target_pages_list == [
        "https://fb.com/mecauca", "https://fb.com/tet", "https://fb.com/phu", "https://fb.com/x",
    ]
    assert acc.target_page == "https://fb.com/mecauca"
    assert acc.page_niches_map["https://fb.com/phu"] == ["câu cá"]


def test_luu_cau_hinh_page_MOI_thi_them_vao_CUOI(db):
    """Page mới không được chen lên đầu — lên đầu là thành Page chính."""
    acc = AccountService.create_account(db, "facebook", "a")
    acc.target_pages_list = ["https://fb.com/mecauca"]
    db.commit()

    AccountService.update_page_config(db, acc.id, "https://fb.com/tet", True, "", "")
    db.refresh(acc)

    assert acc.target_pages_list == ["https://fb.com/mecauca", "https://fb.com/tet"]


def test_tat_page_thi_go_khoi_danh_sach_dich(db):
    acc = AccountService.create_account(db, "facebook", "a")
    acc.target_pages_list = ["https://fb.com/mecauca", "https://fb.com/tet"]
    db.commit()

    AccountService.update_page_config(db, acc.id, "https://fb.com/tet", False, "", "")
    db.refresh(acc)

    assert acc.target_pages_list == ["https://fb.com/mecauca"]


def test_luu_cau_hinh_chuan_hoa_link_doi_thu_dan_vao(db):
    """Owner dán handle trần vào ô đối thủ — phải thành link đầy đủ, không thì scan không ra."""
    acc = AccountService.create_account(db, "facebook", "a")
    acc.target_pages_list = ["https://fb.com/mecauca"]
    db.commit()

    AccountService.update_page_config(
        db, acc.id, "https://fb.com/mecauca", True, "", "@thacaukechuyen\r\nlittlebow4\n@thacaukechuyen"
    )
    db.refresh(acc)

    assert [c["url"] for c in AccountService.extract_tiktok_competitors(acc)] == [
        "https://www.tiktok.com/@thacaukechuyen",
        "https://www.tiktok.com/@littlebow4",
    ], "trùng phải gộp, xuống dòng kiểu Windows phải hiểu"


def test_xoa_page_thi_xoa_luon_niche_cua_page_do(db):
    acc = AccountService.create_account(db, "facebook", "a")
    acc.target_pages_list = ["p1", "p2"]
    acc.page_niches_map = {"p1": ["a"], "p2": ["b"]}
    db.commit()

    AccountService.delete_page_config(db, acc.id, "p2")
    db.refresh(acc)

    assert acc.page_niches_map == {"p1": ["a"]}


def test_xoa_page_khong_ton_tai_thi_khong_dung_gi(db):
    acc = AccountService.create_account(db, "facebook", "a")
    acc.target_pages_list = ["p1", "p2"]
    db.commit()

    assert AccountService.delete_page_config(db, acc.id, "khong-co") is True
    db.refresh(acc)
    assert acc.target_pages_list == ["p1", "p2"]


def test_xoa_page_cua_tai_khoan_khong_ton_tai(db):
    assert AccountService.delete_page_config(db, 999, "p1") is False
