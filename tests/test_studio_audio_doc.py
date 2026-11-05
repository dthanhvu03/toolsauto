"""
PLAN-156 / PLAN-157 / ADR-064 / ADR-065 — Audio → Documentary.

Không gọi mạng thật: nguồn ảnh qua ``httpx.MockTransport``, AI rút từ khóa bị thay, Whisper bị thay. ffmpeg thật.
"""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as app_config
from app.core import settings as runtime_settings
from app.core.database.models import (
    Base,
    RuntimeSetting,
    RuntimeSettingAudit,
    StudioAnalysis,
    StudioAsset,
    StudioProject,
    StudioTask,
)
from app.core.media.ffmpeg_path import ffmpeg_available
from app.features.studio import analyze, entry, paths, pipeline, store, taskqueue
from app.features.studio import doc as doc_stage
from app.features.studio.contracts import Lane, ProjectStatus
from app.features.studio.doc import config as doc_config
from app.features.studio.doc import keywords, rights, seed, service
from app.features.studio.doc.config import DocConfig
from app.features.studio.doc.images import licenses, providers
from app.features.studio.doc.images import search as image_search
from app.features.studio.doc.schema import ImageRef, RightsStatus
from app.features.studio.render.graph import Media, _ken_burns, build
from app.features.studio.spec import Audio, AudioTrack, Canvas, Clip, ProjectSpec

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="cần ffmpeg")

TABLES = [m.__table__ for m in (
    StudioAsset, StudioAnalysis, StudioProject, StudioTask, RuntimeSetting, RuntimeSettingAudit,
)]
FIXTURE_MP3 = Path(app_config.STORAGE_MEDIA_DIR) / "studio" / "fixtures" / "audio_doc_poc_60s.mp3"
FIXTURE_IMG = Path(app_config.STORAGE_MEDIA_DIR) / "studio" / "fixtures" / "placeholder_illustration.png"
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, timeout=120)


def _bust_settings_cache() -> None:
    runtime_settings._cache_ts = 0.0
    runtime_settings._cache_values = {}


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'doc.sqlite'}")
    Base.metadata.create_all(engine, tables=TABLES)
    session = sessionmaker(bind=engine)()
    root = tmp_path / "studio"
    monkeypatch.setattr(paths, "ROOT", root)
    for name in ("assets", "renders", "work", "inbox", "fixtures", "doc"):
        (root / name).mkdir(parents=True)
    if FIXTURE_IMG.is_file():
        (root / "fixtures" / FIXTURE_IMG.name).write_bytes(FIXTURE_IMG.read_bytes())
    else:
        _ff("-f", "lavfi", "-i", "color=c=blue:s=640x360", "-frames:v", "1", str(root / "fixtures" / FIXTURE_IMG.name))
    _ff("-f", "lavfi", "-i", "sine=frequency=220:duration=20", str(root / "fixtures" / "tone20.mp3"))
    # AI thật không bao giờ bị gọi trong test
    monkeypatch.setattr(keywords, "_default_generate", lambda prompt: '{"SHOT-01-01": ["Old Trafford"]}')
    _bust_settings_cache()
    yield session
    session.close()
    _bust_settings_cache()


def _lines(*spans: tuple[float, float, str]) -> list[dict]:
    return [{"start": a, "end": b, "text": t} for a, b, t in spans]


def _doc_project(db) -> tuple[int, StudioTask]:
    """Dự án doc không qua Whisper / render: asset audio 20s + chạy doc_plan."""
    mp3 = paths.ROOT / "fixtures" / "tone20.mp3"
    asset, _ = store.add_asset(db, mp3, kind="audio", origin="upload", move=False, duration=20.0, title="t")
    db.add(StudioAnalysis(asset_id=asset.id, kind="transcript", data={"lang": "vi", "lines": _lines(
        (0.5, 4.0, "Câu một"), (4.2, 9.0, "Câu hai"), (12.0, 18.0, "Câu ba sau khoảng lặng"),
    )}))
    db.commit()
    task = StudioTask(flow="audio_doc", stage="doc_plan", asset_id=asset.id, payload={})
    return doc_stage.run(db, task).project_id, task


def _transport(routes: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, resp in routes.items():
            if str(request.url).startswith(prefix):
                return resp
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


# ── chia cảnh theo audio ──────────────────────────────────────────────────────


def test_shots_follow_transcript_and_cover_whole_audio():
    segs = seed.lines_to_segments(_lines(
        (0.4, 3.0, "Mở đầu"), (3.1, 6.0, "tiếp theo"), (6.1, 9.5, "câu ba"),
        (12.0, 15.0, "sau khoảng lặng"), (15.1, 40.0, "một câu rất dài " * 10),
    ))
    beats, shots = seed.plan(45_000, segs, DocConfig())
    assert shots[0].start_ms == 0 and shots[-1].end_ms == 45_000
    assert all(a.end_ms == b.start_ms for a, b in zip(shots, shots[1:]))  # liền mạch
    assert max(s.end_ms - s.start_ms for s in shots) <= 12_000  # câu dài bị cắt
    assert len(beats) == 2 and beats[1].start_ms == 12_000  # khoảng lặng 2,5s ≥ 1,2s → đoạn ý mới
    assert shots[0].narration.startswith("Mở đầu")
    assert all("Carrick" not in b.summary for b in beats)


def test_shot_thresholds_come_from_config():
    segs = seed.lines_to_segments(_lines(*[(i * 2.0, i * 2.0 + 1.9, f"câu {i}") for i in range(15)]))
    _, short = seed.plan(30_000, segs, DocConfig(shot_sec=4.0))
    _, long = seed.plan(30_000, segs, DocConfig(shot_sec=10.0))
    assert len(short) > len(long)


def test_no_speech_splits_evenly_by_shot_sec():
    beats, shots = seed.plan(20_000, [], DocConfig(shot_sec=5.0))
    assert [s.start_ms for s in shots] == [0, 5_000, 10_000, 15_000]
    assert beats


def test_motions_and_window_from_config():
    assert doc_config.parse_motions("slow_zoom_in, abc ,pan_left") == ("slow_zoom_in", "pan_left")
    assert doc_config.parse_motions("xyz") == ("static",)
    assert doc_config.window_end_ms(DocConfig(preview_sec=0), 90_000) == 90_000
    assert doc_config.window_end_ms(DocConfig(preview_sec=30), 90_000) == 30_000
    assert doc_config.window_end_ms(DocConfig(preview_sec=300), 90_000) == 90_000
    _, shots = seed.plan(30_000, [], DocConfig(shot_sec=10.0, motions=("pan_right",)))
    assert {s.motion for s in shots} == {"pan_right"}


def test_config_load_reads_web_overrides(db):
    assert doc_config.load(db) == DocConfig(keys={"pexels": "", "pixabay": "", "google": "", "google_cx": ""})
    runtime_settings.upsert_setting(db, "doc.canvas", "1080x1920")
    runtime_settings.upsert_setting(db, "doc.preview_sec", "45")
    runtime_settings.upsert_setting(db, "doc.src_pexels", "true")
    runtime_settings.upsert_setting(db, "doc.motions", "static")
    cfg = doc_config.load(db)
    assert (cfg.width, cfg.height, cfg.preview_sec) == (1080, 1920, 45)
    assert "pexels" in cfg.sources and cfg.motions == ("static",)
    assert "pexels_key" not in json.dumps(doc_config.public(cfg))


# ── ngôn ngữ ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("chosen", "expected"), [("en", "en"), ("auto", None), ("", None)])
def test_language_passed_to_whisper(db, monkeypatch, chosen, expected):
    seen = {}

    def fake(path, language=None):
        seen["language"] = language
        return [], language

    monkeypatch.setattr(analyze.speech, "transcribe", fake)
    mp3 = paths.ROOT / "fixtures" / "tone20.mp3"
    asset, _ = store.add_asset(db, mp3, kind="audio", origin="upload", move=False)
    task = StudioTask(flow="audio_doc", stage="analyze", asset_id=asset.id, payload={"language": chosen})
    analyze.run(db, task)
    assert seen["language"] == expected


def test_upload_keeps_language_in_payload(db):
    mp3 = (paths.ROOT / "fixtures" / "tone20.mp3").read_bytes()
    task = entry.accept_audio_doc(db, io.BytesIO(mp3), "a.mp3", language="EN")
    assert task.payload["language"] == "en"
    task2 = entry.accept_audio_doc(db, io.BytesIO(mp3 + b"x"), "b.mp3", language="auto")
    assert "language" not in task2.payload


# ── từ khóa AI ───────────────────────────────────────────────────────────────


def test_keywords_parse_and_suggest():
    _, shots = seed.plan(20_000, seed.lines_to_segments(_lines((0, 5, "Bruno penalty"), (5.1, 12, "Cunha"))), DocConfig())
    reply = "ok:\n" + json.dumps({shots[0].shot_id: ["Bruno Fernandes penalty", "Old Trafford"], "x": 3})
    assert keywords.suggest(shots, "vi", generate=lambda p: reply) == 1
    assert shots[0].keywords == ["Bruno Fernandes penalty", "Old Trafford"]

    def boom(prompt):
        raise RuntimeError("AI down")

    assert keywords.suggest(shots[1:], "vi", generate=boom) == 0
    assert keywords.parse("không phải json") == {}


def test_doc_plan_runs_ai_keywords_and_reuses_project(db):
    pid, task = _doc_project(db)
    state = service.get_state(db, pid)[1]
    assert state.shots[0].keywords == ["Old Trafford"]
    assert len(state.beats) == 2  # khoảng lặng 9 → 12s
    assert doc_stage.run(db, task).project_id == pid
    assert db.query(StudioProject).count() == 1


# ── giấy phép / nguồn ảnh ────────────────────────────────────────────────────


def test_license_rules_follow_config():
    cfg = DocConfig()
    assert licenses.rights_for("CC BY-SA 4.0", cfg) == RightsStatus.RIGHTS_VERIFIED
    assert licenses.rights_for("CC BY-NC 2.0", cfg) == RightsStatus.RESTRICTED
    assert licenses.rights_for("", cfg) == RightsStatus.UNKNOWN
    assert licenses.rights_for("pexels", DocConfig(auto_verify_licenses=("cc0",))) == RightsStatus.UNKNOWN


def test_providers_parse_responses():
    cfg = DocConfig(keys={"pexels": "k", "pixabay": "k", "google": "k", "google_cx": "cx"})
    http = _transport({
        providers.WIKIMEDIA_API: httpx.Response(200, json={"query": {"pages": {"1": {
            "index": 1, "title": "File:Old Trafford.jpg",
            "imageinfo": [{"url": "https://u/w.jpg", "thumburl": "https://u/t.jpg", "width": 2000, "height": 1200,
                           "descriptionurl": "https://c/File:Old", "mime": "image/jpeg", "extmetadata": {
                               "LicenseShortName": {"value": "CC BY-SA 4.0"},
                               "LicenseUrl": {"value": "https://cc/by-sa"},
                               "Artist": {"value": '<a href="x">Ann</a>'}}}]}}}}),
        providers.OPENVERSE_API: httpx.Response(200, json={"results": [{
            "url": "https://u/o.jpg", "thumbnail": "https://u/ot.jpg", "foreign_landing_url": "https://f",
            "creator": "Bob", "license": "by-nc", "license_url": "https://cc/by-nc", "width": 1600, "height": 900}]}),
        providers.PEXELS_API: httpx.Response(200, json={"photos": [{
            "url": "https://p/1", "photographer": "Cat", "width": 4000, "height": 3000,
            "src": {"original": "https://p/o.jpg", "medium": "https://p/m.jpg"}}]}),
        providers.PIXABAY_API: httpx.Response(200, json={"hits": [{
            "pageURL": "https://x/1", "largeImageURL": "https://x/l.jpg", "webformatURL": "https://x/w.jpg",
            "imageWidth": 1920, "imageHeight": 1080, "user": "Dan"}]}),
        providers.GOOGLE_API: httpx.Response(200, json={"items": [{
            "link": "https://g/1.jpg", "title": "g", "image": {"contextLink": "https://g", "width": 1500, "height": 900}}]}),
    })
    w = providers.wikimedia(http, "old trafford", 5, cfg)[0]
    assert (w.license, w.author, w.source_page) == ("cc-by-sa", "Ann", "https://c/File:Old")
    assert providers.openverse(http, "q", 5, cfg)[0].license == "cc-by-nc"
    assert providers.pexels(http, "q", 5, cfg)[0].license == "pexels"
    assert providers.pixabay(http, "q", 5, cfg)[0].author == "Dan"
    assert providers.google(http, "q", 5, cfg)[0].license == "unknown"


def test_search_merges_sources_and_survives_failures():
    cfg = DocConfig(sources=("wikimedia", "openverse", "pexels"), image_min_width=1000)
    http = _transport({
        providers.WIKIMEDIA_API: httpx.Response(500),
        providers.OPENVERSE_API: httpx.Response(200, json={"results": [
            {"url": "https://u/big.jpg", "license": "cc0", "width": 1600},
            {"url": "https://u/small.jpg", "license": "cc0", "width": 300},
        ]}),
    })
    found, notes = image_search.search("q", cfg, http=http)
    assert [c.image_url for c in found] == ["https://u/big.jpg"]
    assert any(n.startswith("wikimedia") for n in notes)
    assert any("Pexels API key" in n for n in notes)
    assert image_search.search("q", DocConfig(sources=()), http=http)[0] == []


# ── tìm + chọn ảnh trong dự án ───────────────────────────────────────────────


def test_search_and_pick_image_fills_rights(db, monkeypatch):
    pid, _ = _doc_project(db)
    shot_id = service.get_state(db, pid)[1].shots[0].shot_id
    http = _transport({
        providers.OPENVERSE_API: httpx.Response(200, json={"results": [
            {"url": "https://img/a.png", "license": "by", "license_url": "https://cc/by", "creator": "Eve",
             "foreign_landing_url": "https://land/a", "width": 2000},
            {"url": "https://img/b.txt", "license": "by", "width": 2000},
            {"url": "https://img/big.png", "license": "by", "width": 2000},
        ]}),
        "https://img/a.png": httpx.Response(200, content=PNG_1x1, headers={"content-type": "image/png"}),
        "https://img/b.txt": httpx.Response(200, content=b"hi", headers={"content-type": "text/html"}),
        "https://img/big.png": httpx.Response(
            200, content=b"0" * (2 * 1024 * 1024), headers={"content-type": "image/png"}),
    })
    runtime_settings.upsert_setting(db, "doc.src_wikimedia", "false")
    runtime_settings.upsert_setting(db, "doc.image_max_mb", "1")
    service.search_images(db, pid, shot_id, ["Old Trafford night"], http=http)
    shot = service.get_state(db, pid)[1].shots[0]
    assert shot.keywords[0] == "Old Trafford night" and len(shot.candidates) == 3

    for bad in (1, 2):  # không phải ảnh / quá lớn
        with pytest.raises(service.DocError):
            service.pick_image(db, pid, shot_id, bad, http=http)
    service.pick_image(db, pid, shot_id, 0, http=http)
    sel = service.get_state(db, pid)[1].shots[0].selected
    assert sel.provider == "openverse" and sel.rights_status == RightsStatus.RIGHTS_VERIFIED
    assert sel.author == "Eve" and "https://land/a" in sel.proof_note
    assert db.get(StudioAsset, sel.asset_id).origin == "web"


# ── quyền / sửa cảnh ─────────────────────────────────────────────────────────


def test_rights_gate_follows_config():
    _, shots = seed.plan(10_000, [], DocConfig(shot_sec=10.0))
    from app.features.studio.doc.schema import DocState

    state = DocState(audio_asset_id=1, duration_ms=10_000, shots=shots)
    shots[0].selected = ImageRef(asset_id=9, rights_status=RightsStatus.RIGHTS_VERIFIED)
    assert not rights.check_export(state, DocConfig(), end_ms=10_000).ok  # thiếu bằng chứng
    assert rights.check_export(state, DocConfig(rights_need_proof=False), end_ms=10_000).ok
    assert not rights.check_export(state, DocConfig(rights_need_proof=False, rights_ok="approved_only"), end_ms=10_000).ok
    shots[0].selected = ImageRef(asset_id=9, rights_status=RightsStatus.UNKNOWN, license="owned")
    assert any("RIGHTS_UNKNOWN" in b for b in rights.check_export(state, DocConfig(), end_ms=10_000).blockers)


def test_bad_shot_patch_rejected_and_state_still_loads(db):
    pid, _ = _doc_project(db)
    shot_id = service.get_state(db, pid)[1].shots[0].shot_id
    for patch in ({"motion": "spin"}, {"start_ms": -5}, {"end_ms": 0}, {"start_ms": "abc"}, {"keywords": 5}):
        with pytest.raises(service.DocError):
            service.update_shot(db, pid, shot_id, patch)
    with pytest.raises(service.DocError):
        service.update_transcript(db, pid, [{"raw_text": "thiếu mốc"}])
    assert service.detail(db, pid)["doc"]["shots"][0]["motion"] != "spin"
    service.update_shot(db, pid, shot_id, {"motion": "pan_left", "keywords": "a, b"})
    shot = service.get_state(db, pid)[1].shots[0]
    assert shot.motion == "pan_left" and shot.keywords == ["a", "b"]


def test_bad_rights_rejected_without_orphan_asset(db):
    pid, _ = _doc_project(db)
    shot_id = service.get_state(db, pid)[1].shots[0].shot_id
    before = db.query(StudioAsset).count()
    img = (paths.ROOT / "fixtures" / FIXTURE_IMG.name).read_bytes()
    with pytest.raises(service.DocError):
        service.attach_image(db, pid, shot_id, io.BytesIO(img), "a.png", rights_status="OK_LUON")
    assert db.query(StudioAsset).count() == before
    service.attach_image(db, pid, shot_id, io.BytesIO(img), "a.png")
    with pytest.raises(service.DocError):
        service.set_shot_rights(db, pid, shot_id, {"rights_status": "OK_LUON"})
    assert service.get_state(db, pid)[1].shots[0].selected.rights_status == RightsStatus.UNKNOWN


# ── spec dựng theo cấu hình ──────────────────────────────────────────────────


def test_preview_spec_uses_config(db):
    pid, _ = _doc_project(db)
    state = service.get_state(db, pid)[1]
    cfg = DocConfig(width=1080, height=1920, fps=25, fit="blur_pad", preview_sec=10, subtitle_font_size=60,
                    subtitle_max_chars=40, voice_volume=0.8, credit="Kênh A", kb_zoom_max=1.3, subtitles=True)
    spec = service.build_preview_spec(db, state, cfg)
    assert (spec.canvas.w, spec.canvas.h, spec.canvas.fps, spec.canvas.fit) == (1080, 1920, 25, "blur_pad")
    assert sum((c.end or 0) - c.start for c in spec.clips) == pytest.approx(10.0)
    assert len(spec.clips) == 1  # cảnh chưa ảnh liền nhau → gộp một clip ảnh nền
    assert spec.subtitles.font_size == 60 and spec.subtitles.lines[0].text == "Câu một"
    assert all(line.end <= 10.0 + 1e-6 for line in spec.subtitles.lines)
    assert spec.audio.tracks[0].volume == 0.8 and spec.credit == "Kênh A" and spec.motion.zoom_max == 1.3
    assert service.build_preview_spec(db, state, DocConfig(subtitles=False)).subtitles.enabled is False


def test_long_subtitle_split_by_max_chars(db):
    pid, _ = _doc_project(db)
    state = service.get_state(db, pid)[1]
    state.transcript[0].reviewed_text = "một hai ba bốn năm sáu bảy tám chín mười " * 3
    lines = service._sub_lines(state, 20_000, 30)
    first = [x for x in lines if x.start < 4.0]
    assert len(first) > 1 and all(len(x.text) <= 30 for x in first)
    assert first[0].start == pytest.approx(0.5) and first[-1].end == pytest.approx(4.0)


def test_ken_burns_default_matches_previous_filter():
    spec = ProjectSpec(canvas=Canvas(w=1920, h=1080, fps=30, fit="crop"),
                       clips=[Clip(asset=1, start=0, end=3.0, motion="slow_zoom_in")])
    chain = _ken_burns("0:v", "v0", 0, spec, 3.0)
    assert "scale=3840:2160" in chain and "z='min(1+0.0015*on,1.2)'" in chain and ":d=1:" in chain
    fast = spec.model_copy(update={"motion": spec.motion.model_copy(update={"zoom_per_sec": 0.09, "upscale": 1.5})})
    chain2 = _ken_burns("0:v", "v0", 0, fast, 3.0)
    assert "scale=2880:1620" in chain2 and "0.003*on" in chain2


# ── render thật (nhỏ) ────────────────────────────────────────────────────────


def test_ken_burns_renders(tmp_path):
    img = tmp_path / "a.png"
    _ff("-f", "lavfi", "-i", "color=c=red:s=800x450", "-frames:v", "1", str(img))
    audio = tmp_path / "a.mp3"
    _ff("-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(audio))
    out = tmp_path / "out.mp4"
    (tmp_path / "work").mkdir()
    spec = ProjectSpec(
        canvas=Canvas(w=640, h=360, fps=30, fit="crop"),
        clips=[Clip(asset=1, start=0, end=2.0, motion="slow_zoom_in")],
        audio=Audio(original=0.0, tracks=[AudioTrack(asset=2, volume=1.0)]),
    )
    media = {
        1: Media(path=str(img), kind="image", duration=0.0, has_audio=False),
        2: Media(path=str(audio), kind="audio", duration=2.0, has_audio=True),
    }
    plan = build(spec, media, output=str(out), workdir=str(tmp_path / "work"),
                 font_file="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 fonts_dir="/usr/share/fonts/truetype/dejavu")
    subprocess.run(plan.argv, check=True, timeout=120, capture_output=True)
    frames = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert frames == "60"  # 2s × 30fps — không phải frames²


def test_audio_doc_flow_and_rights_lock(db, monkeypatch):
    monkeypatch.setattr(
        analyze.speech, "transcribe",
        lambda path, language=None: (_lines((0.0, 2.5, "Bruno Fernandes penalty"), (2.5, 5.0, "Cunha ghi bàn")), "vi"),
    )
    runtime_settings.upsert_setting(db, "doc.canvas", "1280x720")
    runtime_settings.upsert_setting(db, "doc.preview_sec", "8")
    mp3 = paths.ROOT / "fixtures" / "tone20.mp3"
    entry.accept_audio_doc(db, io.BytesIO(mp3.read_bytes()), "sample.mp3", title="POC", language="vi")
    for _ in range(30):
        claimed = taskqueue.claim(db, lanes=[Lane.HEAVY, Lane.LIGHT], worker_id="t")
        if claimed is None:
            break
        pipeline.run_task(db, claimed)

    project = db.query(StudioProject).order_by(StudioProject.id.desc()).first()
    assert project is not None and project.status == ProjectStatus.DRAFT
    detail = service.detail(db, project.id)
    assert detail["doc"]["transcript"][0]["raw_text"] == "Bruno Fernandes penalty"
    assert detail["rights_gate"]["window_end_ms"] == 8_000

    with pytest.raises(service.DocError, match="không render"):
        service.prepare_preview(db, project.id, require_rights=True)

    img_bytes = (paths.ROOT / "fixtures" / FIXTURE_IMG.name).read_bytes()
    for shot in service.get_state(db, project.id)[1].shots:
        if shot.start_ms < 8_000:
            service.attach_image(
                db, project.id, shot.shot_id, io.BytesIO(img_bytes), "frame.png",
                credit="internal", license="owned", rights_status=RightsStatus.RIGHTS_VERIFIED.value,
                illustration=True, proof_note="fixture",
            )

    out = entry.queue_doc_preview(db, project.id, require_rights=True)
    assert out["rights_ok"] is True and Path(out["manifest"]).is_file()
    for _ in range(15):
        claimed = taskqueue.claim(db, lanes=[Lane.HEAVY, Lane.LIGHT], worker_id="t")
        if claimed is None:
            break
        pipeline.run_task(db, claimed)
    db.refresh(project)
    assert project.status == ProjectStatus.RENDERED, project.error
    assert project.spec["canvas"]["w"] == 1280
    assert project.output_path and Path(project.output_path).is_file()


def test_many_image_clips_render_segment_by_segment(db):
    """Quá ``studio.segment_render_over`` cảnh ảnh → dựng từng cảnh rồi ghép; video ra đủ dài, có tiếng."""
    from app.features.studio import render

    img = paths.ROOT / "fixtures" / FIXTURE_IMG.name
    pic, _ = store.add_asset(db, img, kind="image", origin="brand", move=False)
    tone, _ = store.add_asset(db, paths.ROOT / "fixtures" / "tone20.mp3", kind="audio", origin="upload",
                              move=False, duration=20.0, has_audio=True)
    spec = ProjectSpec(
        canvas=Canvas(w=640, h=360, fps=25, fit="crop"),
        clips=[Clip(asset=pic.id, start=0, end=1.0, motion=m) for m in ("slow_zoom_in", "static", "pan_left")],
        audio=Audio(original=0.0, tracks=[AudioTrack(asset=tone.id, volume=1.0)]),
    )
    project = StudioProject(asset_id=tone.id, spec=spec.model_dump(mode="json"), status=ProjectStatus.DRAFT)
    db.add(project)
    db.commit()
    runtime_settings.upsert_setting(db, "studio.segment_render_over", "2")
    assert render.segmented(spec, {pic.id: Media(path=str(img), kind="image", duration=0, has_audio=False)}, 2)

    result = render.run(db, StudioTask(flow="doc_preview", stage="render", project_id=project.id, payload={}))
    assert "dựng theo 3 cảnh" in result.note
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries", "stream=codec_type,nb_read_frames",
         "-of", "csv=p=0", project.output_path], capture_output=True, text=True, check=True,
    ).stdout
    assert "video,75" in out and "audio" in out  # 3s × 25fps
