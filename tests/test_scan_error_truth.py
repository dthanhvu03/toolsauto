"""
2026-09-11 — /nguon phải nói thật: lỗi quét đọc được, và biết quét LÚC NÀO.

Ảnh chụp của Owner: `❌ ERROR: MS4wLjABAAAAMgUb…: Failed to parse JSON (caused by JSO` — sec_uid
60 ký tự chiếm hết chỗ, phần có nghĩa bị cắt; và "tìm được lần cuối: 0" không nói lần cuối là
lúc nào. Chạy đúng lệnh đó ở máy dev với yt-dlp 2026.08.19 ra 21 video 3/3 lần ⇒ lỗi nằm ở máy
chạy bot, và tin nhắn phải chỉ Owner tới đó.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from app.features.viral_intake import sources as srcmod
from app.features.viral_intake.sources import humanize_scan_error

OWNER_STDERR = (
    "ERROR: MS4wLjABAAAAMgUbPA6oIGGcX7yl0__2kSP_0aeeresNEOf8RsraKcdygGfYqJn5GMSrYFQZDC8Z: "
    "Failed to parse JSON (caused by JSONDecodeError('Expecting value: line 1 column 1 (char 0)'))"
)


def test_loi_that_cua_owner_thanh_cau_hanh_dong_duoc():
    msg = humanize_scan_error("tiktok", OWNER_STDERR)

    assert "MS4wLjAB" not in msg, "sec_uid không được chiếm chỗ trong tin"
    assert "yt-dlp" in msg, "phải tự khai bản yt-dlp hoặc chỉ Owner tới chỗ kiểm được"
    assert len(msg) <= 300, "cột last_error và tin Telegram cắt ở 300 — dài hơn là mất phần đuôi"


@pytest.mark.parametrize("stderr,needle", [
    ("ERROR: [TikTok] x: Unable to extract webpage video data", "cập nhật yt-dlp"),
    ("ERROR: HTTP Error 429: Too Many Requests", "429"),
    ("ERROR: [TikTok] abc: Unable to extract secondary user id", "link MỘT video"),
    ("ERROR: [youtube] xyz: HTTP Error 404: Not Found", "không tồn tại"),
    ("ERROR: This channel is private", "riêng tư"),
    ("ERROR: Read timed out", "hết giờ"),
])
def test_cac_loi_quen_thuoc_duoc_dich(stderr, needle):
    assert needle in humanize_scan_error("tiktok", stderr)


def test_loi_la_thi_bo_dau_ERROR_id_giu_phan_co_nghia():
    got = humanize_scan_error("youtube", "WARNING: gì đó\nERROR: [youtube] abcdefgh: Lý do lạ hoắc")

    assert got == "Lý do lạ hoắc"


def test_stderr_rong_thi_noi_ro_khong_co_ly_do():
    assert "không nói lý do" in humanize_scan_error("tiktok", "")


def test_scan_source_luu_loi_da_dich_chu_khong_luu_stderr_tho(tmp_path, monkeypatch):
    """Đường thật: `scan_source` → subprocess (giả) trả stderr của Owner → `last_error` đọc được."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database.models import Base, ViralSource

    engine = create_engine(f"sqlite:///{tmp_path / 's.sqlite'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    src = ViralSource(platform="tiktok", url="tiktokuser:MS4wLjAB", handle="thacaukechuyen", enabled=True,
                      min_views=5000, max_videos=30)
    db.add(src)
    db.commit()
    monkeypatch.setattr(srcmod, "_load_rate_limits", lambda: {})
    monkeypatch.setattr(
        srcmod.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, stdout="", stderr=OWNER_STDERR),
    )

    found, skipped, error = srcmod.SourceService.scan_source(db, src)

    assert found == 0 and error
    assert "MS4wLjAB" not in src.last_error and "yt-dlp" in src.last_error
    assert src.last_scanned_at, "phải ghi LÚC NÀO quét, kể cả khi hỏng"
    db.close()
    engine.dispose()


# ── /nguon nói rõ lúc nào ───────────────────────────────────────────────────


class _Client:
    def __init__(self):
        self.msgs = []

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)


@pytest.fixture
def nguon(monkeypatch):
    import app.core.database.core as dbcore
    from app.core import feature_hooks
    from app.features.telegram_bot.command_handler import TelegramCommandHandler

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(dbcore, "SessionLocal", lambda: _S())
    state = {"rows": []}
    monkeypatch.setattr(feature_hooks, "call", lambda name, *a, **k: state["rows"])
    client = _Client()
    handler = TelegramCommandHandler(client)

    def run(**over):
        base = {"id": 3, "platform": "tiktok", "handle": "thacaukechuyen", "min_views": 5000, "max_videos": 30,
                "enabled": True, "last_scanned_at": None, "last_found": 0, "last_error": None}
        base.update(over)
        state["rows"] = [base]
        client.msgs.clear()
        handler.handle_command("nguon")
        return " ".join(client.msgs)

    return run


def test_chua_quet_thi_noi_chua_quet(nguon):
    assert "Chưa quét lần nào" in nguon()


def test_quet_ok_co_video_moi_thi_ghi_gio_va_so(nguon):
    text = nguon(last_scanned_at=1757560320, last_found=3)

    assert "Quét lúc" in text and "✅ 3 video mới" in text


def test_quet_ok_khong_co_gi_moi_KHONG_phai_hong(nguon):
    text = nguon(last_scanned_at=1757560320, last_found=0)

    assert "⚪ không có video mới" in text and "hỏng" not in text


def test_quet_hong_thi_ghi_gio_va_ly_do(nguon):
    text = nguon(last_scanned_at=1757560320, last_found=0, last_error="TikTok trả về trang không phải dữ liệu")

    assert "❌ hỏng" in text and "không phải dữ liệu" in text and "Quét lúc" in text


# ── test không được ghi vào log thật ────────────────────────────────────────


def test_test_khong_ghi_vao_log_production():
    import app.config as config

    log_dir = os.environ.get("LOG_DIR")

    assert log_dir and os.path.abspath(log_dir) != os.path.abspath(str(config.LOGS_DIR)), \
        "conftest phải trỏ LOG_DIR ra thư mục tạm — không thì `boom` của test lẫn vào logs/app.log"


# ── giờ theo múi giờ Việt Nam, không theo đồng hồ tiến trình ────────────────


def test_gio_quet_theo_mui_gio_VN_du_tien_trinh_chay_UTC(nguon, monkeypatch):
    """
    Ảnh Owner 13:53 ghi "Quét lúc 06:24" — laptop chạy bot theo UTC, lượt quét thật là 13:24.
    Owner tưởng lỗi cũ từ sáng, thực ra vừa quét xong với code mới.
    """
    import time as _time

    monkeypatch.setenv("TZ", "UTC")
    if hasattr(_time, "tzset"):
        _time.tzset()
    # 2026-09-11 06:24:00 UTC == 13:24 giờ Việt Nam
    ts = 1757571840

    text = nguon(last_scanned_at=ts, last_found=1)

    assert "11/09 13:24" in text, text


# ── tin lỗi tự khai bản yt-dlp ──────────────────────────────────────────────


def _status(**over):
    base = {"installed": "2026.08.19", "pinned": "2026.08.19", "outdated": False, "mismatch": False, "package": "2026.08.19"}
    base.update(over)
    return base


def test_yt_dlp_cu_thi_tin_loi_noi_thang_kem_lenh_cap_nhat(monkeypatch):
    from app.core.observability import health

    monkeypatch.setattr(health, "_ytdlp_version_status", lambda: _status(installed="2025.03.31", outdated=True))

    msg = humanize_scan_error("tiktok", OWNER_STDERR)

    assert "2025.03.31" in msg and "CŨ" in msg and "pip install" in msg


def test_yt_dlp_dung_ban_thi_ket_luan_bi_chan_tam(monkeypatch):
    from app.core.observability import health

    monkeypatch.setattr(health, "_ytdlp_version_status", lambda: _status())

    msg = humanize_scan_error("tiktok", OWNER_STDERR)

    assert "đúng bản ghim" in msg and "chặn tạm" in msg


def test_co_ban_la_chen_vao_PATH_thi_noi(monkeypatch):
    from app.core.observability import health

    monkeypatch.setattr(health, "_ytdlp_version_status", lambda: _status(installed="2024.01.01", package="2026.08.19", mismatch=True, outdated=True))

    assert "CŨ" in humanize_scan_error("tiktok", OWNER_STDERR), "cũ thắng: lệnh sửa cụ thể hơn"


def test_do_phien_ban_hong_thi_tin_loi_van_co(monkeypatch):
    from app.core.observability import health

    def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(health, "_ytdlp_version_status", boom)

    msg = humanize_scan_error("tiktok", OWNER_STDERR)

    assert "không phải dữ liệu" in msg and "Sức khỏe" in msg
