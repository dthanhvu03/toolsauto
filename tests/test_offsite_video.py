"""ADR-023 — chép bản `_reup` sang Drive khi Owner bật "Chép video đã xử lý".

Trước bản vá, `DRIVE_COPY_VIDEOS` được khai báo trong `config.py` và hiện trên trang
cài đặt nhưng **không dòng code nào đọc** — ô đó là nhãn nói dối. Test ở đây chốt cả
ba điều kiện của ADR-012 mà việc chép phải giữ: chỉ chép khi bật, chép chứ không di
chuyển, và Drive hỏng thì chỉ ghi log chứ không ném lỗi ra luồng reup.
"""
from __future__ import annotations

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
    assert dest == drive_root / "videos" / src.name
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
    assert "copy_video_if_enabled(media_path)" in src
    goi = src.index("copy_video_if_enabled(media_path)")
    re_nhanh = src.index("if target_account is None:")
    assert goi < re_nhanh, "phải gọi trước khi rẽ nhánh READY, nếu không video đăng tay bị bỏ sót"
