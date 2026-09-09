"""Trang Sức khỏe hệ thống phải nói được yt-dlp có cũ không.

Bối cảnh 2026-09-08: Owner quét kênh TikTok trên laptop, nhận
``ERROR: [tiktok:user] … Unable to extract secondary user ID``. Cùng kênh đó chạy tốt trên
máy dev với yt-dlp ``2026.08.19`` — tức lỗi là **phần mềm cũ**, không phải kênh hỏng. Trước
bản vá này không chỗ nào trong tool nói cho Owner biết điều đó; nguồn chỉ hiện lỗi đỏ khó
hiểu. TikTok/YouTube đổi liên tục nên chuyện này sẽ lặp lại.
"""
from __future__ import annotations

import pytest

import app.core.observability.health as health


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    """Đo phiên bản có nhớ tạm 5 phút (ADR-029) — không dọn thì test này ăn kết quả test kia."""
    health._ytdlp_probe_cache.update({"at": 0.0, "value": None})
    yield
    health._ytdlp_probe_cache.update({"at": 0.0, "value": None})


def _fake_metadata_version(monkeypatch, value):
    import importlib.metadata as md

    monkeypatch.setattr(md, "version", lambda name: value)


def _fake_probe(monkeypatch, version, binary="/venv/bin/yt-dlp", error=None):
    """ADR-029: `installed` nay lấy từ BINARY tool thật sự gọi, không phải từ gói trong venv."""
    monkeypatch.setattr(
        health, "_probe_ytdlp_binary",
        lambda: {"binary": binary, "version": version, "error": error},
    )


def test_doc_duoc_ban_dang_cai_va_ban_ghim(monkeypatch):
    info = health._ytdlp_version_status()
    assert info["error"] is None
    assert info["installed"], "phải đọc được phiên bản yt-dlp đang cài"
    assert info["pinned"], "phải đọc được bản ghim trong requirements.txt"


def test_ban_cu_hon_ban_ghim_thi_bao_outdated(monkeypatch):
    _fake_probe(monkeypatch, "2026.3.3")
    info = health._ytdlp_version_status()
    assert info["installed"] == "2026.3.3"
    assert info["outdated"] is True, "2026.3.3 phải bị coi là cũ hơn bản ghim 2026.8.19"


def test_ban_moi_hon_hoac_bang_thi_khong_bao(monkeypatch):
    _fake_probe(monkeypatch, "2099.12.31")
    assert health._ytdlp_version_status()["outdated"] is False


def test_so_sanh_theo_so_khong_theo_chuoi(monkeypatch):
    """`"2026.8.19" < "2026.3.3"` là SAI khi so chuỗi (vì '8' > '3'), nhưng so theo số thì
    2026.8.19 mới hơn. Chốt để không ai đổi sang so chuỗi."""
    _fake_probe(monkeypatch, "2026.10.1")
    assert health._ytdlp_version_status()["outdated"] is False
    _fake_probe(monkeypatch, "2025.12.31")
    assert health._ytdlp_version_status()["outdated"] is True


def test_khong_doc_duoc_phien_ban_thi_bao_loi_chu_khong_nem(monkeypatch):
    import importlib.metadata as md

    def _boom(_name):
        raise RuntimeError("khong tim thay goi")

    monkeypatch.setattr(md, "version", _boom)
    _fake_probe(monkeypatch, None, error="không chạy được yt-dlp: hỏng")
    info = health._ytdlp_version_status()
    assert info["installed"] is None
    assert info["error"] and "không đọc được" in info["error"]
    assert info["outdated"] is False


# ── ADR-029: báo đúng BINARY đang chạy, không phải gói trong venv ────────────


def test_installed_lay_tu_binary_chu_khong_phai_goi_trong_venv(monkeypatch):
    """
    Đây là gốc của cả buổi chẩn đoán 2026-09-09: PATH có yt-dlp cũ 17 tháng, venv có bản
    mới, mà trang Sức khỏe đọc bản trong venv nên báo "ổn".
    """
    _fake_metadata_version(monkeypatch, "2026.8.19")     # gói trong venv: mới
    _fake_probe(monkeypatch, "2025.3.31", binary=r"C:\Python312\Scripts\yt-dlp.exe")

    info = health._ytdlp_version_status()

    assert info["installed"] == "2025.3.31", "phải là bản của binary đang chạy"
    assert info["package"] == "2026.8.19"
    assert info["outdated"] is True
    assert info["binary"] == r"C:\Python312\Scripts\yt-dlp.exe"


def test_binary_lech_goi_thi_bao_mismatch(monkeypatch):
    _fake_metadata_version(monkeypatch, "2026.8.19")
    _fake_probe(monkeypatch, "2025.3.31")

    assert health._ytdlp_version_status()["mismatch"] is True


def test_binary_khop_goi_thi_khong_bao_mismatch(monkeypatch):
    _fake_metadata_version(monkeypatch, "2026.8.19")
    _fake_probe(monkeypatch, "2026.08.19")  # khác cách viết số 0, so theo số phải coi là bằng

    assert health._ytdlp_version_status()["mismatch"] is False


def test_do_binary_hong_thi_lui_ve_phien_ban_goi(monkeypatch):
    """Không đo được binary thì vẫn còn số của gói để hiện, hơn là bỏ trống."""
    _fake_metadata_version(monkeypatch, "2026.8.19")
    _fake_probe(monkeypatch, None, error="không chạy được yt-dlp: FileNotFoundError")

    info = health._ytdlp_version_status()

    assert info["installed"] == "2026.8.19"
    assert info["mismatch"] is False, "không đo được thì không được kết luận là lệch"
    assert "không chạy được" in info["error"]


def test_do_phien_ban_khong_bao_gio_nem_loi(monkeypatch):
    """Trang Sức khỏe không được chết vì một lượt đo phiên bản."""
    import subprocess

    def _boom(*a, **k):
        raise RuntimeError("subprocess chết")

    monkeypatch.setattr(subprocess, "run", _boom)

    probe = health._probe_ytdlp_binary()

    assert probe["version"] is None and probe["error"]


def test_do_phien_ban_co_nho_tam_khong_goi_lai_moi_lan(monkeypatch):
    """`get_system_health` bị gọi bởi web, /health/json và cả lệnh Telegram — không được
    sinh một tiến trình con mỗi lượt."""
    goi = {"n": 0}
    import subprocess

    real = subprocess.run

    def _dem(*a, **k):
        goi["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(subprocess, "run", _dem)

    health._probe_ytdlp_binary()
    health._probe_ytdlp_binary()
    health._probe_ytdlp_binary()

    assert goi["n"] == 1, "lần thứ hai trở đi phải lấy từ nhớ tạm"


def test_khong_doc_duoc_requirements_van_con_canh_bao_lech(monkeypatch, tmp_path):
    """
    Hồi quy trên chính bản vá ADR-029: `mismatch` từng được tính SAU lượt đọc
    `requirements.txt`, mà đường đó có `return` sớm khi đọc hỏng. Cảnh báo "có yt-dlp lạ chen
    vào" là thứ đáng giá nhất — không được biến mất chỉ vì một thứ khác cũng hỏng.
    """
    _fake_metadata_version(monkeypatch, "2026.8.19")
    _fake_probe(monkeypatch, "2025.3.31")

    class _NoRead:
        def resolve(self):
            return self

        @property
        def parents(self):
            raise RuntimeError("không đọc được requirements.txt")

    monkeypatch.setattr(health, "Path", lambda *a, **k: _NoRead())

    info = health._ytdlp_version_status()

    assert info["mismatch"] is True, "vẫn phải cảnh báo dù không đọc được bản ghim"
    assert info["pinned"] is None
    assert info["error"]


def test_so_sanh_phien_ban_theo_so_o_cap_module():
    """`_version_key` nay dùng chung cho cả `outdated` lẫn `mismatch`."""
    assert health._version_key("2026.10.1") > health._version_key("2026.8.19")
    assert health._version_key("2026.08.19") == health._version_key("2026.8.19")
