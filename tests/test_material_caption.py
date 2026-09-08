"""
ADR-021 — AI viết caption cho material READY (không cần account, không cần Job).

Kiểm hai thứ ở TẦNG CODE, không mạng, không ffmpeg, không Whisper:

  1. ``ai_provider_ready()`` — chỉ soi hình dạng key / cờ khai báo, KHÔNG gọi mạng;
  2. ``ViralService.generate_caption_for_material()`` — thứ tự chặn (file _reup → key AI →
     mới chạy AI), ghi/xoá ``ai_caption_error``, và KHÔNG BAO GIỜ raise.

Chỗ đắt nhất được canh bằng cách monkeypatch ``ContentOrchestrator.generate_caption``
thành hàm **nổ nếu bị gọi**: đó là bằng chứng "chặn sớm" thật, không phải suy đoán.

Chạy trên SQLite tạm như tests/test_source_fanout.py.
"""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config
from app.constants import ViralStatus
from app.core.database.models import Account, Job, RuntimeSetting, ViralMaterial, ViralSource
from app.features.viral_intake import service as service_mod
from app.features.viral_intake.service import ViralService, ai_provider_ready


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'caption.sqlite'}")
    for model in (Account, ViralMaterial, ViralSource, Job, RuntimeSetting):
        model.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def no_router(tmp_path, monkeypatch):
    """9Router coi như TẮT: trỏ config file sang đường dẫn không tồn tại (test không phụ thuộc máy)."""
    monkeypatch.setattr(config, "NINE_ROUTER_CONFIG_FILE", tmp_path / "khong-co-9router.json")


@pytest.fixture
def reup_file(tmp_path, monkeypatch):
    """Tạo file ``_reup`` thật trên đĩa tạm cho material #1 → ``find_reup_path`` tìm thấy."""
    reup_dir = tmp_path / "reup" / "tiktok"
    reup_dir.mkdir(parents=True)
    path = reup_dir / "viral_1_demo_reup.mp4"
    path.write_bytes(b"\x00" * 2048)
    monkeypatch.setattr(config, "REUP_DIR", tmp_path / "reup")
    return str(path)


@pytest.fixture
def with_key(monkeypatch, no_router):
    """Giả lập máy CÓ key Gemini đúng dạng."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "AIzaSyFAKE-key-for-test-only")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "AIzaSyFAKE-key-for-test-only")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")


@pytest.fixture
def no_key(monkeypatch, no_router):
    """Giả lập máy CHƯA có key nào."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")


def _make_material(session_factory, *, title: str = "Video demo", status: str = "READY") -> int:
    with session_factory() as db:
        mat = ViralMaterial(
            platform="tiktok",
            url="https://www.tiktok.com/@demo/video/1",
            title=title,
            views=1000,
            status=status,
        )
        db.add(mat)
        db.commit()
        return mat.id


def _patch_orchestrator(monkeypatch, fn):
    """Thay ``ContentOrchestrator.generate_caption`` — import trong hàm nên phải vá tận module gốc."""
    from app.core import orchestrator as orch_mod

    monkeypatch.setattr(orch_mod.ContentOrchestrator, "generate_caption", fn)


def _explode(*a, **k):  # pragma: no cover - chỉ chạy khi test THẤT BẠI
    raise AssertionError("ContentOrchestrator.generate_caption KHÔNG được phép chạy ở nhánh này")


# ─────────────────────────── (a) ai_provider_ready — 4 nhánh ───────────────────────────


def test_a1_gemini_dung_dang_aiza_thi_ok(monkeypatch, no_router):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ0123456")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ0123456")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")

    assert ai_provider_ready() == (True, "")


def test_a2_key_gemini_sai_dang_bao_ro_aiza(monkeypatch, no_router):
    """Đúng tình trạng máy Owner: `.env` có GOOGLE_API_KEY dạng `AQ.Ab…` (access token, không phải API key)."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "AQ.Ab8RN6JkhoAnh_khong_phai_api_key")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "AQ.Ab8RN6JkhoAnh_khong_phai_api_key")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")

    ok, reason = ai_provider_ready()
    assert ok is False
    assert "sai dạng" in reason
    assert "AIza" in reason


def test_a3_chi_co_openrouter_van_ok(monkeypatch, no_router):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-v1-fake")

    assert ai_provider_ready() == (True, "")


def test_a4_khong_co_gi_thi_huong_dan_dat_key(no_key):
    ok, reason = ai_provider_ready()
    assert ok is False
    assert "Chưa cấu hình key AI" in reason
    assert "GEMINI_API_KEY" in reason
    assert "manage.py ai check" in reason


def test_a5_9router_bat_thi_ok_du_khong_co_key(tmp_path, monkeypatch):
    cfg = tmp_path / "9router_config.json"
    cfg.write_text(json.dumps({"enabled": True, "default_model": "gemini-3.5-flash"}), encoding="utf-8")
    monkeypatch.setattr(config, "NINE_ROUTER_CONFIG_FILE", cfg)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")

    assert ai_provider_ready() == (True, "")


# ─────────────────────── (b) không có file reup ⇒ không chạy AI ───────────────────────


def test_b_khong_co_file_reup_thi_khong_dung_toi_ai(session_factory, tmp_path, monkeypatch, with_key):
    # ``find_reup_path`` có nhánh dò cuối cùng đi qua ``SessionLocal()`` TOÀN CỤC (Postgres thật),
    # không phải session SQLite của test — nên chỉ đổi REUP_DIR là chưa đủ để giả lập "không có file".
    monkeypatch.setattr(config, "REUP_DIR", tmp_path / "reup-rong")
    monkeypatch.setattr(ViralService, "find_reup_path", staticmethod(lambda *a, **k: None))
    _patch_orchestrator(monkeypatch, _explode)
    mid = _make_material(session_factory)

    with session_factory() as db:
        ok, msg = ViralService.generate_caption_for_material(db, mid)

    assert ok is False
    assert "_reup" in msg
    with session_factory() as db:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == mid).first()
        # Chưa chạy AI lần nào ⇒ không ghi dấu vết
        assert mat.ai_caption_at is None
        assert mat.ai_caption_error is None


def test_b2_material_khong_ton_tai(session_factory, with_key):
    with session_factory() as db:
        ok, msg = ViralService.generate_caption_for_material(db, 4242)
    assert ok is False
    assert "Không tìm thấy material #4242" in msg


# ──────────────────── (c) chưa có key ⇒ chặn NGAY, ghi lỗi vào DB ────────────────────


def test_c_chua_co_key_thi_chan_som_va_ghi_loi(session_factory, reup_file, monkeypatch, no_key):
    _patch_orchestrator(monkeypatch, _explode)
    mid = _make_material(session_factory)
    assert mid == 1  # reup_file đặt tên theo material #1

    with session_factory() as db:
        ok, msg = ViralService.generate_caption_for_material(db, mid)

    assert ok is False
    assert "Chưa cấu hình key AI" in msg
    with session_factory() as db:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == mid).first()
        assert "Chưa cấu hình key AI" in (mat.ai_caption_error or "")
        assert mat.ai_caption_at is not None
        assert mat.ai_caption is None


# ─────────────────────────── (d) đường thành công ───────────────────────────


def test_d_co_key_va_ai_tra_caption_thi_luu_du(session_factory, reup_file, monkeypatch, with_key):
    seen: dict = {}

    def fake_caption(self, video_path, style="general", context="", **kwargs):
        seen["video_path"] = video_path
        seen["style"] = style
        seen["context"] = context
        return {
            "caption": "Mẹo hay cho da khô mùa đông",
            "hashtags": ["#skincare", "#dakho"],
            "keywords": ["skincare"],
            "affiliate_keyword": "kem dưỡng",
        }

    _patch_orchestrator(monkeypatch, fake_caption)
    mid = _make_material(session_factory)

    with session_factory() as db:
        ok, msg = ViralService.generate_caption_for_material(db, mid)

    assert ok is True
    assert f"#{mid}" in msg
    assert seen["video_path"] == reup_file
    assert seen["style"] == "short"  # không có setting ⇒ mặc định

    with session_factory() as db:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == mid).first()
        assert mat.ai_caption == "Mẹo hay cho da khô mùa đông"
        assert json.loads(mat.ai_hashtags) == ["#skincare", "#dakho"]
        assert mat.ai_hashtags_list == ["#skincare", "#dakho"]
        assert mat.ai_caption_at is not None
        assert mat.ai_caption_error is None


def test_d2_style_truyen_tay_duoc_ton_trong(session_factory, reup_file, monkeypatch, with_key):
    seen: dict = {}

    def fake_caption(self, video_path, style="general", context="", **kwargs):
        seen["style"] = style
        return {"caption": "ok", "hashtags": []}

    _patch_orchestrator(monkeypatch, fake_caption)
    mid = _make_material(session_factory)

    with session_factory() as db:
        ViralService.generate_caption_for_material(db, mid, style="sales")

    assert seen["style"] == "sales"


def test_d3_viet_lai_thi_xoa_loi_cu(session_factory, reup_file, monkeypatch, with_key):
    """Lần trước lỗi → lần này thành công phải XOÁ ``ai_caption_error``, không để lỗi cũ nằm lại."""
    _patch_orchestrator(
        monkeypatch, lambda self, p, style="general", context="", **k: {"caption": "xong", "hashtags": []}
    )
    mid = _make_material(session_factory)
    with session_factory() as db:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == mid).first()
        mat.ai_caption_error = "lỗi cũ từ lần trước"
        db.commit()

    with session_factory() as db:
        ok, _ = ViralService.generate_caption_for_material(db, mid)

    assert ok is True
    with session_factory() as db:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == mid).first()
        assert mat.ai_caption_error is None


# ─────────────────────────── (e) caption rỗng ⇒ ghi lỗi ───────────────────────────


def test_e_caption_rong_thi_ghi_loi(session_factory, reup_file, monkeypatch, with_key):
    _patch_orchestrator(
        monkeypatch, lambda self, p, style="general", context="", **k: {"caption": "   ", "hashtags": []}
    )
    mid = _make_material(session_factory)

    with session_factory() as db:
        ok, msg = ViralService.generate_caption_for_material(db, mid)

    assert ok is False
    assert "AI không trả về caption" in msg
    with session_factory() as db:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == mid).first()
        assert "AI không trả về caption" in (mat.ai_caption_error or "")
        assert mat.ai_caption is None
        assert mat.ai_caption_at is not None


# ─────────────────────────── (f) AI nổ ⇒ không raise ───────────────────────────


def test_f_ai_nem_loi_thi_khong_raise_va_ghi_loi(session_factory, reup_file, monkeypatch, with_key):
    def boom(self, video_path, style="general", context="", **kwargs):
        raise RuntimeError("Gemini 401 UNAUTHENTICATED")

    _patch_orchestrator(monkeypatch, boom)
    mid = _make_material(session_factory)

    with session_factory() as db:
        ok, msg = ViralService.generate_caption_for_material(db, mid)  # KHÔNG được raise

    assert ok is False
    assert "401" in msg
    with session_factory() as db:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == mid).first()
        assert "401" in (mat.ai_caption_error or "")
        assert len(mat.ai_caption_error) <= 300


def test_f2_loi_dai_bi_cat_300_ky_tu(session_factory, reup_file, monkeypatch, with_key):
    def boom(self, video_path, style="general", context="", **kwargs):
        raise RuntimeError("X" * 5000)

    _patch_orchestrator(monkeypatch, boom)
    mid = _make_material(session_factory)

    with session_factory() as db:
        ViralService.generate_caption_for_material(db, mid)

    with session_factory() as db:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == mid).first()
        assert len(mat.ai_caption_error) == 300


# ─────────────────────── (g) ai_hashtags_list chịu được JSON hỏng ───────────────────────


@pytest.mark.parametrize(
    "raw, expect",
    [
        (None, []),
        ("", []),
        ("khong-phai-json", []),
        ('{"a": 1}', []),  # JSON hợp lệ nhưng không phải list
        ('["#a", "  ", "#b"]', ["#a", "#b"]),
    ],
)
def test_g_ai_hashtags_list_json_hong_ra_list_rong(raw, expect):
    mat = ViralMaterial(ai_hashtags=raw)
    assert mat.ai_hashtags_list == expect


# ─────────────────── (h) context bóc sạch [AI_GENERATE] và ### … ### ───────────────────


def test_h_context_boc_sach_marker(session_factory, reup_file, monkeypatch, with_key):
    seen: dict = {}

    def fake_caption(self, video_path, style="general", context="", **kwargs):
        seen["context"] = context
        return {"caption": "ok", "hashtags": []}

    _patch_orchestrator(monkeypatch, fake_caption)
    title = (
        "[AI_GENERATE] ### ORIGINAL_VIRAL_TITLE: Cách chọn kem chống nắng ### "
        "Review nhanh 30 giây ### BOOST_CONTEXT: Page làm đẹp, top post kem dưỡng ###"
    )
    mid = _make_material(session_factory, title=title)

    with session_factory() as db:
        ViralService.generate_caption_for_material(db, mid)

    assert seen["context"] == "Review nhanh 30 giây"
    assert "[AI_GENERATE]" not in seen["context"]
    assert "###" not in seen["context"]
    assert "BOOST_CONTEXT" not in seen["context"]


def test_h2_title_thuong_giu_nguyen(session_factory, reup_file, monkeypatch, with_key):
    seen: dict = {}
    _patch_orchestrator(
        monkeypatch,
        lambda self, p, style="general", context="", **k: (
            seen.update(context=context) or {"caption": "ok", "hashtags": []}
        ),
    )
    mid = _make_material(session_factory, title="Mẹo rửa mặt đúng cách")

    with session_factory() as db:
        ViralService.generate_caption_for_material(db, mid)

    assert seen["context"] == "Mẹo rửa mặt đúng cách"


def test_h3_status_khong_chan_caption(session_factory, reup_file, monkeypatch, with_key):
    """ADR-021 chỉ đòi có file ``_reup`` — DRAFTED cũng viết được, không khoá riêng READY."""
    _patch_orchestrator(
        monkeypatch, lambda self, p, style="general", context="", **k: {"caption": "ok", "hashtags": []}
    )
    mid = _make_material(session_factory, status=ViralStatus.DRAFTED)

    with session_factory() as db:
        ok, _ = ViralService.generate_caption_for_material(db, mid)

    assert ok is True


def test_h4_module_khong_goi_mang_khi_kiem_key(no_key):
    """``ai_provider_ready`` phải nhanh: chặn mọi socket, nếu nó gọi mạng thì test đỏ."""
    import socket

    original = socket.socket.connect

    def deny(self, *a, **k):  # pragma: no cover - chỉ chạy khi test THẤT BẠI
        raise AssertionError("ai_provider_ready() KHÔNG được gọi mạng")

    socket.socket.connect = deny
    try:
        ok, _ = ai_provider_ready()
    finally:
        socket.socket.connect = original
    assert ok is False


def test_h5_file_reup_duoc_tim_dung(session_factory, reup_file):
    assert os.path.isfile(reup_file)
    assert ViralService.find_reup_path(1, "tiktok") == reup_file
