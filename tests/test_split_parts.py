"""
ADR-041 — chia video dài thành nhiều phần, cắt ở chỗ "đang gay cấn".

Ba lớp: ``plan_cuts`` (hàm thuần, ba tầng), ``propose/apply`` (DB + đĩa tạm), và đường xử lý
cũ nhận phần con (không tải lại, KHÔNG chống trùng với anh em, cắt đúng mốc của từng phần).
Lớp cuối chạy nguyên ``process_material`` như production — không gọi tắt (bài học ADR-038).
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
from app.core.media.segments import Line, Silence, snap_to_boundary
from app.features.viral_intake import processor, reup_processor, reup_variants, split
from app.features.viral_intake.reup_processor import ReupResult
from app.features.viral_intake.service import ViralService
from app.features.viral_intake.split import MIN_PART_SEC, Plan, parse_ai_plan, plan_cuts


# ── plan_cuts: hàm thuần, ba tầng ───────────────────────────────────────────


def _lines(n: int, each: float = 10.0, gap: float = 1.0) -> list[Line]:
    """n câu, mỗi câu ``each`` giây, nghỉ ``gap`` giây giữa hai câu."""
    out, t = [], 0.0
    for i in range(n):
        out.append(Line(start=t, end=t + each, text=f"câu {i}"))
        t += each + gap
    return out


def _ai(answer: dict):
    return lambda prompt: json.dumps(answer, ensure_ascii=False)


def test_tang_1_AI_chon_cau_ket_va_cat_sau_cau_do_nua_khoang_lang():
    lines = _lines(30)  # 30 câu × 11s = 330s
    duration = 330.0
    ai = _ai({"parts": [{"end_line": 9, "hook": "vừa thấy phao chìm"}, {"end_line": 19, "hook": "cá kéo"}]})

    plan = plan_cuts(duration, 3, lines=lines, silence_list=[], scenes=[], ask_ai=ai)

    assert plan.by == "ai"
    # câu 9 kết ở 9*11+10 = 109; khoảng lặng tới câu 10 là 1s ⇒ cắt ở 109.5
    assert plan.parts[0] == (0.0, 109.5)
    assert plan.parts[1][0] == 109.5 and plan.parts[2][1] == duration
    assert plan.hooks == ["vừa thấy phao chìm", "cá kéo", "kết"]


def test_AI_tra_rac_thi_lui_ve_ranh_gioi_va_noi_ro():
    lines = _lines(30)
    sil = [Silence(start=109.0, end=111.0), Silence(start=219.0, end=221.0)]

    plan = plan_cuts(330.0, 3, lines=lines, silence_list=sil, scenes=[], ask_ai=lambda p: "xin lỗi tôi không rõ")

    assert plan.by == "boundary"
    assert [round(s, 1) for s, _ in plan.parts[1:]] == [110.0, 220.0]


def test_AI_tra_moc_lam_phan_qua_ngan_thi_KHONG_dung():
    """AI bảo cắt ngay câu đầu ⇒ phần 1 dài 10s < 20s ⇒ bỏ, lùi tầng."""
    lines = _lines(30)
    ai = _ai({"parts": [{"end_line": 0, "hook": "x"}, {"end_line": 15, "hook": "y"}]})

    plan = plan_cuts(330.0, 3, lines=lines, silence_list=[], scenes=[], ask_ai=ai)

    assert plan.by != "ai"


def test_AI_tra_sai_so_muc_thi_bo():
    lines = _lines(30)
    ai = _ai({"parts": [{"end_line": 9, "hook": "x"}]})  # cần 2 mục cho 3 phần

    assert plan_cuts(330.0, 3, lines=lines, silence_list=[], scenes=[], ask_ai=ai).by != "ai"


def test_AI_nem_loi_thi_khong_no():
    def boom(p):
        raise RuntimeError("429")

    plan = plan_cuts(300.0, 2, lines=_lines(30), silence_list=[], scenes=[], ask_ai=boom)

    assert plan.by in ("boundary", "even")


def test_it_cau_qua_thi_khong_hoi_AI():
    called = []

    def ai(p):
        called.append(p)
        return "{}"

    plan_cuts(300.0, 3, lines=_lines(4), silence_list=[], scenes=[], ask_ai=ai)

    assert not called, "4 câu cho 3 phần thì AI cũng chỉ đoán — không tốn lượt gọi"


def test_tang_2_uu_tien_khoang_lang_hon_doi_canh():
    """Cắt giữa khoảng lặng không đứt lời; đổi cảnh chỉ là dự phòng."""
    got = snap_to_boundary(100.0, silence_list=[Silence(103.0, 105.0)], scenes=[99.5])

    assert got == 104.0, "khoảng lặng xa hơn (4s) vẫn thắng đổi cảnh gần hơn (0.5s)"


def test_tang_2_ngoai_cua_so_thi_None():
    assert snap_to_boundary(100.0, silence_list=[Silence(110.0, 111.0)], scenes=[93.0]) is None


def test_tang_3_khong_co_gi_thi_chia_deu_va_noi_CHUA_tinh():
    plan = plan_cuts(300.0, 3, lines=[], silence_list=[], scenes=[], ask_ai=None)

    assert plan.by == "even"
    assert plan.parts == [(0.0, 100.0), (100.0, 200.0), (200.0, 300.0)]
    assert "CHƯA tính" in plan.note


def test_ranh_gioi_gan_nhat_lam_phan_qua_ngan_thi_ve_chia_deu():
    """Khoảng lặng ở giây 19 kéo mốc 50 về 19 ⇒ phần 1 = 19s < 20s ⇒ không dùng."""
    plan = plan_cuts(100.0, 2, lines=[], silence_list=[Silence(18.0, 20.0)], scenes=[], ask_ai=None)

    assert plan.by == "even" or plan.parts[0][1] >= MIN_PART_SEC


@pytest.mark.parametrize("n,expect", [(1, 2), (2, 2), (6, 6), (9, 6)])
def test_so_phan_bi_kep_trong_2_6(n, expect):
    assert plan_cuts(1000.0, n, lines=[], silence_list=[], scenes=[], ask_ai=None).n == expect


@pytest.mark.parametrize("text", [
    '{"parts": [{"end_line": 3, "hook": "a"}]}',
    'Đây là JSON:\n```json\n{"parts": [{"end_line": 3, "hook": "a"}]}\n```',
    '{"parts": [{"end_line": "3"}]}',
])
def test_doc_JSON_cua_AI_ke_ca_khi_boc_trong_van(text):
    assert parse_ai_plan(text) == [(3, "a")] or parse_ai_plan(text) == [(3, "")]


@pytest.mark.parametrize("text", [None, "", "không có json", '{"parts": []}', '{"parts": [{"hook": "x"}]}'])
def test_JSON_hong_thi_None(text):
    assert parse_ai_plan(text) is None


def test_plan_di_qua_JSON_khong_mat_gi():
    plan = Plan(n=2, parts=[(0.0, 50.25), (50.25, 100.0)], hooks=["a", "kết"], by="ai", note="n", duration=100.0, lines=7)

    back = Plan.from_json(plan.to_json())

    assert (back.n, back.parts, back.hooks, back.by, back.lines) == (2, plan.parts, plan.hooks, "ai", 7)


# ── propose / apply trên DB + đĩa tạm ───────────────────────────────────────


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'split.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def reup_dir(tmp_path, monkeypatch):
    d = tmp_path / "reup"
    monkeypatch.setattr(config, "REUP_DIR", d)
    return d


def _parent_with_source(session_factory, reup_dir, duration=300.0, status=ViralStatus.READY) -> int:
    with session_factory() as db:
        mat = ViralMaterial(platform="tiktok", url="https://t/1", title="Thả câu kể chuyện ### BOOST_CONTEXT: x ###",
                            views=999, status=status)
        db.add(mat)
        db.commit()
        mid = mat.id
    d = reup_dir / "tiktok"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"viral_{mid}_abc.mp4").write_bytes(b"\x00" * 4096)
    return mid


@pytest.fixture
def quiet_signals(monkeypatch):
    """Không ffmpeg, không Whisper, không AI — mọi tín hiệu rỗng ⇒ chia đều."""
    monkeypatch.setattr(split, "transcript_segments", lambda p: [])
    monkeypatch.setattr(split, "silences", lambda p: [])
    monkeypatch.setattr(split, "scene_changes", lambda p: [])
    monkeypatch.setattr(split, "ai_provider_ready", lambda db: (False, "chưa có key"))
    monkeypatch.setattr(ViralService, "probe_duration", staticmethod(lambda p: 300.0))
    monkeypatch.setattr(ViralService, "ensure_source_frames", staticmethod(lambda *a, **k: []))
    monkeypatch.setattr(ViralService, "build_frame_sheet", staticmethod(lambda *a, **k: None))


def test_de_nghi_luu_ke_hoach_len_cha(session_factory, reup_dir, quiet_signals):
    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        res = split.propose_split(db, mid, 3)

        assert res["ok"], res
        assert res["plan"].by == "even"
        assert db.get(ViralMaterial, mid).split_plan_dict["n"] == 3


def test_de_nghi_khong_co_file_goc_thi_bao_ro(session_factory, reup_dir, quiet_signals):
    with session_factory() as db:
        mat = ViralMaterial(platform="tiktok", url="https://t/2", title="x", views=1, status=ViralStatus.NEW)
        db.add(mat)
        db.commit()

        res = split.propose_split(db, mat.id, 3)

        assert not res["ok"] and "file gốc" in res["msg"]


def test_video_ngan_khong_du_chia(session_factory, reup_dir, quiet_signals, monkeypatch):
    monkeypatch.setattr(ViralService, "probe_duration", staticmethod(lambda p: 50.0))
    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        res = split.propose_split(db, mid, 3)

        assert not res["ok"] and "không đủ" in res["msg"]


def test_AI_san_sang_thi_duoc_hoi_va_ke_hoach_ghi_by_ai(session_factory, reup_dir, quiet_signals, monkeypatch):
    from app.core.ai import use_cases

    monkeypatch.setattr(split, "transcript_segments", lambda p: _lines(30))
    monkeypatch.setattr(ViralService, "probe_duration", staticmethod(lambda p: 330.0))
    monkeypatch.setattr(split, "ai_provider_ready", lambda db: (True, ""))
    monkeypatch.setattr(
        use_cases.AIUseCases, "generate_text",
        staticmethod(lambda prompt, purpose=None: (json.dumps({"parts": [{"end_line": 14, "hook": "hồi hộp"}]}), {})),
    )
    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        res = split.propose_split(db, mid, 2)

        assert res["ok"] and res["plan"].by == "ai"
        assert res["plan"].hooks[0] == "hồi hộp"


def test_tao_phan_con_dung_moc_tieu_de_va_file(session_factory, reup_dir, quiet_signals):
    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        split.propose_split(db, mid, 3)
        res = split.apply_split(db, mid)

        assert res["ok"], res
        kids = split.existing_parts(db, mid)
        assert [k.part_index for k in kids] == [1, 2, 3]
        assert [(k.clip_start_sec, k.clip_length_sec) for k in kids] == [(0, 100), (100, 100), (200, 100)]
        assert kids[1].title == "Thả câu kể chuyện (Phần 2/3)", "marker phải bị bóc, số phần phải có"
        assert len({k.url for k in kids}) == 3, "cột url unique — mỗi phần một url"
        assert all(k.status == ViralStatus.NEW for k in kids)
        for k in kids:
            src = ViralService.find_source_path(k.id, "tiktok")
            assert src and os.path.getsize(src) == 4096, "file gốc phải thấy được dưới tên của CON"


def test_khong_tao_lai_khi_da_chia(session_factory, reup_dir, quiet_signals):
    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        split.propose_split(db, mid, 2)
        assert split.apply_split(db, mid)["ok"]

        res = split.apply_split(db, mid)

        assert not res["ok"] and "đã chia rồi" in res["msg"]


def test_chua_co_ke_hoach_thi_khong_tao(session_factory, reup_dir, quiet_signals):
    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        res = split.apply_split(db, mid)

        assert not res["ok"] and "kế hoạch" in res["msg"]


def test_phan_con_khong_chia_tiep(session_factory, reup_dir, quiet_signals):
    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        split.propose_split(db, mid, 2)
        split.apply_split(db, mid)
        kid = split.existing_parts(db, mid)[0].id

        res = split.propose_split(db, kid, 2)

        assert not res["ok"] and "phần con" in res["msg"]


# ── đường xử lý CŨ nhận phần con — chạy nguyên process_material ─────────────


@pytest.fixture
def fake_pipeline(reup_dir, monkeypatch):
    """yt-dlp + ReupProcessor giả như test ADR-018, thêm: ghi lại clip_start/clip_length mỗi lần cắt."""
    monkeypatch.setattr(processor, "_get_runtime_int", lambda db, key, fallback: fallback)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    monkeypatch.setattr(ViralService, "ensure_reup_thumbnail", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(reup_variants, "record_reup_variant", lambda **k: None)
    # Không có bảng runtime_settings trong SQLite tạm ⇒ processor coi keep_source_days = 0 và
    # XOÁ file gốc ngay — production giữ 7 ngày (ADR-032). Giả lập đúng production.
    monkeypatch.setattr(processor.runtime_settings, "get_int", lambda key, default=0, db=None: 7)
    monkeypatch.setattr(processor.runtime_settings, "get_bool", lambda key, default=False, db=None: False)

    calls: dict = {"preflight": 0, "download": 0, "reup": []}

    def fake_run(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd]
        if "--dump-single-json" in argv:
            calls["preflight"] += 1
            info = {"title": "demo", "view_count": 1234, "formats": [{"vcodec": "h264", "ext": "mp4"}]}
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(info), stderr="")
        if "-o" not in argv:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
        calls["download"] += 1
        template = argv[argv.index("-o") + 1]
        out = template.replace("%(id)s", "src").replace("%(ext)s", "mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(b"\x00" * 2048)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(processor.subprocess, "run", fake_run)

    def fake_reup(input_path, platform="unknown", **kwargs):
        calls["reup"].append((os.path.basename(input_path), kwargs.get("clip_start"), kwargs.get("clip_length"), kwargs.get("force")))
        out = input_path.replace(".mp4", "_reup.mp4")
        with open(out, "wb") as fh:
            fh.write(b"\x01" * 4096)
        return ReupResult(success=True, output_path=out, metrics={})

    monkeypatch.setattr(reup_processor.ReupProcessor, "process", staticmethod(fake_reup))
    return calls


def test_phan_con_di_nguyen_duong_cu_khong_tai_lai_khong_bi_coi_la_trung(session_factory, reup_dir, fake_pipeline, quiet_signals):
    """
    Cái bẫy thật: phần con GIỐNG HỆT cha (cùng file) ⇒ sha256 trùng ⇒ ADR-024 sẽ đánh DUPLICATE
    và bỏ qua. Không có guard thì tính năng chia phần chết ngay lượt đầu, và báo "trùng" —
    nhãn nói dối kiểu mới.
    """
    # 1. cha đi đường cũ: tải + cắt ⇒ có file gốc `viral_<cha>_src.mp4`
    with session_factory() as db:
        mat = ViralMaterial(platform="facebook", url="https://www.facebook.com/reel/1", title="Kể chuyện", views=0,
                            status=ViralStatus.NEW)
        db.add(mat)
        db.commit()
        mid = mat.id
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
    assert fake_pipeline["preflight"] == 1 and fake_pipeline["download"] == 1

    # 2. chia 2 phần
    with session_factory() as db:
        _p = split.propose_split(db, mid, 2)
        assert _p["ok"], _p
        res = split.apply_split(db, mid)
        assert res["ok"], res
        kids = [k.id for k in split.existing_parts(db, mid)]

    # 3. mỗi phần đi NGUYÊN process_material
    for cid in kids:
        with session_factory() as db:
            ok, msg = ViralService.process_material(db, cid)
            assert ok, msg
            k = db.get(ViralMaterial, cid)
            assert k.status == ViralStatus.READY, (k.status, k.last_error)

    assert fake_pipeline["preflight"] == 1 and fake_pipeline["download"] == 1, "phần con KHÔNG được tải lại"
    parts = fake_pipeline["reup"][1:]
    assert [(c, l, f) for _, c, l, f in parts] == [(0.0, 150.0, True), (150.0, 150.0, True)], parts
    assert all(name.startswith(f"viral_{cid}_phan") for name, cid in zip((p[0] for p in parts), kids)), \
        "mỗi phần cắt trên file MANG TÊN CỦA NÓ — không thì hai bản _reup đè nhau"


def test_phan_con_mat_file_goc_thi_FAILED_voi_ly_do(session_factory, reup_dir, fake_pipeline, quiet_signals):
    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        split.propose_split(db, mid, 2)
        split.apply_split(db, mid)
        kid = split.existing_parts(db, mid)[0].id
    for f in (reup_dir / "tiktok").iterdir():
        f.unlink()
    with session_factory() as db:
        ok, _ = ViralService.process_material(db, kid)
        k = db.get(ViralMaterial, kid)

        assert not ok and k.status == ViralStatus.FAILED
        assert "file gốc" in (k.last_error or "")
    assert fake_pipeline["download"] == 0, "không được lén tải lại bằng url giả '#phan1'"


# ── tin Telegram + caption biết mình là phần mấy ────────────────────────────


def test_tin_san_sang_co_dong_phan():
    from types import SimpleNamespace

    from app.core.notifier import formatting as nf

    mat = SimpleNamespace(id=12, platform="tiktok", title="x", views=1, ai_caption=None, ai_hashtags_list=[],
                          ai_caption_error=None, clip_start_sec=100, parent_material_id=7, part_index=2, part_total=3)

    text = nf.material_ready_message(mat, "/x/a.mp4")

    assert "Phần 2/3" in text and "#7" in text


def test_tin_thuong_khong_co_dong_phan():
    from types import SimpleNamespace

    from app.core.notifier import formatting as nf

    mat = SimpleNamespace(id=12, platform="tiktok", title="x", views=1, ai_caption=None, ai_hashtags_list=[],
                          ai_caption_error=None, clip_start_sec=None)

    assert "Phần" not in nf.material_ready_message(mat, "/x/a.mp4")


def test_caption_phan_con_duoc_bao_la_phan_may(session_factory, reup_dir, quiet_signals, monkeypatch):
    """Ngữ cảnh đưa cho AI phải nói rõ phần mấy và (chưa cuối) mời xem tiếp."""
    from app.core import orchestrator
    from app.features.viral_intake import service as svc

    seen = {}

    class _Orch:
        def generate_caption(self, path, style="", context="", **k):
            seen["context"] = context
            return {"caption": "ok", "hashtags": []}

    monkeypatch.setattr(orchestrator, "ContentOrchestrator", _Orch)
    monkeypatch.setattr(svc, "ai_provider_ready", lambda db=None: (True, ""))
    monkeypatch.setattr(ViralService, "find_reup_path", staticmethod(lambda *a, **k: "/x/reup.mp4"))
    from app.core import settings as rs
    monkeypatch.setattr(rs, "get_str", lambda *a, **k: "short")

    mid = _parent_with_source(session_factory, reup_dir)
    with session_factory() as db:
        split.propose_split(db, mid, 3)
        split.apply_split(db, mid)
        k1, _k2, k3 = split.existing_parts(db, mid)

        ViralService.generate_caption_for_material(db, k1.id, notify=False)
        assert "PHẦN 1/3" in seen["context"] and "Phần 2" in seen["context"]

        ViralService.generate_caption_for_material(db, k3.id, notify=False)
        assert "PHẦN 3/3" in seen["context"] and "KẾT" in seen["context"]
