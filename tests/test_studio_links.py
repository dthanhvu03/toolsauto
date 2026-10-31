"""
PLAN-113 — Studio: đăng tay (không kênh Buffer) + lấy video từ link TikTok (quét → chọn → tải & dựng).
yt-dlp thay bằng lệnh python nhỏ (in JSON / chép clip lavfi) — không gọi mạng. ffmpeg thật, SQLite tạm.
"""
from __future__ import annotations

import json
import sys

import pytest

from app.core.database.models import StudioAsset, StudioProject, StudioTask
from app.features.studio import entry, fetch, pipeline, source
from app.features.studio.contracts import ProjectStatus
from tests.test_studio_api import _project, api  # noqa: F401 — fixture
from tests.test_studio_pipeline import _channel, _drain, db, media  # noqa: F401 — fixture

LINK = "https://www.tiktok.com/@shopmeo/video/7400000000000000001"


def _py(code: str, *args: str) -> list[str]:
    return [sys.executable, "-c", code, *args]


@pytest.fixture
def fake_download(monkeypatch, media):  # noqa: F811
    """yt-dlp giả: chép clip lavfi vào đúng chỗ ``-o``. ``state["fail"]`` = dòng lỗi giả."""
    state = {"fail": None, "calls": 0}

    def cmd(*args):
        state["calls"] += 1
        if state["fail"]:
            return _py("import sys; sys.stderr.write(sys.argv[1]); sys.exit(1)", state["fail"])
        out = args[list(args).index("-o") + 1].replace("%(ext)s", "mp4")
        return _py("import shutil, sys; shutil.copy(sys.argv[1], sys.argv[2])", str(media["clip"]), out)

    monkeypatch.setattr(fetch, "yt_dlp_cmd", cmd)
    return state


# ── quét ─────────────────────────────────────────────────────────────────────


def test_parse_bo_dong_hong_trung_va_lay_anh_cuoi():
    lines = [
        json.dumps({"id": "1", "url": LINK, "title": "Mẹo", "view_count": 1200, "duration": 15.5,
                    "thumbnails": [{"url": "a.jpg"}, {"url": "b.jpg"}]}),
        "không phải json",
        json.dumps({"id": "1", "url": LINK}),  # trùng
        json.dumps({"id": "2"}),  # thiếu link
        json.dumps(["list"]),
        json.dumps({"id": "3", "webpage_url": "https://www.tiktok.com/@shopmeo/video/3", "thumbnail": "t.jpg"}),
    ]
    items = source.parse("\n".join(lines))
    assert [i["id"] for i in items] == ["1", "3"]
    assert items[0] == {"id": "1", "url": LINK, "title": "Mẹo", "views": 1200, "duration": 15.5, "thumbnail": "b.jpg"}
    assert items[1]["thumbnail"] == "t.jpg" and items[1]["views"] is None


def test_scan_chi_nhan_tiktok_gioi_han_so_va_bao_429(monkeypatch):
    seen = {}

    def cmd(*args):
        seen["end"] = args[list(args).index("--playlist-end") + 1]
        rows = "\n".join(json.dumps({"id": str(i), "url": f"https://www.tiktok.com/@a/video/{i}"}) for i in range(40))
        return _py("import sys; print(sys.argv[1])", rows)

    monkeypatch.setattr(source, "yt_dlp_cmd", cmd)
    with pytest.raises(source.SourceError):
        source.scan("https://www.youtube.com/@abc", 5)
    with pytest.raises(source.SourceError):
        source.scan("tiktok.com/@abc", 5)
    assert len(source.scan("https://www.tiktok.com/@abc", 5)) == 5 and seen["end"] == "5"
    assert len(source.scan("https://vt.tiktok.com/ZSabc/", 999)) == 30 and seen["end"] == "30"

    monkeypatch.setattr(source, "yt_dlp_cmd", lambda *a: _py("import sys; sys.stderr.write('HTTP Error 429'); sys.exit(1)"))
    with pytest.raises(source.SourceError, match="429"):
        source.scan("https://www.tiktok.com/@abc", 5)


# ── tải ──────────────────────────────────────────────────────────────────────


def test_fetch_loi_video_rieng_tu_khong_thu_lai_mang_loi_thi_thu_lai(db, fake_download):  # noqa: F811
    from app.features.studio import paths

    fake_download["fail"] = "ERROR: [TikTok] 7400: This video is private"
    pipeline.start(db, "link", payload={"url": LINK})
    _drain(db)
    task = db.query(StudioTask).one()
    assert task.status == "FAILED" and "private" in task.error and task.attempts == 1
    assert not list(paths.inbox_dir().glob("link*"))  # không để rác

    fake_download["fail"] = "ERROR: [TikTok] 7400: Connection reset by peer"
    pipeline.start(db, "link", payload={"url": LINK})
    _drain(db)
    task = db.query(StudioTask).order_by(StudioTask.id.desc()).first()
    assert task.status == "QUEUED" and task.attempts == 1 and "Connection reset" in task.error  # xếp lại, chờ thử lại


# ── lấy từ TikTok → đăng tay ─────────────────────────────────────────────────


def test_lay_link_dang_tay_het_quy_trinh(db, fake_download):  # noqa: F811
    tasks = entry.take_links(
        db, [{"url": LINK, "title": "Mẹo gấp áo"}, {"url": LINK}, {"url": "https://youtube.com/watch?v=1"}],
        techniques={"subtitles": False, "hook": "Xem hết nha", "dub": False},
    )
    assert len(tasks) == 1 and tasks[0].flow == "link" and tasks[0].stage == "fetch"
    assert tasks[0].payload["params"] == {"subtitles": False, "hook": "Xem hết nha"}
    assert entry.taken_urls(db, [LINK, "https://x"]) == {LINK}  # đang chờ tải

    assert _drain(db) == 8  # fetch → intake → analyze → dub → compose → render → caption → review
    project = db.query(StudioProject).one()
    asset = db.get(StudioAsset, project.asset_id)
    assert (asset.origin, asset.credit, asset.source_url, asset.title) == ("reup", "@shopmeo", LINK, "Mẹo gấp áo")
    assert project.channel_id is None and project.status == ProjectStatus.REVIEW  # không kênh → không tự duyệt
    assert project.spec["subtitles"]["enabled"] is False and project.spec["credit"] == "Nguồn: @shopmeo"
    assert all(c["hflip"] is False for c in project.spec["clips"]) and not project.spec["canvas"].get("lut")
    assert entry.taken_urls(db, [LINK]) == {LINK}  # đã vào kho

    entry.approve(db, project.id)
    _drain(db)
    publish = db.query(StudioTask).filter_by(stage="publish").one()
    assert publish.status == "DONE" and publish.error == "đăng tay — không gửi Buffer"  # ghi chú việc xong nằm ở error
    db.refresh(project)
    assert project.status == ProjectStatus.APPROVED
    assert entry.mark_posted(db, project.id).status == ProjectStatus.POSTED
    with pytest.raises(entry.ReviewError):
        entry.mark_posted(db, project.id)  # đã đăng rồi

    entry.take_links(db, [{"url": LINK}])  # lấy lại đúng video đó → intake dừng, không ra dự án thứ hai
    _drain(db)
    assert db.query(StudioProject).count() == 1


def test_take_links_kiem_dau_vao(db):  # noqa: F811
    with pytest.raises(ValueError, match="chưa chọn"):
        entry.take_links(db, [{"url": "https://youtube.com/x"}])
    with pytest.raises(ValueError, match="kênh"):
        entry.take_links(db, [{"url": LINK}], channel_id=999)
    many = [{"url": f"https://www.tiktok.com/@a/video/{i}"} for i in range(source.MAX_SCAN + 1)]
    with pytest.raises(ValueError, match="tối đa"):
        entry.take_links(db, many)
    ch = _channel(db)
    task = entry.take_links(db, [{"url": LINK}], channel_id=ch.id)[0]
    assert task.payload["channel_id"] == ch.id and "params" not in task.payload


def _approved(db, media, *, manual: bool):  # noqa: F811
    p = _project(db, media)
    p.status = ProjectStatus.APPROVED
    if manual:
        p.channel_id = None
    db.commit()
    return p


def test_mark_posted_chan_du_an_co_kenh(db, media):  # noqa: F811
    p = _approved(db, media, manual=False)
    with pytest.raises(entry.ReviewError, match="Buffer"):
        entry.mark_posted(db, p.id)


def test_upload_khong_kenh_la_dang_tay(db, media):  # noqa: F811
    with media["clip"].open("rb") as f:
        task = entry.accept_file(db, f, "tu_quay.mp4")
    assert task.flow == "upload" and task.payload.get("channel_id") is None


# ── API ──────────────────────────────────────────────────────────────────────


def test_api_quet_lay_tai_ve_va_da_dang(api, db, media, monkeypatch):  # noqa: F811
    monkeypatch.setattr(source, "scan", lambda url, limit: [{"id": "1", "url": LINK, "title": "Mẹo", "views": 5,
                                                              "duration": 9, "thumbnail": None}])
    r = api.post("/studio/api/tiktok/scan", json={"url": "https://www.tiktok.com/@shopmeo", "limit": 3})
    assert r.status_code == 200 and r.json()["items"][0]["taken"] is False

    r = api.post("/studio/api/tiktok/take", json={"items": [{"url": LINK, "title": "Mẹo"}], "has_text": True})
    assert r.json()["count"] == 1
    assert api.post("/studio/api/tiktok/scan", json={"url": "https://www.tiktok.com/@shopmeo"}).json()["items"][0]["taken"]
    assert api.post("/studio/api/tiktok/take", json={"items": []}).status_code == 400

    p = _approved(db, media, manual=True)
    r = api.get(f"/studio/api/projects/{p.id}/video?download=1")
    assert r.status_code == 200 and f'filename="studio_{p.id}.mp4"' in r.headers["content-disposition"]
    assert "attachment" in r.headers["content-disposition"]
    assert api.post(f"/studio/api/projects/{p.id}/posted").json() == {"ok": True}
    assert api.post(f"/studio/api/projects/{p.id}/posted").status_code == 400


# ── PLAN-116: ô tick kỹ thuật ───────────────────────────────────────────────


def test_technique_params_nhan_dung_kieu_va_chan_lat_lut_cho_video_suu_tam(db, media, monkeypatch):  # noqa: F811
    from app.features.studio import paths, store

    music, _ = store.add_asset(db, media["music"], kind="audio", origin="brand", has_audio=True)
    raw, _ = store.add_asset(db, media["mute"], kind="audio", origin="brand")  # chưa phân tích: has_audio trống
    clip, _ = store.add_asset(db, media["clip"], kind="video", origin="upload")
    monkeypatch.setattr(paths, "lut_names", lambda: ["am_ap"])
    full = {"subtitles": True, "dub": True, "vieneu_voice": " Thái Sơn ", "hook": " Xem hết ", "music_asset_id": music.id,
            "music_volume": 5, "la": "bị bỏ"}
    assert entry.technique_params(db, full, collected=True) == {
        "subtitles": True, "dub": True, "dub_lang": "vi", "vieneu_voice": "Thái Sơn", "hook": "Xem hết",
        "music_asset_id": music.id, "music_volume": 1.0,
    }
    assert entry.technique_params(db, {"mirror": True, "lut": "am_ap"}, collected=False) == {"mirror": "on", "lut": "am_ap"}
    assert entry.technique_params(db, None, collected=True) == {}
    for bad, why in [({"mirror": True}, "sưu tầm"), ({"lut": "am_ap"}, "sưu tầm"), ({"music_asset_id": clip.id}, "nhạc"),
                     ({"music_asset_id": 999}, "nhạc"), ({"music_asset_id": raw.id}, "chưa phân tích")]:
        with pytest.raises(ValueError, match=why):
            entry.technique_params(db, bad, collected=True)
    with pytest.raises(ValueError, match="tông màu"):
        entry.technique_params(db, {"lut": "khong_co"}, collected=False)


def test_lo_tiktok_tick_long_tieng_mau_basic_van_long(db, fake_download, monkeypatch):  # noqa: F811
    from app.features.studio import analyze, dub
    from tests.test_studio_pipeline import _fake_tracks

    monkeypatch.setattr(analyze.speech, "transcribe", lambda path, **kw: ([{"start": 1, "end": 3, "text": "你好"}], "zh"))
    calls = []
    monkeypatch.setattr(dub.engine, "make_tracks", _fake_tracks(calls))
    entry.take_links(db, [{"url": LINK}], techniques={"subtitles": True, "dub": True})
    _drain(db)
    project = db.query(StudioProject).one()
    assert calls == ["vi"] and project.status == ProjectStatus.REVIEW
    assert len(project.spec["clips"][0]["audio"]) == 2  # giọng lồng + nền đã tách giọng gốc
    assert project.spec["subtitles"] == {**project.spec["subtitles"], "source": "dub", "enabled": True}
    dub_task = db.query(StudioTask).filter_by(stage="dub").one()
    assert dub_task.error == "zh→vi, 1/1 câu"  # không còn «mẫu không lồng tiếng»
