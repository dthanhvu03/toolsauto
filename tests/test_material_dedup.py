"""
ADR-024 mục 2 — chống trùng nội dung ở tầng material.

Hai phần:
1. Hàm thuần (``hamming`` / ``phash_distance`` / ``find_duplicate``) — SQLite tạm, không file.
2. Pipeline: material trùng ⇒ ``DUPLICATE``, **ReupProcessor.process không được gọi**
   (mục đích chính của ADR là không tốn ffmpeg), file vừa tải bị xoá.
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
from app.core.database.models import Account, Job, ViralMaterial
from app.features.viral_intake import dedup, processor, reup_processor, reup_variants
from app.features.viral_intake.dedup import find_duplicate, hamming, phash_distance
from app.features.viral_intake.reup_processor import ReupResult
from app.features.viral_intake.service import ViralService

ZERO = "0000000000000000"  # pHash 64-bit toàn 0
ONES = "ffffffffffffffff"  # toàn 1 — cách ZERO đúng 64 bit
NEAR = "0000000000000003"  # cách ZERO 2 bit


# ---------------------------------------------------------------- (a) hamming


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (ZERO, ZERO, 0),
        (ZERO, "0000000000000001", 1),
        (ZERO, NEAR, 2),
        (ZERO, "00000000000000ff", 8),
        (ZERO, ONES, 64),
        ("a1b2c3d4e5f60718", "a1b2c3d4e5f60718", 0),
    ],
)
def test_hamming_known_pairs(a, b, expected):
    assert hamming(a, b) == expected
    assert hamming(b, a) == expected  # đối xứng


@pytest.mark.parametrize(
    "a, b",
    [
        (ZERO, "0000"),  # độ dài lệch — pHash khác kích thước
        ("abc", "abcd"),
        (ZERO, ""),
        ("", ""),
        (ZERO, None),
        (ZERO, "khong-phai-hex!!"),  # đúng độ dài nhưng không parse được
    ],
)
def test_hamming_mismatched_length_is_far(a, b):
    """Độ dài khác nhau ⇒ số lớn: coi như KHÔNG trùng, không được chặn oan."""
    assert hamming(a, b) >= dedup.UNRELATED_DISTANCE
    assert hamming(a, b) > 32  # lớn hơn max của setting viral.phash_max_distance


# -------------------------------------------------------- (b) phash_distance


def test_phash_distance_sorts_by_seconds_not_by_string():
    """
    Ca chốt: sort theo chuỗi thì ``"10.00s" < "2.00s"`` ⇒ ghép khung cuối với khung đầu.
    Hai map dưới đây trùng khít khi ghép ĐÚNG thứ tự thời gian (0), và lệch tối đa (64)
    nếu ghép sai. Số ra 0 chứng minh code sort theo số giây.
    """
    map_a = {"2.00s": ZERO, "10.00s": ONES}
    map_b = {"3.00s": ZERO, "9.00s": ONES}
    assert phash_distance(map_a, map_b) == 0

    # Cùng dữ liệu nhưng đảo vai một bên ⇒ phải ra 64, không phải 0.
    map_c = {"3.00s": ONES, "9.00s": ZERO}
    assert phash_distance(map_a, map_c) == 64


def test_phash_distance_uses_median_not_mean():
    """Một khung lệch hẳn (frame đen / chèn quảng cáo) không được kéo cả video thành 'khác'."""
    map_a = {"1.00s": ZERO, "2.00s": ZERO, "3.00s": ZERO}
    map_b = {"1.00s": ZERO, "2.00s": NEAR, "3.00s": ONES}
    assert phash_distance(map_a, map_b) == 2  # trung vị của [0, 2, 64]; trung bình là 22


def test_phash_distance_pairs_only_overlapping_frames():
    map_a = {"1.00s": ZERO, "2.00s": ZERO, "3.00s": ZERO}
    map_b = {"1.50s": ZERO, "2.50s": NEAR}
    assert phash_distance(map_a, map_b) == 1  # trung vị của [0, 2]


@pytest.mark.parametrize(
    "map_a, map_b",
    [
        ({}, {"1.00s": ZERO}),
        ({"1.00s": ZERO}, {}),
        ({}, {}),
        (None, {"1.00s": ZERO}),
        ({"1.00s": ""}, {"1.00s": ZERO}),  # có khoá nhưng giá trị rỗng
    ],
)
def test_phash_distance_missing_data_is_none(map_a, map_b):
    assert phash_distance(map_a, map_b) is None


# ------------------------------------------------------------- find_duplicate


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dedup.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


def _add(db, *, url, status, content_hash=None, phash_map=None) -> int:
    mat = ViralMaterial(
        platform="tiktok",
        url=url,
        title="x",
        views=1,
        status=status,
        content_hash=content_hash,
        phash=json.dumps(phash_map) if phash_map else None,
    )
    db.add(mat)
    db.commit()
    return mat.id


def test_phash_map_property_tolerates_garbage(session_factory):
    with session_factory() as db:
        mid = _add(db, url="u-garbage", status=ViralStatus.READY)
        mat = db.get(ViralMaterial, mid)
        for raw in (None, "", "khong-phai-json", "[1,2,3]", '"chuoi"'):
            mat.phash = raw
            assert mat.phash_map == {}
        mat.phash = json.dumps({"1.00s": ZERO})
        assert mat.phash_map == {"1.00s": ZERO}


def test_find_duplicate_matches_sha256(session_factory):
    """(c) sha256 giống hệt — đường rẻ nhất, không cần pHash."""
    with session_factory() as db:
        existing = _add(db, url="u1", status=ViralStatus.READY, content_hash="deadbeef")
        hit = find_duplicate(
            db, content_hash="deadbeef", phash_map={}, exclude_id=None, max_distance=8
        )
        assert hit is not None
        mid, reason = hit
        assert mid == existing
        assert reason == f"Trùng nội dung với #{existing} (sha256 giống hệt)"


def test_find_duplicate_matches_phash_within_threshold(session_factory):
    """(d) sha256 KHÁC nhau (video bị mã hoá lại) nhưng pHash gần ⇒ vẫn bắt được."""
    with session_factory() as db:
        existing = _add(
            db,
            url="u1",
            status=ViralStatus.DRAFTED,
            content_hash="aaaa",
            phash_map={"1.00s": ZERO, "2.00s": ZERO},
        )
        hit = find_duplicate(
            db,
            content_hash="bbbb",  # file khác byte hoàn toàn
            phash_map={"1.00s": ZERO, "2.00s": NEAR},  # trung vị = 1
            exclude_id=None,
            max_distance=8,
        )
        assert hit == (existing, f"Trùng nội dung với #{existing} (pHash cách 1)")


def test_find_duplicate_returns_nearest_candidate(session_factory):
    with session_factory() as db:
        _add(db, url="far", status=ViralStatus.READY, phash_map={"1.00s": "00000000000000ff"})
        near = _add(db, url="near", status=ViralStatus.READY, phash_map={"1.00s": NEAR})
        hit = find_duplicate(
            db, content_hash=None, phash_map={"1.00s": ZERO}, exclude_id=None, max_distance=8
        )
        assert hit == (near, f"Trùng nội dung với #{near} (pHash cách 2)")


def test_find_duplicate_outside_threshold_is_none(session_factory):
    """(e) Ngoài ngưỡng ⇒ None — video khác không bị chặn oan."""
    with session_factory() as db:
        _add(db, url="u1", status=ViralStatus.READY, phash_map={"1.00s": ZERO})
        assert (
            find_duplicate(
                db, content_hash=None, phash_map={"1.00s": ONES}, exclude_id=None, max_distance=8
            )
            is None
        )


def test_find_duplicate_threshold_zero_only_blocks_sha256(session_factory):
    """max_distance=0 ⇒ pHash cách 2 không tính là trùng, nhưng sha256 giống hệt vẫn chặn."""
    with session_factory() as db:
        existing = _add(
            db, url="u1", status=ViralStatus.READY, content_hash="cafe", phash_map={"1.00s": ZERO}
        )
        assert (
            find_duplicate(
                db, content_hash="beef", phash_map={"1.00s": NEAR}, exclude_id=None, max_distance=0
            )
            is None
        )
        assert find_duplicate(
            db, content_hash="cafe", phash_map={}, exclude_id=None, max_distance=0
        ) == (existing, f"Trùng nội dung với #{existing} (sha256 giống hệt)")


def test_find_duplicate_excludes_itself(session_factory):
    """(f) Không được so material với chính nó — nếu không thì video nào cũng 'trùng'."""
    with session_factory() as db:
        mid = _add(
            db,
            url="u1",
            status=ViralStatus.READY,
            content_hash="deadbeef",
            phash_map={"1.00s": ZERO},
        )
        assert (
            find_duplicate(
                db,
                content_hash="deadbeef",
                phash_map={"1.00s": ZERO},
                exclude_id=mid,
                max_distance=8,
            )
            is None
        )


@pytest.mark.parametrize(
    "status", [ViralStatus.NEW, ViralStatus.FAILED, ViralStatus.DUPLICATE, ViralStatus.PROCESSING]
)
def test_find_duplicate_ignores_non_stock_statuses(session_factory, status):
    """(g) NEW/FAILED/PROCESSING chưa (hoặc không) có file; DUPLICATE chính là bản bị chặn."""
    with session_factory() as db:
        _add(db, url=f"u-{status}", status=status, content_hash="deadbeef", phash_map={"1.00s": ZERO})
        assert (
            find_duplicate(
                db,
                content_hash="deadbeef",
                phash_map={"1.00s": ZERO},
                exclude_id=None,
                max_distance=8,
            )
            is None
        )


@pytest.mark.parametrize("status", [ViralStatus.READY, ViralStatus.DRAFTED, ViralStatus.REUP])
def test_find_duplicate_covers_stock_statuses(session_factory, status):
    with session_factory() as db:
        mid = _add(db, url=f"u-{status}", status=status, content_hash="deadbeef")
        hit = find_duplicate(
            db, content_hash="deadbeef", phash_map={}, exclude_id=None, max_distance=8
        )
        assert hit is not None and hit[0] == mid


def test_duplicate_status_exists_and_is_distinct():
    assert ViralStatus.DUPLICATE == "DUPLICATE"
    assert ViralStatus.DUPLICATE not in (ViralStatus.FAILED, ViralStatus.READY)


def test_setting_spec_phash_max_distance():
    from app.core.settings import SETTINGS

    spec = SETTINGS["viral.phash_max_distance"]
    assert spec.type == "int" and spec.default_getter() == 8
    assert (spec.min, spec.max) == (0, 32)
    assert "trùng" in spec.description.lower()


# ------------------------------------------------------------- (h)(i) pipeline


@pytest.fixture
def fake_pipeline(tmp_path, monkeypatch):
    """yt-dlp + pHash giả. ``ReupProcessor.process`` NỔ nếu bị gọi — bằng chứng không tốn ffmpeg."""
    reup_dir = tmp_path / "reup"
    monkeypatch.setattr(config, "REUP_DIR", reup_dir)
    monkeypatch.setattr(processor, "_get_runtime_int", lambda db, key, fallback: fallback)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    monkeypatch.setattr(ViralService, "ensure_reup_thumbnail", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(reup_variants, "record_reup_variant", lambda **k: None)

    state: dict = {"reup_calls": 0, "downloaded": [], "phash": {"1.00s": ZERO, "2.00s": ZERO}}

    def fake_run(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd]
        if "--dump-single-json" in argv:
            info = {"title": "demo", "view_count": 5, "formats": [{"vcodec": "h264", "ext": "mp4"}]}
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(info), stderr="")
        out = argv[argv.index("-o") + 1].replace("%(id)s", "src").replace("%(ext)s", "mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(b"\x00" * 2048)
        state["downloaded"].append(out)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(processor.subprocess, "run", fake_run)
    monkeypatch.setattr(
        processor.VideoProtector, "extract_phash", staticmethod(lambda *a, **k: dict(state["phash"]))
    )

    def boom_reup(*a, **k):
        state["reup_calls"] += 1
        raise AssertionError("ReupProcessor.process bị gọi — ADR-024 phải chặn TRƯỚC ffmpeg")

    monkeypatch.setattr(reup_processor.ReupProcessor, "process", staticmethod(boom_reup))
    return state


def _new_material(session_factory, url: str) -> int:
    with session_factory() as db:
        return _add(db, url=url, status=ViralStatus.NEW)


def test_pipeline_marks_duplicate_without_running_ffmpeg(session_factory, fake_pipeline):
    """(h) Trùng ⇒ DUPLICATE + last_error có '#', ReupProcessor KHÔNG chạy, file đã tải bị xoá."""
    with session_factory() as db:
        existing = _add(
            db,
            url="https://www.tiktok.com/@a/video/111",
            status=ViralStatus.READY,
            content_hash="khac-hoan-toan",
            phash_map={"1.00s": ZERO, "2.00s": NEAR},  # pHash cách 1 ⇒ trong ngưỡng 8
        )

    mid = _new_material(session_factory, "https://www.tiktok.com/@b/video/222")
    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        mat = db.get(ViralMaterial, mid)
        assert mat.status == ViralStatus.DUPLICATE
        assert "#" in (mat.last_error or "")
        assert f"#{existing}" in mat.last_error
        assert "pHash" in mat.last_error
        assert mat.content_hash  # sha256 vẫn được ghi lại để lần sau so rẻ hơn
        assert mat.phash_map == {"1.00s": ZERO, "2.00s": ZERO}
        assert db.query(Job).count() == 0

    assert fake_pipeline["reup_calls"] == 0, "ffmpeg đã chạy — hỏng đúng mục đích của ADR-024"
    assert fake_pipeline["downloaded"], "phải có file tải về thì mới chứng minh được là đã xoá"
    for path in fake_pipeline["downloaded"]:
        assert not os.path.exists(path), f"file tải về chưa bị xoá: {path}"


def test_pipeline_duplicate_material_not_picked_up_again(session_factory, fake_pipeline):
    """DUPLICATE không nằm trong tập sweep (NEW/REUP/FAILED) nên không bị xử lý lại."""
    with session_factory() as db:
        mid = _add(db, url="https://www.tiktok.com/@b/video/333", status=ViralStatus.DUPLICATE)
        ok, msg = ViralService.process_material(db, mid)
        assert "DUPLICATE" in msg or not ok
        assert db.get(ViralMaterial, mid).status == ViralStatus.DUPLICATE
    assert fake_pipeline["reup_calls"] == 0


def test_pipeline_unique_material_still_reaches_ready(session_factory, fake_pipeline, monkeypatch):
    """(i) Không trùng ⇒ đường cũ y nguyên: reup chạy, material về READY, không có job."""
    calls = {"reup": 0}

    def fake_reup(input_path, platform="unknown", **kwargs):
        calls["reup"] += 1
        out = input_path.replace(".mp4", "_reup.mp4")
        with open(out, "wb") as fh:
            fh.write(b"\x01" * 4096)
        return ReupResult(success=True, output_path=out, metrics={})

    monkeypatch.setattr(reup_processor.ReupProcessor, "process", staticmethod(fake_reup))

    with session_factory() as db:
        _add(
            db,
            url="https://www.tiktok.com/@a/video/444",
            status=ViralStatus.READY,
            content_hash="khac-hoan-toan",
            phash_map={"1.00s": ONES, "2.00s": ONES},  # cách 64 ⇒ ngoài ngưỡng
        )

    mid = _new_material(session_factory, "https://www.tiktok.com/@b/video/555")
    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        mat = db.get(ViralMaterial, mid)
        assert mat.status == ViralStatus.READY
        assert mat.last_error is None
        assert mat.content_hash and mat.phash_map
        assert db.query(Job).count() == 0
    assert calls["reup"] == 1
