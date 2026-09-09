"""
ADR-031 — chọn mốc bắt đầu cắt.

Bối cảnh đo được 2026-09-09: video nguồn `@thacaukechuyen` dài 389-652 giây, tool giữ 90 giây
ĐẦU. Bóc khung hình video 573s có 2,2 triệu view: giây 45 còn đang móc mồi, giây 320 mới có
con cá. Tức tool đang xuất bản cảnh móc mồi và cắt bỏ đúng đoạn tạo ra kết quả.

Đã thử và loại phương án tự dò: năng lượng âm thanh cả video phẳng 59-81%, cửa sổ "ồn nhất"
chỉ hơn cửa sổ hiện tại 3 điểm phần trăm. Không có tín hiệu để dò.
"""
from __future__ import annotations

import subprocess

import pytest

from app.features.viral_intake.reup_processor import ReupProcessor


@pytest.fixture
def ffmpeg_cmd(monkeypatch):
    """Bắt argv ffmpeg thay vì chạy thật — kiểm `-ss`/`-t` được ghép đúng."""
    seen: list[list[str]] = []

    def fake_run(cmd, *a, **k):
        seen.append([str(c) for c in cmd])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def _ss_of(argv: list[str]) -> float | None:
    return float(argv[argv.index("-ss") + 1]) if "-ss" in argv else None


def _t_of(argv: list[str]) -> float | None:
    return float(argv[argv.index("-t") + 1]) if "-t" in argv else None


# ── độ dài tối đa lấy từ Thiết lập ───────────────────────────────────────────


def test_max_duration_lay_tu_o_cai_dat(monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: 60)

    assert ReupProcessor._configured_max_duration() == 60.0


def test_o_cai_dat_hong_thi_lui_ve_hang_so_trong_code(monkeypatch):
    """Đọc cài đặt đụng DB — hỏng ở đó không được làm chết cả lượt xử lý video."""
    from app.core import settings as runtime_settings

    def boom(*a, **k):
        raise RuntimeError("DB chết")

    monkeypatch.setattr(runtime_settings, "get_int", boom)

    assert ReupProcessor._configured_max_duration() == float(ReupProcessor.MAX_REELS_DURATION)


def test_gia_tri_vo_ly_thi_lui_ve_mac_dinh(monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: 0)

    assert ReupProcessor._configured_max_duration() == float(ReupProcessor.MAX_REELS_DURATION)


# ── clip_start đi vào -ss ────────────────────────────────────────────────────


def test_process_nhan_tham_so_clip_start():
    import inspect

    params = inspect.signature(ReupProcessor.process).parameters
    assert "clip_start" in params
    assert params["clip_start"].default == 0.0, "mặc định phải là 0 = giữ nguyên hành vi cũ"


def test_ma_nguon_cong_clip_start_vao_ss_chu_khong_them_lan_re_encode():
    """Một chỗ `-ss` duy nhất, dùng chung với head_trim chống trùng."""
    src = ReupProcessor.__module__
    import importlib
    import pathlib

    path = pathlib.Path(importlib.import_module(src).__file__)
    code = path.read_text(encoding="utf-8")

    assert "seek += clip_start" in code
    # Đếm chính xác lượt mã hoá chính; "trim_cmd" của nhánh dự phòng cũng chứa chuỗi "cmd"
    # nên phải khớp cả biểu thức, không khớp tiền tố.
    assert code.count('cmd += ["-ss", f"{seek:.3f}"]') == 1, "chỉ một chỗ ghép -ss ở lượt chính"
    # độ dài còn lại phải trừ cả seek, không chỉ head_trim
    assert "effective_duration = duration - seek if seek > 0 else duration" in code


def test_moc_vuot_do_dai_video_thi_bo_qua():
    """Gõ nhầm 9999 cho video 573 giây thì phải cắt từ đầu, không ra file rỗng."""
    import importlib
    import pathlib

    code = pathlib.Path(importlib.import_module(ReupProcessor.__module__).__file__).read_text(encoding="utf-8")

    assert "clip_start > 0 and duration > (clip_start + 2.0)" in code


# ── set_clip_start ──────────────────────────────────────────────────────────


@pytest.fixture
def session_factory(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database.models import Account, Job, RuntimeSetting, ViralMaterial, ViralSource

    engine = create_engine(f"sqlite:///{tmp_path / 'clip.sqlite'}")
    for model in (Account, ViralMaterial, ViralSource, Job, RuntimeSetting):
        model.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


def _material(session_factory, **over):
    from app.constants import ViralStatus
    from app.core.database.models import ViralMaterial

    with session_factory() as db:
        base = dict(platform="tiktok", url="https://t/1", title="x", views=1,
                    status=ViralStatus.READY, last_error="lỗi cũ")
        base.update(over)
        mat = ViralMaterial(**base)
        db.add(mat)
        db.commit()
        return mat.id


def test_dat_moc_thi_ve_REUP_de_duong_xu_ly_tai_lai(session_factory):
    """
    Không cắt lại tại chỗ được: file gốc đã xoá, bản _reup chỉ còn 90 giây đầu. REUP là status
    duy nhất được xử lý lại bất kể views.
    """
    from app.constants import ViralStatus
    from app.core.database.models import ViralMaterial
    from app.features.viral_intake.service import ViralService

    mid = _material(session_factory)
    with session_factory() as db:
        ok, msg = ViralService.set_clip_start(db, mid, 300)

        assert ok, msg
        mat = db.get(ViralMaterial, mid)
        assert mat.clip_start_sec == 300
        assert mat.status == ViralStatus.REUP
        assert mat.last_error is None
        assert "giây 300" in msg


def test_bo_trong_thi_ve_None_tuc_cat_tu_dau(session_factory):
    from app.core.database.models import ViralMaterial
    from app.features.viral_intake.service import ViralService

    mid = _material(session_factory, clip_start_sec=300)
    with session_factory() as db:
        ok, msg = ViralService.set_clip_start(db, mid, None)

        assert ok and "từ đầu" in msg
        assert db.get(ViralMaterial, mid).clip_start_sec is None


@pytest.mark.parametrize("value,needle", [("abc", "số giây"), (-5, "không được âm")])
def test_gia_tri_sai_thi_tu_choi_khong_ghi_gi(session_factory, value, needle):
    from app.constants import ViralStatus
    from app.core.database.models import ViralMaterial
    from app.features.viral_intake.service import ViralService

    mid = _material(session_factory)
    with session_factory() as db:
        ok, msg = ViralService.set_clip_start(db, mid, value)

        assert not ok and needle in msg
        mat = db.get(ViralMaterial, mid)
        assert mat.clip_start_sec is None
        assert mat.status == ViralStatus.READY, "từ chối thì không được đổi status"


def test_id_la_thi_tra_False_khong_nem(session_factory):
    from app.features.viral_intake.service import ViralService

    with session_factory() as db:
        ok, msg = ViralService.set_clip_start(db, 9999, 100)

        assert not ok and "9999" in msg


def test_processor_truyen_moc_xuong_reup():
    import importlib
    import pathlib

    from app.features.viral_intake import processor

    code = pathlib.Path(importlib.import_module(processor.__name__).__file__).read_text(encoding="utf-8")

    assert 'clip_start=float(getattr(mat, "clip_start_sec", None) or 0)' in code


# ── nhánh dự phòng: chỗ đã hỏng thật khi chạy thử ────────────────────────────


def test_nhanh_du_phong_fast_trim_cung_phai_ton_trong_moc():
    """
    Hồi quy tìm ra khi chạy thật 2026-09-09: bản vá đầu chỉ sửa lượt mã hoá chính. Lượt đó
    thất bại → rơi xuống `_fast_trim_fallback`, mà nhánh đó KHÔNG có `-ss` → file vẫn là 90
    giây đầu, trong khi hệ thống báo thành công. Sai âm thầm, kiểu tệ nhất.

    Chứng minh bằng ffmpeg thật: video đồng hồ 400s, `clip_start=300`, khung ở giây 2 của
    output hiện số **302**.
    """
    import importlib
    import pathlib

    code = pathlib.Path(importlib.import_module(ReupProcessor.__module__).__file__).read_text(encoding="utf-8")
    # Cắt tới `subprocess.run(trim_cmd` — dòng `return ReupResult` đầu tiên nằm ngay đầu hàm
    # (ca "không cần fallback"), cắt ở đó thì hụt mất phần dựng lệnh.
    block = code.split("def _fast_trim_fallback", 1)[1].split("subprocess.run(trim_cmd", 1)[0]

    assert 'trim_cmd += ["-ss"' in block, "nhánh dự phòng phải seek theo clip_start"
    assert "clip_start > 0 and duration > (clip_start + 2.0)" in block


def test_ca_hai_nhanh_deu_kiem_moc_vuot_do_dai():
    """Gõ 9999 cho video 400 giây thì cả hai nhánh đều phải bỏ qua mốc, không ra file rỗng."""
    import importlib
    import pathlib

    code = pathlib.Path(importlib.import_module(ReupProcessor.__module__).__file__).read_text(encoding="utf-8")

    assert code.count("clip_start > 0 and duration > (clip_start + 2.0)") == 2
