"""
ADR-019 — bảng "Nguồn" tách khỏi account: detect kênh, CRUD, quét bằng yt-dlp flat-playlist
(mock subprocess), dedup, lỗi không raise, scan_all only_due, và sweep gom NEW không account
→ READY (ADR-018). SQLite tạm như tests/test_viral_router_background.py; không mạng, không ffmpeg.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config
from app.constants import ViralStatus
from app.core.database.models import Account, Job, RuntimeSetting, ViralMaterial, ViralSource
from app.features.viral_intake import processor, reup_processor, reup_variants, sources
from app.features.viral_intake.reup_processor import ReupResult
from app.features.viral_intake.service import ViralService
from app.features.viral_intake.sources import MSG_FB_IG, MSG_VIDEO_LINK, SourceService


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'viral_sources.sqlite'}")
    for model in (Account, ViralMaterial, ViralSource, Job, RuntimeSetting):
        model.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _no_sleep_no_ratelimit(monkeypatch, tmp_path):
    monkeypatch.setattr(sources.time, "sleep", lambda *_: None)
    monkeypatch.setattr(sources, "_load_rate_limits", lambda: {})
    monkeypatch.setattr(sources, "_save_rate_limits", lambda tracker: None)


# ---------------------------------------------------------------------------
# detect_channel
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.tiktok.com/@mrwork93?lang=vi", ("tiktok", "https://www.tiktok.com/@mrwork93", "mrwork93")),
        ("tiktok.com/@abc.def", ("tiktok", "https://www.tiktok.com/@abc.def", "abc.def")),
        ("https://www.youtube.com/@albert_cancook", ("youtube", "https://www.youtube.com/@albert_cancook/shorts", "albert_cancook")),
        ("https://youtube.com/@albert_cancook/shorts?si=x", ("youtube", "https://www.youtube.com/@albert_cancook/shorts", "albert_cancook")),
        ("https://www.youtube.com/channel/UCabc123/videos", ("youtube", "https://www.youtube.com/channel/UCabc123/shorts", "UCabc123")),
        ("https://www.youtube.com/c/SomeName", ("youtube", "https://www.youtube.com/c/SomeName/shorts", "SomeName")),
        ("https://www.youtube.com/user/OldName", ("youtube", "https://www.youtube.com/user/OldName/shorts", "OldName")),
        ("https://www.tiktok.com/@abc/video/123", None),
        ("https://www.youtube.com/shorts/xyz", None),
        ("https://www.youtube.com/watch?v=xyz", None),
        ("https://youtu.be/xyz", None),
        ("https://vt.tiktok.com/ZSabc/", None),
        ("https://www.facebook.com/somepage/reels/", None),
        ("https://www.instagram.com/handle/", None),
        ("https://example.com/x", None),
        ("", None),
    ],
)
def test_detect_channel_table(url, expected):
    assert SourceService.detect_channel(url) == expected


def test_reject_reason_distinguishes_video_vs_fb_ig():
    assert SourceService.reject_reason("https://www.tiktok.com/@abc/video/123") == MSG_VIDEO_LINK
    assert SourceService.reject_reason("https://www.youtube.com/shorts/xyz") == MSG_VIDEO_LINK
    assert SourceService.reject_reason("https://www.facebook.com/p/reels/") == MSG_FB_IG
    assert SourceService.reject_reason("https://www.instagram.com/x/") == MSG_FB_IG
    assert SourceService.reject_reason("https://www.tiktok.com/@ok") == ""


# ---------------------------------------------------------------------------
# add_source / CRUD
# ---------------------------------------------------------------------------
def test_add_source_rejects_fb_ig_video_and_duplicate(session_factory):
    with session_factory() as db:
        ok, msg, sid = SourceService.add_source(db, "https://www.facebook.com/page/reels/")
        assert (ok, sid) == (False, None) and "từng link video" in msg
        ok, msg, sid = SourceService.add_source(db, "https://www.instagram.com/handle/")
        assert (ok, sid) == (False, None) and "từng link video" in msg
        ok, msg, sid = SourceService.add_source(db, "https://www.tiktok.com/@abc/video/1")
        assert (ok, sid) == (False, None) and "link video" in msg
        ok, msg, sid = SourceService.add_source(db, "https://www.youtube.com/watch?v=abc")
        assert (ok, sid) == (False, None) and "link video" in msg

        ok, msg, sid = SourceService.add_source(db, "https://youtube.com/@albert_cancook", min_views=1_000_000, max_videos=5, target_page="https://facebook.com/p1")
        assert ok and sid
        src = db.get(ViralSource, sid)
        assert (src.platform, src.url, src.handle) == ("youtube", "https://www.youtube.com/@albert_cancook/shorts", "albert_cancook")
        assert (src.min_views, src.max_videos, src.target_page, src.enabled) == (1_000_000, 5, "https://facebook.com/p1", True)
        assert src.last_scanned_at is None and src.last_found == 0 and src.last_error is None

        # Trùng (biến thể URL khác nhau → cùng canonical) → từ chối, trả id cũ
        ok2, msg2, sid2 = SourceService.add_source(db, "https://www.youtube.com/@albert_cancook/shorts")
        assert not ok2 and sid2 == sid and "đã có" in msg2
        assert len(SourceService.list_sources(db)) == 1

        assert SourceService.set_enabled(db, sid, False) is True
        assert db.get(ViralSource, sid).enabled is False
        assert SourceService.set_enabled(db, 9999, True) is False
        assert SourceService.delete_source(db, sid) is True
        assert SourceService.delete_source(db, sid) is False
        assert SourceService.list_sources(db) == []


# ---------------------------------------------------------------------------
# scan_source
# ---------------------------------------------------------------------------
def _yt_lines(platform: str) -> str:
    if platform == "tiktok":
        rows = [
            # uploader = @handle chữ, uploader_id = id số (thật của yt-dlp) — URL phải dùng handle chữ
            {"id": "7001", "uploader": "mrwork93", "uploader_id": "7628871700940555277", "title": "Big one", "view_count": 5_000_000, "url": "https://www.tiktok.com/@mrwork93/video/7001"},
            {"id": "7002", "uploader_id": "7628871700940555277", "title": "Mid", "view_count": 1_500_000},  # thiếu uploader → source.handle
            {"id": "7003", "uploader": "mrwork93", "title": "Small", "view_count": 999},
        ]
    else:
        rows = [
            {"id": "aaa111", "title": "Steak", "view_count": 8_000_000, "url": "https://www.youtube.com/shorts/aaa111"},
            {"id": "bbb222", "title": "Eggs", "view_count": None},  # view_count None → coi 0 → thiếu views
            {"id": "ccc333", "title": "Bread", "view_count": 2_500_000},
        ]
    return "\n".join(json.dumps(r) for r in rows) + "\n"


@pytest.fixture
def fake_yt_dlp(monkeypatch):
    state = {"calls": [], "stdout_for": {}, "fail": None}

    def fake_run(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd]
        state["calls"].append(argv)
        if state["fail"]:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr=state["fail"])
        url = argv[-1]
        platform = "tiktok" if "tiktok.com" in url else "youtube"
        return subprocess.CompletedProcess(argv, 0, stdout=state["stdout_for"].get(url, _yt_lines(platform)), stderr="")

    monkeypatch.setattr(sources.subprocess, "run", fake_run)
    return state


def test_scan_source_tiktok_creates_new_materials_and_dedups(session_factory, fake_yt_dlp):
    with session_factory() as db:
        _, _, sid = SourceService.add_source(db, "https://www.tiktok.com/@mrwork93", min_views=1_000_000, max_videos=5, target_page="pageX")
        src = db.get(ViralSource, sid)
        found, skipped, error = SourceService.scan_source(db, src)
        assert (found, skipped, error) == (2, 1, None)

        argv = fake_yt_dlp["calls"][-1]
        assert "--flat-playlist" in argv and "--dump-json" in argv and "--no-warnings" in argv
        assert argv[argv.index("--playlist-end") + 1] == "5"
        assert argv[-1] == "https://www.tiktok.com/@mrwork93"

        mats = db.query(ViralMaterial).order_by(ViralMaterial.views.desc()).all()
        assert [m.url for m in mats] == [
            "https://www.tiktok.com/@mrwork93/video/7001",
            "https://www.tiktok.com/@mrwork93/video/7002",
        ]
        for m in mats:
            assert m.status == ViralStatus.NEW
            assert m.platform == "tiktok"
            assert m.scraped_by_account_id is None
            assert m.target_page == "pageX"
        assert [m.views for m in mats] == [5_000_000, 1_500_000]
        assert mats[0].title == "Big one"

        db.refresh(src)
        assert src.last_found == 2 and src.last_error is None and src.last_scanned_at

        # Quét lại → 0 mới (dedup), skipped = 2 trùng + 1 thiếu views
        found2, skipped2, error2 = SourceService.scan_source(db, src)
        assert (found2, skipped2, error2) == (0, 3, None)
        assert db.query(ViralMaterial).count() == 2
        assert db.get(ViralSource, sid).last_found == 0


def test_scan_source_youtube_url_normalized_and_www_variant_dedup(session_factory, fake_yt_dlp):
    with session_factory() as db:
        # Material cũ lưu biến thể www. → phải được coi là trùng
        db.add(ViralMaterial(platform="youtube", url="https://www.youtube.com/shorts/ccc333", title="", views=0, status=ViralStatus.READY))
        db.commit()
        _, _, sid = SourceService.add_source(db, "https://www.youtube.com/@albert_cancook", min_views=1_000_000)
        src = db.get(ViralSource, sid)
        found, skipped, error = SourceService.scan_source(db, src)
        assert (found, skipped, error) == (1, 2, None)
        new = db.query(ViralMaterial).filter(ViralMaterial.status == ViralStatus.NEW).one()
        assert new.url == "https://youtube.com/shorts/aaa111"
        assert (new.platform, new.views, new.title, new.scraped_by_account_id) == ("youtube", 8_000_000, "Steak", None)


def test_scan_source_uses_setting_min_views_when_source_null(session_factory, fake_yt_dlp, monkeypatch):
    monkeypatch.setattr(sources, "_setting_int", lambda db, key, fallback: {"viral.min_views": 2_000_000, "viral.max_videos_per_channel": 7}.get(key, fallback))
    with session_factory() as db:
        _, _, sid = SourceService.add_source(db, "https://www.tiktok.com/@mrwork93")
        found, skipped, error = SourceService.scan_source(db, db.get(ViralSource, sid))
        assert (found, skipped, error) == (1, 2, None)
        argv = fake_yt_dlp["calls"][-1]
        assert argv[argv.index("--playlist-end") + 1] == "7"


def test_scan_source_yt_dlp_error_sets_last_error_without_raise(session_factory, fake_yt_dlp):
    fake_yt_dlp["fail"] = "WARNING: x\nERROR: [TikTok] Unable to extract: " + "y" * 400
    with session_factory() as db:
        _, _, sid = SourceService.add_source(db, "https://www.tiktok.com/@mrwork93", min_views=1)
        src = db.get(ViralSource, sid)
        found, skipped, error = SourceService.scan_source(db, src)
        assert (found, skipped) == (0, 0)
        assert error and error.startswith("ERROR: [TikTok]")
        db.refresh(src)
        assert src.last_error.startswith("ERROR: [TikTok]") and len(src.last_error) <= 200
        assert src.last_scanned_at and src.last_found == 0
        assert db.query(ViralMaterial).count() == 0


def test_scan_source_timeout_is_swallowed(session_factory, monkeypatch):
    def boom(cmd, *a, **k):
        raise subprocess.TimeoutExpired(cmd, 90)

    monkeypatch.setattr(sources.subprocess, "run", boom)
    with session_factory() as db:
        _, _, sid = SourceService.add_source(db, "https://www.tiktok.com/@mrwork93", min_views=1)
        found, skipped, error = SourceService.scan_source(db, db.get(ViralSource, sid))
        assert (found, skipped) == (0, 0) and "timeout" in error
        assert "timeout" in db.get(ViralSource, sid).last_error


# ---------------------------------------------------------------------------
# scan_all
# ---------------------------------------------------------------------------
def test_scan_all_only_due_skips_recently_scanned_and_disabled(session_factory, fake_yt_dlp, monkeypatch):
    monkeypatch.setattr(sources, "_setting_int", lambda db, key, fallback: 60 if key == "viral.source_scan_interval_min" else fallback)
    with session_factory() as db:
        _, _, s_tt = SourceService.add_source(db, "https://www.tiktok.com/@mrwork93", min_views=1_000_000)
        _, _, s_yt = SourceService.add_source(db, "https://www.youtube.com/@albert_cancook", min_views=1_000_000)
        _, _, s_off = SourceService.add_source(db, "https://www.tiktok.com/@disabled", min_views=1)
        SourceService.set_enabled(db, s_off, False)

        first = SourceService.scan_all(db, only_due=True)
        assert first["scanned"] == 2 and first["found"] == 4 and first["errors"] == 0
        assert len(fake_yt_dlp["calls"]) == 2

        # Vừa quét xong → only_due bỏ qua cả 2
        second = SourceService.scan_all(db, only_due=True)
        assert second == {"found": 0, "scanned": 0, "errors": 0, "skipped": 0}
        assert len(fake_yt_dlp["calls"]) == 2

        # only_due=False → quét lại, dedup → 0 mới
        third = SourceService.scan_all(db, only_due=False)
        assert third["scanned"] == 2 and third["found"] == 0
        assert len(fake_yt_dlp["calls"]) == 4

        # Quá hạn → đến lượt
        src = db.get(ViralSource, s_tt)
        src.last_scanned_at = src.last_scanned_at - 61 * 60
        db.commit()
        fourth = SourceService.scan_all(db, only_due=True)
        assert fourth["scanned"] == 1
        assert fake_yt_dlp["calls"][-1][-1] == "https://www.tiktok.com/@mrwork93"


def test_scan_all_counts_errors(session_factory, fake_yt_dlp):
    fake_yt_dlp["fail"] = "ERROR: boom"
    with session_factory() as db:
        SourceService.add_source(db, "https://www.tiktok.com/@a", min_views=1)
        SourceService.add_source(db, "https://www.tiktok.com/@b", min_views=1)
        out = SourceService.scan_all(db, only_due=False)
        assert out["scanned"] == 2 and out["errors"] == 2 and out["found"] == 0


# ---------------------------------------------------------------------------
# sweep: NEW không account → READY (ADR-018 + ADR-019 mục 4)
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_pipeline(tmp_path, monkeypatch):
    """yt-dlp + ReupProcessor giả như tests/test_viral_ready_without_account.py."""
    monkeypatch.setattr(config, "REUP_DIR", tmp_path / "reup")
    monkeypatch.setattr(processor, "_get_runtime_int", lambda db, key, fallback: fallback)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    monkeypatch.setattr(ViralService, "ensure_reup_thumbnail", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(reup_variants, "record_reup_variant", lambda **k: None)
    calls = {"preflight": 0, "download": 0, "reup": 0}

    def fake_run(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd]
        if "--dump-single-json" in argv:
            calls["preflight"] += 1
            info = {"title": "demo", "view_count": 1234, "formats": [{"vcodec": "vp9", "ext": "webm"}]}
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(info), stderr="")
        if "-o" not in argv:
            # ADR-024: pipeline con goi ffprobe/ffmpeg lay pHash - khong phai lenh tai.
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
        calls["download"] += 1
        out = argv[argv.index("-o") + 1].replace("%(id)s", "src").replace("%(ext)s", "webm")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            # ADR-024 so trung theo sha256: moi material phai ra noi dung KHAC nhau,
            # neu khong material thu hai bi coi la trung (dung y ADR, hong y test nay).
            fh.write(out.encode("utf-8").ljust(2048, b"\x00"))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(processor.subprocess, "run", fake_run)

    def fake_reup(input_path, platform="unknown", **kwargs):
        calls["reup"] += 1
        out = os.path.splitext(input_path)[0] + "_reup.mp4"
        with open(out, "wb") as fh:
            fh.write(b"\x01" * 4096)
        return ReupResult(success=True, output_path=out, metrics={})

    monkeypatch.setattr(reup_processor.ReupProcessor, "process", staticmethod(fake_reup))
    return calls


def test_sweep_picks_orphan_new_without_any_active_account(session_factory, fake_pipeline):
    # (Không dùng fake_yt_dlp ở đây: sources.subprocess và processor.subprocess là cùng module,
    # hai mock sẽ đè nhau — seed material đúng dạng scan_source tạo ra.)
    with session_factory() as db:
        # Không có account nào (active_accounts rỗng) — vẫn phải gom material của nguồn
        for vid, views in (("aaa111", 8_000_000), ("ccc333", 2_500_000)):
            db.add(ViralMaterial(platform="youtube", url=f"https://youtube.com/shorts/{vid}", title="", views=views, status=ViralStatus.NEW, scraped_by_account_id=None))
        db.commit()
        ids = [m.id for m in db.query(ViralMaterial).filter(ViralMaterial.status == ViralStatus.NEW).all()]
        assert len(ids) == 2

    with session_factory() as db:
        processor.ViralProcessorService().process_all(db)

    with session_factory() as db:
        for mid in ids:
            mat = db.get(ViralMaterial, mid)
            assert mat.status == ViralStatus.READY, (mat.status, mat.last_error)
            assert mat.scraped_by_account_id is None
        assert db.query(Job).count() == 0
    assert fake_pipeline == {"preflight": 2, "download": 2, "reup": 2}


def test_sweep_orphan_new_also_gathered_alongside_account_materials(session_factory, fake_pipeline):
    """Có account active (không phải facebook ACTIVE) → NEW của account + NEW mồ côi đều được gom."""
    with session_factory() as db:
        acc = Account(name="tt", platform="tiktok", is_active=True, login_status="ACTIVE")
        db.add(acc)
        db.commit()
        db.add(ViralMaterial(platform="tiktok", url="https://www.tiktok.com/@x/video/1", title="", views=10, status=ViralStatus.NEW, scraped_by_account_id=acc.id))
        db.add(ViralMaterial(platform="tiktok", url="https://www.tiktok.com/@y/video/2", title="", views=20, status=ViralStatus.NEW, scraped_by_account_id=None))
        db.commit()
    with session_factory() as db:
        processor.ViralProcessorService().process_all(db)
    with session_factory() as db:
        statuses = {m.url: m.status for m in db.query(ViralMaterial).all()}
        # Mồ côi → READY (không account); của account đi đường cũ (không còn NEW)
        assert statuses["https://www.tiktok.com/@y/video/2"] == ViralStatus.READY
        assert statuses["https://www.tiktok.com/@x/video/1"] != ViralStatus.NEW
    assert fake_pipeline["download"] == 2


# ---------------------------------------------------------------------------
# ADR-026 — update_source: sửa tại chỗ Min views / Max video / Page đích
# ---------------------------------------------------------------------------


def _seeded_source(db, **over):
    """Nguồn đã quét vài lần — để kiểm update KHÔNG làm mất lịch sử quét."""
    base = dict(
        platform="tiktok", url="https://www.tiktok.com/@shop", handle="shop",
        min_views=1000, max_videos=3, enabled=True,
        last_scanned_at=1_700_000_000, last_found=7, last_error=None,
    )
    base.update(over)
    src = ViralSource(**base)
    src.target_pages_list = ["https://facebook.com/p1"]
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


def test_update_source_changes_numbers_and_keeps_scan_history(session_factory):
    """Đúng ca của Owner: max 3 → 50 mà không mất 'Quét cuối' / 'Tìm thấy'."""
    with session_factory() as db:
        sid = _seeded_source(db).id
        ok, msg = SourceService.update_source(db, sid, min_views=5000, max_videos=50, target_pages=["https://facebook.com/p1"])
        assert ok, msg
        src = db.get(ViralSource, sid)
        assert (src.min_views, src.max_videos) == (5000, 50)
        assert (src.last_scanned_at, src.last_found) == (1_700_000_000, 7)
        assert (src.url, src.handle, src.platform) == ("https://www.tiktok.com/@shop", "shop", "tiktok")


def test_update_source_empty_means_back_to_default_not_keep_old(session_factory):
    """Ô để trống ⇒ NULL ⇒ dùng setting chung. Đây là chỗ dễ hiểu ngược nhất (ADR-026 mục 2)."""
    with session_factory() as db:
        sid = _seeded_source(db).id
        ok, _ = SourceService.update_source(db, sid, min_views="", max_videos="", target_pages=[])
        assert ok
        src = db.get(ViralSource, sid)
        assert src.min_views is None and src.max_videos is None


def test_update_source_clearing_pages_also_clears_legacy_column(session_factory):
    """Xoá hết Page phải sạch cả `target_page` cũ, không để lại nguồn sự thật thứ hai."""
    with session_factory() as db:
        sid = _seeded_source(db).id
        assert db.get(ViralSource, sid).target_page == "https://facebook.com/p1"
        ok, _ = SourceService.update_source(db, sid, target_pages=[])
        assert ok
        src = db.get(ViralSource, sid)
        assert src.target_pages is None and src.target_page is None
        assert src.target_pages_list == []


def test_update_source_rewrites_page_list_in_order(session_factory):
    with session_factory() as db:
        sid = _seeded_source(db).id
        ok, msg = SourceService.update_source(db, sid, target_pages=["https://facebook.com/b", "https://facebook.com/a"])
        assert ok and "2 Page đích" in msg
        assert db.get(ViralSource, sid).target_pages_list == ["https://facebook.com/b", "https://facebook.com/a"]


@pytest.mark.parametrize("field,value,needle", [
    ("max_videos", 0, "1–500"),
    ("max_videos", 501, "1–500"),
    ("max_videos", "abc", "số nguyên"),
    ("min_views", -1, "không được âm"),
    ("min_views", "x", "số nguyên"),
])
def test_update_source_rejects_bad_values_without_touching_db(session_factory, field, value, needle):
    with session_factory() as db:
        sid = _seeded_source(db).id
        ok, msg = SourceService.update_source(db, sid, **{field: value})
        assert not ok and needle in msg
        src = db.get(ViralSource, sid)
        # Không ghi gì: cả hai số lẫn Page đều y nguyên
        assert (src.min_views, src.max_videos) == (1000, 3)
        assert src.target_pages_list == ["https://facebook.com/p1"]


def test_update_source_unknown_id_is_false_not_raise(session_factory):
    with session_factory() as db:
        ok, msg = SourceService.update_source(db, 9999, max_videos=10)
        assert not ok and "9999" in msg
