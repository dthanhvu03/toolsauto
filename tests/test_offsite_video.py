"""ADR-023 — chép bản `_reup` sang Drive khi Owner bật "Chép video đã xử lý".

Trước bản vá, `DRIVE_COPY_VIDEOS` được khai báo trong `config.py` và hiện trên trang
cài đặt nhưng **không dòng code nào đọc** — ô đó là nhãn nói dối. Test ở đây chốt cả
ba điều kiện của ADR-012 mà việc chép phải giữ: chỉ chép khi bật, chép chứ không di
chuyển, và Drive hỏng thì chỉ ghi log chứ không ném lỗi ra luồng reup.
"""
from __future__ import annotations

import time

import pytest

from app.core.storage import offsite


class _FakeSettings:
    """Thay `runtime_settings` để không đụng DB thật."""

    def __init__(self, values: dict):
        self._v = values

    def get_bool(self, key, default=False, db=None):
        return bool(self._v.get(key, default))

    def get_str(self, key, default="", db=None):
        return str(self._v.get(key, default))


@pytest.fixture
def drive_root(tmp_path):
    return tmp_path / "drive"


def _use_settings(monkeypatch, values):
    monkeypatch.setattr(offsite, "_settings", lambda: _FakeSettings(values))


def _make_video(tmp_path, name="viral_1_abc_reup.mp4", data=b"x" * 2048):
    src = tmp_path / name
    src.write_bytes(data)
    return src


def test_bat_co_thi_chep_sang_thu_muc_videos(tmp_path, drive_root, monkeypatch):
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)

    dest = offsite.copy_video_if_enabled(src)

    assert dest is not None
    # ADR-030: thêm một cấp thư mục theo tháng. Không truyền tiêu đề ⇒ giữ tên file gốc.
    assert dest == drive_root / "videos" / time.strftime("%Y-%m") / src.name
    assert dest.is_file() and dest.read_bytes() == src.read_bytes()
    # ADR-012 nguyên tắc 1: chép, KHÔNG di chuyển — bản gốc phải còn nguyên
    assert src.is_file()


def test_tat_co_video_thi_khong_chep_du_drive_dang_bat(tmp_path, drive_root, monkeypatch):
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": False, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)

    assert offsite.copy_video_if_enabled(src) is None
    assert not (drive_root / "videos").exists()


def test_tat_drive_tong_thi_khong_chep(tmp_path, drive_root, monkeypatch):
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": False, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    assert offsite.copy_video_if_enabled(_make_video(tmp_path)) is None


def test_thu_muc_drive_khong_ton_tai_thi_bo_qua_khong_nem_loi(tmp_path, monkeypatch):
    _use_settings(
        monkeypatch,
        {
            "DRIVE_COPY_ENABLED": True,
            "DRIVE_COPY_VIDEOS": True,
            "DRIVE_ROOT_DIR": str(tmp_path / "khong-ton-tai"),
        },
    )
    assert offsite.copy_video_if_enabled(_make_video(tmp_path)) is None


def test_doc_setting_hong_thi_bo_qua_khong_nem_loi(tmp_path, monkeypatch):
    def _no(*_a, **_k):
        raise RuntimeError("settings chet")

    monkeypatch.setattr(offsite, "_settings", _no)
    assert offsite.copy_video_if_enabled(_make_video(tmp_path)) is None


def test_file_nguon_khong_ton_tai_thi_bo_qua(tmp_path, drive_root, monkeypatch):
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    assert offsite.copy_video_if_enabled(tmp_path / "khong-co.mp4") is None


def test_processor_goi_copy_video_mot_diem_chung_cho_ca_hai_nhanh():
    """Điểm gọi phải nằm TRƯỚC nhánh rẽ ADR-018, để cả video đăng tay (READY) lẫn
    video có job đều được chép — video đăng tay còn cần Drive hơn vì Owner tải bằng
    điện thoại."""
    src = (
        __import__("pathlib").Path("app/features/viral_intake/processor.py")
        .read_text(encoding="utf-8")
    )
    assert "copy_video_if_enabled(" in src
    goi = src.index("copy_video_if_enabled(")
    re_nhanh = src.index("if target_account is None:")
    assert goi < re_nhanh, "phải gọi trước khi rẽ nhánh READY, nếu không video đăng tay bị bỏ sót"


def test_chep_lan_hai_cung_file_thi_bo_qua_khong_tai_len_lai(tmp_path, drive_root, monkeypatch):
    """ADR-024 mục 1: mỗi lần "Reup lại" trước đây đều copy2 đè lại cả video ~30 MB lên
    Drive dù nội dung y hệt. Nay cùng tên + cùng kích thước ⇒ bỏ qua."""
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)

    first = offsite.copy_video_if_enabled(src)
    assert first is not None and first.is_file()
    mtime_sau_lan_dau = first.stat().st_mtime_ns

    goi = {"n": 0}
    import shutil as _sh

    real_copy = _sh.copy2

    def _dem(*a, **k):
        goi["n"] += 1
        return real_copy(*a, **k)

    monkeypatch.setattr(_sh, "copy2", _dem)
    second = offsite.copy_video_if_enabled(src)

    assert second == first
    assert goi["n"] == 0, "lần hai không được gọi copy2 nữa"
    assert first.stat().st_mtime_ns == mtime_sau_lan_dau, "file đích không bị ghi đè"


def test_kich_thuoc_khac_thi_van_chep_de(tmp_path, drive_root, monkeypatch):
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path, data=b"a" * 1024)
    offsite.copy_video_if_enabled(src)

    src.write_bytes(b"b" * 4096)  # reup lại ra bản khác
    dest = offsite.copy_video_if_enabled(src)

    assert dest is not None and dest.stat().st_size == 4096


# ---------------------------------------------------------------------------
# ADR-030 — tên theo tiêu đề, thư mục theo tháng, đường dẫn tương đối
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title,expected", [
    ("Nay tui đi câu mực nha anh em", "949 - Nay tui đi câu mực nha anh em.mp4"),
    # Ký tự Windows từ chối → thay bằng khoảng trắng, gộp lại
    ('Cá to: 5kg? "khủng" | biển <đông>/ngày', "949 - Cá to 5kg khủng biển đông ngày.mp4"),
    # Windows từ chối tên kết thúc bằng dấu chấm hoặc khoảng trắng
    ("Kết thúc bằng chấm...", "949 - Kết thúc bằng chấm.mp4"),
])
def test_ten_file_giu_dau_tieng_viet_va_bo_ky_tu_cam(title, expected):
    assert offsite.safe_video_name("viral_949_abc_reup.mp4", 949, title) == expected


def test_tieu_de_dai_bi_cat_nhung_van_giu_id_va_duoi_file():
    name = offsite.safe_video_name("x_reup.mp4", 12, "A" * 300)

    assert name.startswith("12 - ") and name.endswith(".mp4")
    assert len(name) < 100, "Windows giới hạn cả đường dẫn 260 ký tự, tên phải ngắn"


@pytest.mark.parametrize("title", [None, "", "   ", "  ...  ", r'\/:*?<>|'])
def test_tieu_de_rong_hoac_toan_ky_tu_cam_thi_lui_ve_ten_goc(title):
    """Không bao giờ được trả tên rỗng — file không tên là hỏng cả lượt chép."""
    assert offsite.safe_video_name("viral_1_abc_reup.mp4", 1, title) == "viral_1_abc_reup.mp4"


def test_giu_id_o_dau_vi_kenh_nguon_co_nhieu_video_trung_ten():
    """Kênh của Owner có 4 clip cùng tên 'Muốn giàu phải ra biển' — bỏ ID là ghi đè nhau."""
    a = offsite.safe_video_name("x_reup.mp4", 101, "Muốn giàu phải ra biển")
    b = offsite.safe_video_name("y_reup.mp4", 102, "Muốn giàu phải ra biển")

    assert a != b and a.startswith("101 - ") and b.startswith("102 - ")


def test_chep_video_dat_ten_theo_tieu_de_va_xep_thu_muc_thang(tmp_path, drive_root, monkeypatch):
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)

    dest = offsite.copy_video_if_enabled(src, material_id=949, title="Nay tui đi câu mực nha anh em")

    assert dest == drive_root / "videos" / time.strftime("%Y-%m") / "949 - Nay tui đi câu mực nha anh em.mp4"
    assert dest.read_bytes() == src.read_bytes()
    assert src.is_file(), "ADR-012 nguyên tắc 1: chép chứ không di chuyển"
    # Tên file GỐC trên máy không được đổi — find_reup_path và cả luồng xử lý dựa vào nó
    assert src.name == "viral_1_abc_reup.mp4"


def test_ten_moi_van_giu_co_che_bo_qua_ban_y_het_cua_ADR_024(tmp_path, drive_root, monkeypatch):
    """
    Chỗ dễ gãy nhất của ADR-030: đổi cách đặt tên mà làm hỏng chỗ này thì mỗi lần
    "Reup lại" lại tải lên Drive cả video ~30 MB.
    """
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)
    kw = dict(material_id=949, title="Nay tui đi câu mực nha anh em")

    first = offsite.copy_video_if_enabled(src, **kw)
    assert first is not None

    import shutil as _sh

    goi = {"n": 0}
    real_copy = _sh.copy2
    monkeypatch.setattr(_sh, "copy2", lambda *a, **k: (goi.__setitem__("n", goi["n"] + 1), real_copy(*a, **k))[1])

    second = offsite.copy_video_if_enabled(src, **kw)

    assert second == first
    assert goi["n"] == 0, "cùng tên + cùng cỡ thì không được chép lại"


def test_duong_dan_tuong_doi_dung_dinh_dang_hien_cho_nguoi_dung(tmp_path, drive_root, monkeypatch):
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)
    dest = offsite.copy_video_if_enabled(src, material_id=949, title="Nay tui đi câu mực")

    rel = offsite.relative_to_root(dest)

    assert rel == f"videos/{time.strftime('%Y-%m')}/949 - Nay tui đi câu mực.mp4"
    assert "\\" not in rel, "dùng dấu / cho dễ đọc, kể cả trên Windows"


def test_khong_chep_duoc_thi_khong_co_duong_dan():
    assert offsite.relative_to_root(None) is None


def test_backup_khong_bi_doi_cho(tmp_path, drive_root, monkeypatch):
    """`kind="backup"` phải giữ thư mục phẳng — lệnh khôi phục đang trông vào đó."""
    drive_root.mkdir()
    _use_settings(monkeypatch, {"DRIVE_COPY_ENABLED": True, "DRIVE_ROOT_DIR": str(drive_root)})
    src = _make_video(tmp_path, name="dump.sql")

    dest = offsite.copy_out(src, "backup")

    assert dest == drive_root / "backups" / "dump.sql"


# ---------------------------------------------------------------------------
# Review nhiều mũ (2026-09-09) — hợp đồng "không ném lỗi" và tên file từ chữ người lạ
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title", [
    "../../etc/passwd",
    r"..\..\Windows\System32",
    "..",
    "....//....//x",
    "/etc/passwd",
])
def test_tieu_de_khong_the_thoat_ra_ngoai_thu_muc_dich(title, tmp_path, drive_root, monkeypatch):
    """
    Tiêu đề là chữ do NGƯỜI LẠ viết (lấy từ TikTok) và nay thành tên file. Không được có
    dấu phân cách nào lọt qua, và bản chép phải nằm đúng trong thư mục tháng.
    """
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)

    dest = offsite.copy_video_if_enabled(src, material_id=7, title=title)

    assert dest is not None
    assert dest.parent == drive_root / "videos" / time.strftime("%Y-%m")
    assert "/" not in dest.name and "\\" not in dest.name
    assert dest.resolve().is_relative_to(drive_root.resolve())


class _NoStr:
    """Object có __str__ nổ — thế thân cho mọi thứ bất thường lọt vào tiêu đề."""

    def __str__(self):
        raise RuntimeError("tiêu đề hỏng")


def test_dung_ten_file_hong_thi_bo_qua_chu_khong_ném_loi(tmp_path, drive_root, monkeypatch):
    """
    Hồi quy: `safe_video_name` từng nằm NGOÀI try/except của `copy_video_if_enabled`, trong
    khi docstring hứa "KHÔNG BAO GIỜ ném lỗi". Hàm này chạy SAU khi video đã xử lý xong —
    một ngoại lệ thoát ra là hỏng cả lượt xử lý chỉ vì bản chép phụ.
    """
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)

    assert offsite.copy_video_if_enabled(src, material_id=1, title=_NoStr()) is None
    assert offsite.copy_video_if_enabled(None, material_id=1, title="x") is None


def test_duong_dan_tuong_doi_hong_thi_tra_None_chu_khong_ném_loi(monkeypatch):
    """
    Hàm này hay được gọi ngay trong danh sách tham số của `notify_*`, tức chạy TRƯỚC khi vào
    hàm đó — try/except bên trong notifier không đỡ được.
    """
    def no(*a, **k):
        raise RuntimeError("settings chết")

    monkeypatch.setattr(offsite, "get_root", no)

    assert offsite.relative_to_root(__import__("pathlib").Path("/x/y.mp4")) == "y.mp4"


def test_sang_thang_moi_thi_chep_them_mot_ban(tmp_path, drive_root, monkeypatch):
    """
    Ghi lại hành vi đã biết, không phải lỗi: thư mục theo tháng lấy theo THỜI ĐIỂM CHÉP, nên
    một video reup lại ở tháng sau sẽ có thêm một bản ở thư mục tháng mới. Cơ chế bỏ qua bản
    y hệt của ADR-024 chỉ so trong cùng thư mục. Chấp nhận được: reup lại là việc hiếm, và
    đổi lại thư mục không phình ra vài nghìn file.
    """
    drive_root.mkdir()
    _use_settings(
        monkeypatch,
        {"DRIVE_COPY_ENABLED": True, "DRIVE_COPY_VIDEOS": True, "DRIVE_ROOT_DIR": str(drive_root)},
    )
    src = _make_video(tmp_path)
    kw = dict(material_id=949, title="Nay tui đi câu mực")

    monkeypatch.setattr(offsite.time, "strftime", lambda fmt: "2026-09")
    thang_9 = offsite.copy_video_if_enabled(src, **kw)
    monkeypatch.setattr(offsite.time, "strftime", lambda fmt: "2026-10")
    thang_10 = offsite.copy_video_if_enabled(src, **kw)

    assert thang_9.parent.name == "2026-09" and thang_10.parent.name == "2026-10"
    assert thang_9.is_file() and thang_10.is_file()
