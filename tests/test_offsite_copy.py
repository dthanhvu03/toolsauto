"""
Sao chép ngoại vi sang Drive (ADR-012).

Trọng tâm không phải "chép có thành công không" — mà là **thất bại có im lặng đúng
cách không**. Người gọi `copy_out` là lệnh backup và luồng đăng bài; cả hai không
được chết chỉ vì Drive chưa gắn ổ hay hết dung lượng.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.storage import offsite


@pytest.fixture()
def drive(tmp_path, monkeypatch):
    """Bật sao lưu ngoại vi, trỏ vào một thư mục tạm đóng vai ổ Drive."""
    root = tmp_path / "drive"
    root.mkdir()
    monkeypatch.setattr(offsite, "get_root", lambda: root)
    return root


def _make_file(tmp_path: Path, name: str = "dump.sql") -> Path:
    src = tmp_path / name
    src.write_text("SELECT 1;", encoding="utf-8")
    return src


def test_copy_puts_file_in_subdir_by_kind(drive, tmp_path):
    src = _make_file(tmp_path)

    dest = offsite.copy_out(src, "backup")

    assert dest is not None
    assert dest == drive / "backups" / "dump.sql"
    assert dest.read_text(encoding="utf-8") == "SELECT 1;"


def test_source_is_kept_not_moved(drive, tmp_path):
    """Sao chép, KHÔNG di chuyển — bản chính phải luôn còn ở máy."""
    src = _make_file(tmp_path)

    offsite.copy_out(src, "backup")

    assert src.exists(), "file gốc bị mất — Drive chỉ được là bản thứ hai"


def test_disabled_returns_none_without_touching_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(offsite, "get_root", lambda: None)
    src = _make_file(tmp_path)

    assert offsite.copy_out(src, "backup") is None
    assert src.exists()


def test_missing_drive_folder_does_not_raise(tmp_path, monkeypatch):
    """Drive chưa gắn ổ: thư mục không tồn tại. Phải trả None, không ném lỗi."""
    monkeypatch.setattr(offsite, "get_root", lambda: tmp_path / "chua_gan_o")
    src = _make_file(tmp_path)

    assert offsite.copy_out(src, "backup") is None


def test_write_failure_does_not_raise(drive, tmp_path, monkeypatch):
    """Hết dung lượng / Drive khoá file — người gọi vẫn phải chạy tiếp."""
    src = _make_file(tmp_path)

    def boom(*_a, **_k):
        raise OSError("There is not enough space on the disk")

    monkeypatch.setattr(offsite.shutil, "copy2", boom)

    assert offsite.copy_out(src, "backup") is None


def test_missing_source_does_not_raise(drive, tmp_path):
    assert offsite.copy_out(tmp_path / "khong_ton_tai.sql", "backup") is None


def test_check_root_rejects_missing_folder(tmp_path):
    ok, message = offsite.check_root(tmp_path / "khong_co")
    assert ok is False
    assert "Không thấy thư mục" in message


def test_check_root_accepts_writable_folder(drive):
    ok, message = offsite.check_root(drive)
    assert ok is True
    assert str(drive) in message


def test_check_root_leaves_no_probe_file(drive):
    offsite.check_root(drive)
    assert list(drive.iterdir()) == [], "file thăm dò phải được dọn sau khi kiểm tra"


def test_kinds_map_to_known_subdirs():
    """
    Chốt danh sách loại nội dung được phép.

    DB đang chạy và profile trình duyệt KHÔNG được có mặt ở đây: Drive đồng bộ liên
    tục còn hai thứ đó ghi liên tục — xung đột đồng bộ làm hỏng dữ liệu âm thầm, và
    profile hỏng nghĩa là mất phiên đăng nhập.
    """
    assert set(offsite.SUBDIRS) == {"backup", "video"}
    assert "profile" not in offsite.SUBDIRS
    assert "database" not in offsite.SUBDIRS
