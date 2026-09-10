"""
ADR-029 — tool phải chạy đúng bản yt-dlp đã ghim, không phải bản đầu tiên trên PATH.

Sự cố 2026-09-09: máy Owner có `yt-dlp.exe` cài toàn cục **cũ 17 tháng** nằm trên PATH, thắng
bản 2026.8.19 trong venv. Quét TikTok gãy âm thầm, còn trang Sức khỏe đọc phiên bản gói trong
venv nên vẫn báo "ổn". Thứ tự tìm binary là gốc của chuyện đó.
"""
from __future__ import annotations

import sys

import pytest

from app.core import yt_dlp_path


@pytest.fixture
def fake_venv(tmp_path, monkeypatch):
    """Giả một venv: `<venv>/Scripts/python.exe` + `yt-dlp.exe` cạnh nó."""
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(scripts / "python.exe"))
    return scripts


def test_uu_tien_binary_trong_venv_hon_PATH(fake_venv, monkeypatch):
    """Đúng ca của Owner: có bản lạ trên PATH thì vẫn phải chọn bản của dự án."""
    venv_bin = fake_venv / "yt-dlp.exe"
    venv_bin.write_text("", encoding="utf-8")
    monkeypatch.setattr(yt_dlp_path.shutil, "which", lambda name: r"C:\Python312\Scripts\yt-dlp.exe")

    assert yt_dlp_path.yt_dlp_binary() == str(venv_bin)


def test_khong_co_binary_thi_dung_python_m_yt_dlp_chu_chua_dung_PATH(fake_venv, monkeypatch):
    """`python -m yt_dlp` vẫn là bản đã ghim vì đi theo đúng trình thông dịch đang chạy."""
    monkeypatch.setattr(yt_dlp_path.shutil, "which", lambda name: r"C:\Python312\Scripts\yt-dlp.exe")

    head = yt_dlp_path.yt_dlp_binary()

    assert head == [str(fake_venv / "python.exe"), "-m", "yt_dlp"]


def test_khong_import_duoc_goi_thi_moi_lui_ve_PATH(fake_venv, monkeypatch):
    monkeypatch.setattr(yt_dlp_path.shutil, "which", lambda name: r"C:\Python312\Scripts\yt-dlp.exe")
    monkeypatch.setitem(sys.modules, "yt_dlp", None)  # `import yt_dlp` → ImportError

    assert yt_dlp_path.yt_dlp_binary() == r"C:\Python312\Scripts\yt-dlp.exe"


def test_khong_co_gi_ca_thi_tra_ten_tran(fake_venv, monkeypatch):
    monkeypatch.setattr(yt_dlp_path.shutil, "which", lambda name: None)
    monkeypatch.setitem(sys.modules, "yt_dlp", None)

    assert yt_dlp_path.yt_dlp_binary() == "yt-dlp"


def test_bo_cuc_linux_cung_duoc_nhan(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").write_text("", encoding="utf-8")
    (bin_dir / "yt-dlp").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(bin_dir / "python"))
    monkeypatch.setattr(yt_dlp_path.shutil, "which", lambda name: "/usr/bin/yt-dlp")

    assert yt_dlp_path.yt_dlp_binary() == str(bin_dir / "yt-dlp")


def test_yt_dlp_cmd_ghep_dung_tham_so(fake_venv, monkeypatch):
    (fake_venv / "yt-dlp.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(yt_dlp_path.shutil, "which", lambda name: None)

    argv = yt_dlp_path.yt_dlp_cmd("--version", "--no-warnings")

    assert argv == [str(fake_venv / "yt-dlp.exe"), "--version", "--no-warnings"]


def test_dang_chay_that_thi_khong_bao_gio_tra_rong():
    """Bảo hiểm: dù máy nào chạy, hàm cũng phải trả một argv dùng được."""
    head = yt_dlp_path.yt_dlp_binary()

    assert head and (isinstance(head, str) or len(head) == 3)
