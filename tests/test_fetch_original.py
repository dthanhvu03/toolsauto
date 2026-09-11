"""
ADR-043 — `/tai <link>`: tải bản gốc về máy, không đi qua luồng reup.

Chạy nguyên `fetch_original` với yt-dlp giả (ghi file thật vào đĩa tạm) — khoá đúng những
ranh giới ADR đặt ra: không material, không cookie ở lượt đầu, thử lại có cookie khi Facebook
đòi đăng nhập, ≤ 50 MB mới `sendable`, link kênh bị chặn trước khi gọi yt-dlp.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config
from app.core.database.models import Account, ViralMaterial
from app.core.storage import offsite
from app.features.viral_intake import fetch as fmod
from app.features.viral_intake.fetch import fetch_original, humanize_fetch_error

VIDEO = "https://www.tiktok.com/@thacaukechuyen/video/7679052117176372487"
FB = "https://www.facebook.com/reel/123"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'f.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def disks(tmp_path, monkeypatch):
    media = tmp_path / "media"
    monkeypatch.setattr(config, "STORAGE_MEDIA_DIR", media)
    monkeypatch.setattr(config, "DOWNLOADS_DIR", media / "tai-ve")
    monkeypatch.setattr(config, "REUP_DIR", media / "reup")
    monkeypatch.setattr(offsite, "get_root", lambda: None)
    return media


@pytest.fixture
def fake_ytdlp(monkeypatch):
    """yt-dlp giả: ghi lại từng lệnh; `state` điều khiển probe/download thành hay bại."""
    state = {"probe_fail": None, "probe_fail_without_cookies": None, "size": 1024, "title": "Muốn giàu phải ra biển", "calls": []}

    def run(cmd, *a, **k):
        argv = [str(c) for c in cmd]
        state["calls"].append(argv)
        has_cookies = "--cookies-from-browser" in argv
        if "--dump-single-json" in argv:
            if state["probe_fail"] or (state["probe_fail_without_cookies"] and not has_cookies):
                return subprocess.CompletedProcess(argv, 1, "", state["probe_fail"] or state["probe_fail_without_cookies"])
            return subprocess.CompletedProcess(argv, 0, json.dumps({"id": "7679", "title": state["title"]}), "")
        out = argv[argv.index("-o") + 1].replace("%(ext)s", "mp4")
        with open(out, "wb") as fh:
            fh.write(b"\x00" * state["size"])
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(fmod.subprocess, "run", run)
    return state


def test_tai_ve_dung_thu_muc_dung_ten_khong_tao_material(db, disks, fake_ytdlp):
    res = fetch_original(db, VIDEO)

    assert res["ok"], res
    assert res["path"].endswith("Muốn giàu phải ra biển.mp4")
    assert f"tai-ve/{time.strftime('%Y-%m')}/" in res["path"].replace("\\", "/")
    assert res["sendable"] is True
    assert db.query(ViralMaterial).count() == 0, "không được lọt vào luồng viral"
    assert not (disks / "reup").exists(), "không được đụng REUP_DIR"


def test_lenh_yt_dlp_chi_mot_video_va_co_tran_dung_luong(db, disks, fake_ytdlp):
    fetch_original(db, VIDEO)

    dl = fake_ytdlp["calls"][-1]
    assert "--no-playlist" in dl and "--max-filesize" in dl and "500M" in dl


def test_qua_50MB_thi_khong_sendable_nhung_van_ok(db, disks, fake_ytdlp):
    fake_ytdlp["size"] = 51 * 1024 * 1024

    res = fetch_original(db, VIDEO)

    assert res["ok"] and res["sendable"] is False and res["size_mb"] >= 51


def test_luot_dau_KHONG_dung_cookie(db, disks, fake_ytdlp):
    db.add(Account(name="fb", platform="facebook", is_active=True, login_status="ACTIVE", profile_path="/p"))
    db.commit()

    fetch_original(db, FB)

    assert all("--cookies-from-browser" not in c for c in fake_ytdlp["calls"]), "video công khai không cần cookie; Chrome mở profile là cookie hỏng"


def test_facebook_doi_dang_nhap_thi_thu_lai_bang_cookie_tai_khoan(db, disks, fake_ytdlp):
    db.add(Account(name="fb", platform="facebook", is_active=True, login_status="ACTIVE", profile_path="/p"))
    db.commit()
    fake_ytdlp["probe_fail_without_cookies"] = "ERROR: [facebook] 123: You must log in to continue"

    res = fetch_original(db, FB)

    assert res["ok"], res
    probes = [c for c in fake_ytdlp["calls"] if "--dump-single-json" in c]
    assert len(probes) == 2 and "chromium:/p" in probes[1]


def test_facebook_doi_dang_nhap_ma_khong_co_tai_khoan_thi_noi_ro(db, disks, fake_ytdlp):
    fake_ytdlp["probe_fail_without_cookies"] = "ERROR: [facebook] 123: You must log in to continue"

    res = fetch_original(db, FB)

    assert not res["ok"] and "đăng nhập" in res["msg"] and "ACTIVE" in res["msg"]


def test_co_cookie_van_bi_tu_choi_thi_noi_ca_ly_do_Chrome(db, disks, fake_ytdlp):
    db.add(Account(name="fb", platform="facebook", is_active=True, login_status="ACTIVE", profile_path="/p"))
    db.commit()
    fake_ytdlp["probe_fail"] = "ERROR: [facebook] 123: This video is private"

    res = fetch_original(db, FB)

    assert not res["ok"] and "Chrome" in res["msg"]


@pytest.mark.parametrize("url", [
    "https://www.tiktok.com/@thacaukechuyen",
    "https://www.youtube.com/@abc",
    "https://www.facebook.com/somepage",
])
def test_link_kenh_bi_chan_TRUOC_khi_goi_yt_dlp(db, disks, fake_ytdlp, url):
    res = fetch_original(db, url)

    assert not res["ok"] and "MỘT video" in res["msg"]
    assert not fake_ytdlp["calls"], "chặn sớm — yt-dlp với --no-playlist vẫn cố lấy video đầu rồi hỏng thô"


@pytest.mark.parametrize("url", ["https://vt.tiktok.com/ZS8Kx/", "https://vimeo.com/123", "https://youtu.be/abc"])
def test_link_rut_gon_va_trang_la_van_duoc_thu(db, disks, fake_ytdlp, url):
    assert fetch_original(db, url)["ok"]


def test_khong_phai_link_thi_tu_choi(db, disks, fake_ytdlp):
    assert not fetch_original(db, "abc")["ok"]


def test_chep_Drive_khi_bat(db, disks, fake_ytdlp, tmp_path, monkeypatch):
    drive = tmp_path / "drive"
    drive.mkdir()  # `check_root` đòi thư mục Drive phải tồn tại (ổ đã gắn)
    monkeypatch.setattr(offsite, "get_root", lambda: drive)

    res = fetch_original(db, VIDEO)

    assert res["drive_path"] and res["drive_path"].startswith("videos/Tải về/")
    assert (drive / res["drive_path"]).is_file()


def test_trung_ten_thi_khong_ghi_de(db, disks, fake_ytdlp):
    a = fetch_original(db, VIDEO)
    b = fetch_original(db, VIDEO)

    assert a["path"] != b["path"] and "[7679]" in b["path"]


@pytest.mark.parametrize("stderr,needle", [
    ("ERROR: [TikTok] 1: Unexpected response from webpage request", "yt-dlp"),
    ("ERROR: Unsupported URL: https://x", "không hỗ trợ"),
    ("ERROR: [youtube] abc: Video unavailable. This video has been removed", "gỡ"),
    ("File is larger than max-filesize", "500M"),
])
def test_dich_loi(stderr, needle):
    assert needle in humanize_fetch_error("tiktok", stderr, had_cookies=False)


# ── /tai trên Telegram ──────────────────────────────────────────────────────


class _Client:
    def __init__(self):
        self.msgs, self.videos = [], []

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)

    def send_video(self, path, caption="", **kw):
        self.videos.append((path, caption))


def _wait():
    for _ in range(60):
        if not [t for t in threading.enumerate() if t.name == "tg-tai"]:
            return
        time.sleep(0.05)


@pytest.fixture
def tai(monkeypatch):
    import app.core.database.core as dbcore
    from app.core import feature_hooks
    from app.features.telegram_bot.command_handler import TelegramCommandHandler

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(dbcore, "SessionLocal", lambda: _S())
    state = {"res": {}, "seen": []}

    def call(name, *a, **k):
        state["seen"].append((name, a[1:]))
        return state["res"]

    monkeypatch.setattr(feature_hooks, "call", call)
    client = _Client()
    handler = TelegramCommandHandler(client)

    def run(args, res):
        state["res"] = res
        handler.handle_command("tai", args)
        _wait()
        return client, state["seen"]

    return run


def test_tai_khong_link_thi_chi_cu_phap(tai):
    client, seen = tai([], {})

    assert "Cú pháp" in client.msgs[0] and not seen


def test_tai_nho_thi_gui_file(tai):
    client, seen = tai(["https://t/1"], {"ok": True, "msg": "📥 Đã tải", "path": "/x/a.mp4", "sendable": True})

    assert seen == [("viral.fetch_original", ("https://t/1",))]
    assert client.videos and client.videos[0][0] == "/x/a.mp4"


def test_tai_to_thi_KHONG_gui_file_chi_bao_duong_dan(tai):
    client, _ = tai(["https://t/1"], {"ok": True, "msg": "📥 Đã tải · 148.5 MB", "path": "/x/a.mp4", "sendable": False})

    assert not client.videos
    assert "50 MB" in client.msgs[-1] and "148.5" in client.msgs[-1]


def test_tai_hong_thi_bao_ly_do(tai):
    client, _ = tai(["https://t/1"], {"ok": False, "msg": "Facebook đòi đăng nhập"})

    assert "đăng nhập" in client.msgs[-1] and not client.videos


def test_help_nhac_tai():
    from app.features.telegram_bot.command_handler import TelegramCommandHandler

    c = _Client()
    TelegramCommandHandler(c).handle_command("help")

    assert "/tai" in c.msgs[0]
