"""
PLAN-156 / ADR-064 — Audio → Documentary POC.
Không gọi mạng. Whisper bị thay. ffmpeg thật.
"""
from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as app_config
from app.core.database.models import Base, StudioAnalysis, StudioAsset, StudioProject, StudioTask
from app.core.media.ffmpeg_path import ffmpeg_available
from app.features.studio import analyze, entry, paths, pipeline, taskqueue
from app.features.studio.contracts import ProjectStatus
from app.features.studio.doc import rights, seed, service
from app.features.studio.doc.schema import ImageRef, RightsStatus
from app.features.studio.render.graph import Media, build
from app.features.studio.spec import Audio, AudioTrack, Canvas, Clip, ProjectSpec

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="cần ffmpeg")

STUDIO_TABLES = [m.__table__ for m in (StudioAsset, StudioAnalysis, StudioProject, StudioTask)]
FIXTURE_MP3 = Path(app_config.STORAGE_MEDIA_DIR) / "studio" / "fixtures" / "audio_doc_poc_60s.mp3"
FIXTURE_IMG = Path(app_config.STORAGE_MEDIA_DIR) / "studio" / "fixtures" / "placeholder_illustration.png"


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, timeout=120)


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'doc.sqlite'}")
    Base.metadata.create_all(engine, tables=STUDIO_TABLES)
    Session = sessionmaker(bind=engine)
    session = Session()
    root = tmp_path / "studio"
    monkeypatch.setattr(paths, "ROOT", root)
    for name in ("assets", "renders", "work", "inbox", "fixtures", "doc"):
        (root / name).mkdir(parents=True)
    # copy fixtures vào ROOT/fixtures của test
    if FIXTURE_MP3.is_file():
        (root / "fixtures" / FIXTURE_MP3.name).write_bytes(FIXTURE_MP3.read_bytes())
    if FIXTURE_IMG.is_file():
        (root / "fixtures" / FIXTURE_IMG.name).write_bytes(FIXTURE_IMG.read_bytes())
    else:
        _ff("-f", "lavfi", "-i", "color=c=blue:s=640x360", "-frames:v", "1", str(root / "fixtures" / "placeholder_illustration.png"))
    if not (root / "fixtures" / "audio_doc_poc_60s.mp3").is_file():
        _ff("-f", "lavfi", "-i", "sine=frequency=220:duration=8", str(root / "fixtures" / "audio_doc_poc_60s.mp3"))
    yield session
    session.close()


def test_seed_beats_clamped_to_duration():
    state = seed.build_initial_state(
        audio_asset_id=1, duration_ms=60_000, transcript_lines=[], lang="vi",
    )
    assert state.beats
    assert state.shots
    assert state.beats[0].start_ms == 0
    assert state.beats[-1].end_ms <= 60_000
    assert all(s.end_ms <= 60_000 for s in state.shots)


def test_rights_gate_blocks_unknown():
    state = seed.build_initial_state(audio_asset_id=1, duration_ms=30_000, transcript_lines=[], lang=None)
    state.preview_end_ms = 30_000
    shot = state.shots[0]
    shot.selected = ImageRef(asset_id=9, rights_status=RightsStatus.UNKNOWN, license="")
    gate = rights.check_export(state)
    assert not gate.ok
    assert any("RIGHTS_UNKNOWN" in b for b in gate.blockers)

    shot.selected = ImageRef(
        asset_id=9, rights_status=RightsStatus.RIGHTS_VERIFIED, license="owned", proof_note="poc",
    )
    gate2 = rights.check_export(state)
    # các shot khác vẫn thiếu ảnh trong cửa sổ preview
    assert not gate2.ok
    assert gate2.missing_images


def test_ken_burns_filtergraph_contains_zoompan(tmp_path):
    img = tmp_path / "a.png"
    _ff("-f", "lavfi", "-i", "color=c=red:s=800x450", "-frames:v", "1", str(img))
    audio = tmp_path / "a.mp3"
    _ff("-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(audio))
    out = tmp_path / "out.mp4"
    work = tmp_path / "work"
    work.mkdir()
    spec = ProjectSpec(
        canvas=Canvas(w=640, h=360, fps=30, fit="crop"),
        clips=[Clip(asset=1, start=0, end=2.0, motion="slow_zoom_in")],
        audio=Audio(original=0.0, tracks=[AudioTrack(asset=2, volume=1.0)]),
    )
    media = {
        1: Media(path=str(img), kind="image", duration=0.0, has_audio=False),
        2: Media(path=str(audio), kind="audio", duration=2.0, has_audio=True),
    }
    plan = build(
        spec, media, output=str(out), workdir=str(work),
        font_file="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        fonts_dir="/usr/share/fonts/truetype/dejavu",
    )
    graph = " ".join(plan.argv)
    assert "zoompan" in graph
    subprocess.run(plan.argv, check=True, timeout=120, capture_output=True)
    assert out.is_file() and out.stat().st_size > 1000


def test_audio_doc_flow_and_rights_lock(db, monkeypatch):
    monkeypatch.setattr(
        analyze.speech, "transcribe",
        lambda path, language=None: (
            [{"start": 0.0, "end": 2.5, "text": "Bruno Fernandes penalty"},
             {"start": 2.5, "end": 5.0, "text": "Matheus Cunha ghi ban"}],
            "vi",
        ),
    )
    mp3 = paths.ROOT / "fixtures" / "audio_doc_poc_60s.mp3"
    task = entry.accept_audio_doc(db, io.BytesIO(mp3.read_bytes()), "sample.mp3", title="MU Roma POC")
    assert task.flow == "audio_doc"

    from app.features.studio.contracts import Lane

    # chạy hết hàng việc light+heavy trong test
    for _ in range(30):
        claimed = taskqueue.claim(db, lanes=[Lane.HEAVY, Lane.LIGHT], worker_id="t")
        if claimed is None:
            break
        pipeline.run_task(db, claimed)

    project = db.query(StudioProject).order_by(StudioProject.id.desc()).first()
    assert project is not None
    assert project.status == ProjectStatus.DRAFT
    asset = db.get(StudioAsset, project.asset_id)
    assert asset is not None and asset.kind == "audio"
    assert abs(float(asset.duration or 0) - 60.0) < 1.5 or float(asset.duration or 0) > 5

    detail = service.detail(db, project.id)
    assert detail["doc"]["shots"]
    assert detail["doc"]["transcript"]
    assert detail["doc"]["transcript"][0]["raw_text"]
    # sửa reviewed
    segs = detail["doc"]["transcript"]
    segs[0]["reviewed_text"] = "Bruno Fernandes đá phạt đền"
    service.update_transcript(db, project.id, segs)

    # preview nghiêm → bị chặn
    with pytest.raises(service.DocError, match="không render"):
        service.prepare_preview(db, project.id, require_rights=True)

    # gắn ảnh hợp lệ cho mọi shot trong cửa sổ preview
    img_bytes = (paths.ROOT / "fixtures" / "placeholder_illustration.png").read_bytes()
    state = service.get_state(db, project.id)[1]
    for shot in state.shots:
        if shot.start_ms >= state.preview_end_ms:
            continue
        service.attach_image(
            db, project.id, shot.shot_id, io.BytesIO(img_bytes), "frame.png",
            credit="internal", license="owned", rights_status=RightsStatus.RIGHTS_VERIFIED.value,
            illustration=True, proof_note="poc fixture",
        )

    prepared = service.prepare_preview(db, project.id, require_rights=True)
    assert prepared["rights_ok"] is True
    assert Path(prepared["manifest"]).is_file()

    # xếp render + chạy
    out = entry.queue_doc_preview(db, project.id, require_rights=True)
    assert out["task_id"]
    for _ in range(15):
        claimed = taskqueue.claim(db, lanes=[Lane.HEAVY, Lane.LIGHT], worker_id="t")
        if claimed is None:
            break
        pipeline.run_task(db, claimed)

    db.refresh(project)
    assert project.status == ProjectStatus.RENDERED, project.error
    assert project.output_path and Path(project.output_path).is_file()


def _doc_project(db) -> tuple[int, StudioTask]:
    """Dựng dự án doc không qua whisper / render: asset audio 20s + chạy doc_plan."""
    from app.features.studio import doc, store

    mp3 = paths.ROOT / "fixtures" / "audio_doc_poc_60s.mp3"
    asset, _ = store.add_asset(db, mp3, kind="audio", origin="upload", move=False, duration=20.0, title="t")
    task = StudioTask(flow="audio_doc", stage="doc_plan", asset_id=asset.id, payload={})
    result = doc.run(db, task)
    return result.project_id, task


def test_doc_plan_rerun_reuses_project(db):
    from app.features.studio import doc

    pid, task = _doc_project(db)
    again = doc.run(db, task)
    assert again.project_id == pid
    assert db.query(StudioProject).count() == 1


def test_bad_shot_patch_rejected_and_state_still_loads(db):
    pid, _ = _doc_project(db)
    shot_id = service.get_state(db, pid)[1].shots[0].shot_id
    for patch in ({"motion": "spin"}, {"start_ms": -5}, {"end_ms": 0}, {"start_ms": "abc"}):
        with pytest.raises(service.DocError):
            service.update_shot(db, pid, shot_id, patch)
    with pytest.raises(service.DocError):
        service.update_transcript(db, pid, [{"raw_text": "thiếu mốc"}])
    # dữ liệu sai không lọt vào DocState — dự án vẫn mở được
    assert service.detail(db, pid)["doc"]["shots"][0]["motion"] != "spin"
    service.update_shot(db, pid, shot_id, {"motion": "pan_left"})
    assert service.get_state(db, pid)[1].shots[0].motion == "pan_left"


def test_bad_rights_rejected_without_orphan_asset(db):
    pid, _ = _doc_project(db)
    shot_id = service.get_state(db, pid)[1].shots[0].shot_id
    before = db.query(StudioAsset).count()
    img = (paths.ROOT / "fixtures" / "placeholder_illustration.png").read_bytes()
    with pytest.raises(service.DocError):
        service.attach_image(db, pid, shot_id, io.BytesIO(img), "a.png", rights_status="OK_LUON")
    assert db.query(StudioAsset).count() == before
    service.attach_image(db, pid, shot_id, io.BytesIO(img), "a.png")
    with pytest.raises(service.DocError):
        service.set_shot_rights(db, pid, shot_id, {"rights_status": "OK_LUON"})
    assert service.get_state(db, pid)[1].shots[0].selected.rights_status == RightsStatus.UNKNOWN


def test_ken_burns_one_frame_out_per_frame_in():
    """zoompan d=1 trên ảnh lặp. d=<số frame> từng làm WSL hết RAM 05/11 (frames² frame / hàng chờ concat)."""
    spec = ProjectSpec(
        canvas=Canvas(w=640, h=360, fps=30, fit="crop"),
        clips=[Clip(asset=1, start=0, end=3.0, motion="pan_left")],
        audio=Audio(original=0.0, tracks=[AudioTrack(asset=2, volume=1.0)]),
    )
    media = {
        1: Media(path="/x/a.png", kind="image", duration=0.0, has_audio=False),
        2: Media(path="/x/a.mp3", kind="audio", duration=5.0, has_audio=True),
    }
    joined = " ".join(build(spec, media, output="/x/o.mp4", workdir="/tmp", font_file="f.ttf", fonts_dir="/tmp").argv)
    assert "zoompan=" in joined and ":d=1:" in joined
    assert "/90)" in joined  # pan theo số frame của clip (3s × 30fps)
