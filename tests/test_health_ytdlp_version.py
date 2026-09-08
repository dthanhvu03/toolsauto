"""Trang Sức khỏe hệ thống phải nói được yt-dlp có cũ không.

Bối cảnh 2026-09-08: Owner quét kênh TikTok trên laptop, nhận
``ERROR: [tiktok:user] … Unable to extract secondary user ID``. Cùng kênh đó chạy tốt trên
máy dev với yt-dlp ``2026.08.19`` — tức lỗi là **phần mềm cũ**, không phải kênh hỏng. Trước
bản vá này không chỗ nào trong tool nói cho Owner biết điều đó; nguồn chỉ hiện lỗi đỏ khó
hiểu. TikTok/YouTube đổi liên tục nên chuyện này sẽ lặp lại.
"""
from __future__ import annotations

import app.core.observability.health as health


def _fake_metadata_version(monkeypatch, value):
    import importlib.metadata as md

    monkeypatch.setattr(md, "version", lambda name: value)


def test_doc_duoc_ban_dang_cai_va_ban_ghim(monkeypatch):
    info = health._ytdlp_version_status()
    assert info["error"] is None
    assert info["installed"], "phải đọc được phiên bản yt-dlp đang cài"
    assert info["pinned"], "phải đọc được bản ghim trong requirements.txt"


def test_ban_cu_hon_ban_ghim_thi_bao_outdated(monkeypatch):
    _fake_metadata_version(monkeypatch, "2026.3.3")
    info = health._ytdlp_version_status()
    assert info["installed"] == "2026.3.3"
    assert info["outdated"] is True, "2026.3.3 phải bị coi là cũ hơn bản ghim 2026.8.19"


def test_ban_moi_hon_hoac_bang_thi_khong_bao(monkeypatch):
    _fake_metadata_version(monkeypatch, "2099.12.31")
    assert health._ytdlp_version_status()["outdated"] is False


def test_so_sanh_theo_so_khong_theo_chuoi(monkeypatch):
    """`"2026.8.19" < "2026.3.3"` là SAI khi so chuỗi (vì '8' > '3'), nhưng so theo số thì
    2026.8.19 mới hơn. Chốt để không ai đổi sang so chuỗi."""
    _fake_metadata_version(monkeypatch, "2026.10.1")
    assert health._ytdlp_version_status()["outdated"] is False
    _fake_metadata_version(monkeypatch, "2025.12.31")
    assert health._ytdlp_version_status()["outdated"] is True


def test_khong_doc_duoc_phien_ban_thi_bao_loi_chu_khong_nem(monkeypatch):
    import importlib.metadata as md

    def _boom(_name):
        raise RuntimeError("khong tim thay goi")

    monkeypatch.setattr(md, "version", _boom)
    info = health._ytdlp_version_status()
    assert info["installed"] is None
    assert info["error"] and "không đọc được" in info["error"]
    assert info["outdated"] is False
