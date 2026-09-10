"""
Bảy lỗi do `/code-review` bắt trên dải ADR-025→037 (2026-09-10).

Lỗi nghiêm trọng nhất — thiếu `force` ⇒ chốt `skip_existing` trả lại file cũ — **vô hiệu hoàn
toàn** tính năng chọn đoạn cắt của ADR-031/036. Mọi lượt chạy thật trước đó không bắt được vì
chúng đều tự truyền `force=True`. Chứng minh bằng video có đồng hồ: đặt mốc 120 mà khung ở
giây 2 của kết quả vẫn hiện "2"; sau khi vá hiện "122".
"""
from __future__ import annotations

import importlib
import pathlib

import pytest


def _code(module_path: str) -> str:
    return pathlib.Path(importlib.import_module(module_path).__file__).read_text(encoding="utf-8")


# ── 1. force: nếu không, mốc cắt bị nuốt trong im lặng ──────────────────────


def test_duong_chay_chinh_phai_truyen_force_khi_xu_ly_lai():
    code = _code("app.features.viral_intake.processor")
    goi = code.index("reup_result = ReupProcessor.process(")
    khoi = code[goi:goi + 1400]

    assert "force=bool(" in khoi, "thiếu force ⇒ skip_existing trả lại _reup cũ, mốc cắt vô hiệu"
    assert "ViralStatus.REUP" in khoi and "clip_start_sec" in khoi


def test_chot_skip_existing_van_con_de_luot_quet_thuong_khong_lam_lai():
    """Không xoá chốt — nó vẫn đúng cho lượt quét thường; chỉ lượt CỐ Ý làm lại mới bỏ qua."""
    code = _code("app.features.viral_intake.reup_processor")

    assert "if not force and os.path.exists(output_path)" in code


# ── 2. bỏ qua kết quả xử lý ⇒ Owner chờ mãi trong im lặng ───────────────────


def test_xu_ly_nen_phai_bao_khi_bi_TU_CHOI_chu_khong_chi_khi_nem_loi():
    code = _code("app.features.telegram_bot.event_router")
    khoi = code.split("def _process_material_async", 1)[1].split("threading.Thread", 1)[0]

    assert "if not ok:" in khoi, "process_material từ chối bằng giá trị trả về, không bằng ngoại lệ"
    assert "Không xử lý được" in khoi


# ── 3. duration nhận nhầm chiều cao ─────────────────────────────────────────


def test_ffprobe_thieu_duration_thi_KHONG_lay_chieu_cao_lam_thoi_luong(monkeypatch):
    """
    ffprobe in stream trước, format sau. Container thiếu `duration` ⇒ chỉ còn [w, h];
    lấy phần tử cuối là gán CHIỀU CAO làm thời lượng — clip 90 giây báo "Dài 17:04".
    """
    import subprocess

    from app.core.media import thumbnail

    monkeypatch.setattr(thumbnail.os.path, "isfile", lambda p: True)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: type("R", (), {"stdout": "576\n1024\nN/A\n"})(),
    )

    info = thumbnail.media_info("/x/a.mp4")

    assert info["duration"] == 0.0, "không đo được thì phải là 0, không phải chiều cao"
    assert (info["width"], info["height"]) == (576, 1024)


def test_du_ba_so_thi_doc_dung(monkeypatch):
    import subprocess

    from app.core.media import thumbnail

    monkeypatch.setattr(thumbnail.os.path, "isfile", lambda p: True)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: type("R", (), {"stdout": "576\n1024\n90.5\n"})(),
    )

    assert thumbnail.media_info("/x/a.mp4") == {"duration": 90.5, "width": 576, "height": 1024}


# ── 4. bấm khung hình không được xoá độ dài đã đặt ──────────────────────────


@pytest.fixture
def session_factory(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'r.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


def _material(session_factory, **over):
    from app.constants import ViralStatus
    from app.core.database.models import ViralMaterial

    with session_factory() as db:
        base = dict(platform="tiktok", url="https://t/1", title="x", views=1, status=ViralStatus.READY)
        base.update(over)
        mat = ViralMaterial(**base)
        db.add(mat)
        db.commit()
        return mat.id


def test_khong_truyen_do_dai_thi_GIU_NGUYEN(session_factory):
    """Nút khung hình trong Telegram chỉ gửi mốc — không được vì thế mà xoá độ dài đã đặt."""
    from app.core.database.models import ViralMaterial
    from app.features.viral_intake.service import ViralService

    mid = _material(session_factory, clip_start_sec=100, clip_length_sec=50)
    with session_factory() as db:
        ok, _ = ViralService.set_clip_start(db, mid, 332, None)

        assert ok
        mat = db.get(ViralMaterial, mid)
        assert (mat.clip_start_sec, mat.clip_length_sec) == (332, 50)


def test_truyen_chuoi_rong_thi_XOA(session_factory):
    """Owner xoá trắng ô trên web ⇒ về dùng số chung. Phải phân biệt với "không truyền"."""
    from app.core.database.models import ViralMaterial
    from app.features.viral_intake.service import ViralService

    mid = _material(session_factory, clip_start_sec=100, clip_length_sec=50)
    with session_factory() as db:
        ok, _ = ViralService.set_clip_start(db, mid, 332, "")

        assert ok
        assert db.get(ViralMaterial, mid).clip_length_sec is None


def test_route_truyen_chuoi_rong_nguyen_ven():
    code = _code("app.features.viral_intake.router")

    assert "clip_length_sec or None" not in code


# ── 5. file tạm không được nhận nhầm là bản gốc ─────────────────────────────


@pytest.mark.parametrize("ten", [
    "viral_7_abc_reup.mp4",
    "viral_7_abc_reup.tmp.mp4",
    "viral_7_abc.with_intro.tmp.mp4",
    "viral_7_abc_reup.mp4.reprocess-src.mp4",
])
def test_file_tam_va_ban_da_cat_khong_duoc_coi_la_goc(tmp_path, monkeypatch, ten):
    """
    Sau một lần crash, file tạm còn nằm đó với mtime mới nhất nên THẮNG ở bước sort — bản
    "gốc" đem đi cắt lại hoá ra là bản đã cắt, mà không có lỗi nào báo.
    """
    import app.config as config

    from app.features.viral_intake.service import ViralService

    monkeypatch.setattr(config, "REUP_DIR", tmp_path)
    d = tmp_path / "tiktok"
    d.mkdir()
    (d / ten).write_bytes(b"x" * 100)

    assert ViralService.find_source_path(7, "tiktok") is None


def test_ban_goc_that_van_tim_duoc(tmp_path, monkeypatch):
    import app.config as config

    from app.features.viral_intake.service import ViralService

    monkeypatch.setattr(config, "REUP_DIR", tmp_path)
    d = tmp_path / "tiktok"
    d.mkdir()
    (d / "viral_7_abc.mp4").write_bytes(b"x" * 100)
    (d / "viral_7_abc_reup.tmp.mp4").write_bytes(b"y" * 100)

    found = ViralService.find_source_path(7, "tiktok")

    assert found and found.endswith("viral_7_abc.mp4")


# ── 6. gửi lại video không được chạy trên luồng poller ──────────────────────


def test_gui_lai_chay_nen_giong_quet():
    """Gửi lại phải TẢI LÊN cả video — chạy thẳng thì callback hết hạn, bot đứng im."""
    code = _code("app.features.telegram_bot.event_router")

    assert 'if action in ("scan", "gui"):' in code
    assert "tg-{action}-{target_id}" in code


# ── 7. tin dài mà không có caption vẫn phải tách ────────────────────────────


def test_tieu_de_dai_khong_caption_cung_phai_tach_tin():
    """
    Chốt cũ chỉ bật khi CÓ caption AI. Riêng tiêu đề TikTok dài cũng đủ vượt 1024 ⇒
    `send_video` cắt giữa thẻ <i> ⇒ Telegram trả 400 ⇒ mất luôn cả tin lẫn video.
    """
    code = _code("app.core.notifier.service")

    assert "if len(msg) > cls.TELEGRAM_MEDIA_CAPTION_LIMIT:" in code
    assert "if block and len(msg) >" not in code


def test_tin_dai_khong_caption_that_su_vuot_nguong():
    from types import SimpleNamespace

    from app.core.notifier import formatting as nf

    mat = SimpleNamespace(
        id=9, platform="tiktok", title="X" * 1200, views=1,
        ai_caption=None, ai_hashtags_list=[], ai_caption_error=None, clip_start_sec=None,
    )

    assert len(nf.material_ready_message(mat, "/x/a.mp4")) > 1024
