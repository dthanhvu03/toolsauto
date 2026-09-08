"""
ADR-022 — thông báo Telegram cho hai luồng KHÔNG sinh Job.

Trước bản này mọi ``notify_*`` đều gắn với ``Job``; hai luồng làm gần đây (ADR-018 material
về ``READY`` khi không có account, ADR-021 AI viết caption thẳng trên material) không sinh
job nào nên Owner — người đăng tay — không nhận được gì ở đúng hai khoảnh khắc cần biết.

Kiểm ở TẦNG CODE, không mạng: đăng ký một ``StubNotifier`` (kế thừa ``BaseNotifier``) ghi
lại từng lời gọi vào list. Máy này không có token Telegram nên đây là cách duy nhất chứng
minh nội dung tin nhắn.

Hai bất biến quan trọng nhất, mỗi cái một test riêng:
  * tin nhắn đi với ``parse_mode="HTML"`` ⇒ chữ do người khác viết PHẢI được escape;
  * thông báo là việc phụ ⇒ kênh nổ thì hàm ``notify_*`` vẫn không raise (việc chính —
    material đã ``READY``, caption đã commit — không được hỏng theo).
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config
from app.constants import JobStatus, ViralStatus
from app.core.database.models import Account, Job, RuntimeSetting, ViralMaterial, ViralSource
from app.core.media import thumbnail as media_thumb
from app.core.notifier import formatting as nf
from app.core.notifier.service import BaseNotifier, NotifierService
from app.features.viral_intake import processor, reup_processor, reup_variants
from app.features.viral_intake.reup_processor import ReupResult
from app.features.viral_intake.service import ViralService


# ─────────────────────────────── hạ tầng test ───────────────────────────────


class StubNotifier(BaseNotifier):
    """Kênh giả: không gửi đi đâu, chỉ ghi lại (kind, payload) để test đọc."""

    def __init__(self, key: str = "stub:1", explode: bool = False):
        self.calls: list[tuple] = []
        self._key = key
        self._explode = explode

    def channel_key(self) -> str:
        return self._key

    def _record(self, kind: str, *payload):
        self.calls.append((kind, *payload))
        if self._explode:
            raise RuntimeError("kênh Telegram hỏng (giả lập)")
        return True

    def send(self, message: str) -> bool:
        return self._record("text", message)

    def send_photo(self, photo_path: str, caption: str) -> bool:
        return self._record("photo", photo_path, caption)

    def send_with_buttons(self, message: str, buttons: list) -> bool:
        return self._record("buttons", message, buttons)

    def send_video(self, video_path: str, caption: str = "", buttons: Optional[list] = None) -> bool:
        return self._record("video", video_path, caption)

    @property
    def texts(self) -> list[str]:
        """Nội dung mọi tin nhắn, bất kể gửi kiểu gì."""
        return [c[-1] if c[0] in ("text",) else c[2] for c in self.calls]


@pytest.fixture
def stub() -> StubNotifier:
    """Đăng ký stub và luôn dọn sạch ``_channels`` sau test (class attribute dùng chung)."""
    saved = list(NotifierService._channels)
    NotifierService._channels = []
    channel = StubNotifier()
    NotifierService.register(channel)
    try:
        yield channel
    finally:
        NotifierService._channels = saved


@pytest.fixture
def no_channel():
    """Không kênh nào đăng ký — trạng thái mặc định của máy chưa có token."""
    saved = list(NotifierService._channels)
    NotifierService._channels = []
    try:
        yield
    finally:
        NotifierService._channels = saved


class FakeMaterial:
    """Vật thế thân đủ thuộc tính cho hai hàm soạn tin (không cần DB)."""

    def __init__(self, **kw):
        self.id = kw.get("id", 7)
        self.platform = kw.get("platform", "tiktok")
        self.title = kw.get("title", "Video demo")
        self.views = kw.get("views", 0)
        self.ai_caption = kw.get("ai_caption")
        self.ai_caption_error = kw.get("ai_caption_error")
        self._hashtags = kw.get("hashtags") or []

    @property
    def ai_hashtags_list(self) -> list[str]:
        return list(self._hashtags)


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'notify.sqlite'}")
    for model in (Account, ViralMaterial, ViralSource, Job, RuntimeSetting):
        model.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


# ───────────────── (a) material_ready_message — nội dung + escape ─────────────────


def test_a1_ready_co_du_nen_tang_tieu_de_luot_xem_ten_file():
    mat = FakeMaterial(id=68, platform="tiktok", title="Cua rang me sang chảnh", views=1234567)
    msg = nf.material_ready_message(mat, "/data/reup/tiktok/viral_68_abc_reup.mp4")

    assert "Video sẵn sàng đăng tay" in msg
    assert "Material #68" in msg
    assert "tiktok" in msg
    assert "Cua rang me sang chảnh" in msg
    assert "1,234,567" in msg  # có dấu phân cách nghìn
    assert "viral_68_abc_reup.mp4" in msg
    assert "/app/viral" in msg and "Tải file" in msg
    # chỉ tên file, không lộ nguyên đường dẫn ổ đĩa
    assert "/data/reup" not in msg


def test_a2_boc_sach_ai_generate_va_moi_cum_marker():
    title = "[AI_GENERATE] Mèo béo ### ORIGINAL_VIRAL_TITLE: x ### ### BOOST_CONTEXT: bán kem ###"
    msg = nf.material_ready_message(FakeMaterial(title=title))

    assert "[AI_GENERATE]" not in msg
    assert "###" not in msg
    assert "ORIGINAL_VIRAL_TITLE" not in msg and "BOOST_CONTEXT" not in msg
    assert "bán kem" not in msg  # cả nội dung bên trong marker cũng bị bóc
    assert "<i>Mèo béo</i>" in msg


@pytest.mark.parametrize("title", ["", None, "   ", "[AI_GENERATE]", "### X: y ###"])
def test_a3_tieu_de_rong_thi_ghi_khong_co_tieu_de(title):
    assert "(không có tiêu đề)" in nf.material_ready_message(FakeMaterial(title=title))


def test_a4_khong_co_media_path_thi_khong_co_dong_ten_file():
    msg = nf.material_ready_message(FakeMaterial(), None)
    assert "<code>" not in msg
    assert "Tải file" in msg


def test_a5_ky_tu_dac_biet_trong_tieu_de_duoc_escape_theo_parse_mode_HTML():
    """``TelegramClient`` gửi ``parse_mode="HTML"`` ⇒ ``<``/``>``/``&`` phải thành entity.

    Tiêu đề bốc từ TikTok/YouTube là chữ của người lạ; lọt một dấu ``<`` là Telegram trả
    400 và tin nhắn không tới đâu cả.
    """
    mat = FakeMaterial(title='Bí kíp <b>đỉnh</b> & rẻ "số 1"', platform="<x>")
    msg = nf.material_ready_message(mat, "/a/b/vi&deo_reup.mp4")

    assert "&lt;b&gt;" in msg and "&amp; rẻ" in msg
    assert "<b>đỉnh</b>" not in msg
    assert "&lt;x&gt;" in msg
    assert "vi&amp;deo_reup.mp4" in msg
    # các thẻ của chính khuôn tin nhắn thì vẫn còn nguyên
    assert "<b>Video sẵn sàng đăng tay</b>" in msg


def test_a6_parse_mode_that_su_la_html():
    """Chốt cứng giả định của mọi test escape ở trên: client mặc định gửi HTML."""
    import inspect

    from app.core.notifier.telegram_client import TelegramClient

    for name in ("send_message", "send_video"):
        sig = inspect.signature(getattr(TelegramClient, name))
        assert sig.parameters["parse_mode"].default == "HTML", name


# ───────────────── (b) caption_ready_message — 2 nhánh ─────────────────


def test_b1_co_caption_thi_gui_day_du_kem_hashtag_va_nhac_sao_chep():
    mat = FakeMaterial(
        id=68,
        ai_caption="Món cua sang chảnh mà bị chê giống pate mèo 😹",
        hashtags=["#cua", "#anngon", "#xuhuong"],
    )
    msg = nf.caption_ready_message(mat)

    assert "Caption đã viết xong" in msg
    assert "Material #68" in msg
    assert "Món cua sang chảnh mà bị chê giống pate mèo 😹" in msg
    assert "#cua #anngon #xuhuong" in msg  # nối bằng dấu cách
    assert "Sao chép" in msg and "/app/viral" in msg


def test_b2_khong_co_caption_thi_bao_that_bai_kem_ly_do():
    mat = FakeMaterial(id=68, ai_caption=None, ai_caption_error="Key Gemini sai dạng — key thật bắt đầu bằng AIza…")
    msg = nf.caption_ready_message(mat)

    assert "Viết caption thất bại" in msg
    assert "Key Gemini sai dạng" in msg
    assert "Sao chép" not in msg


def test_b3_ly_do_dai_bi_cat_200_ky_tu():
    mat = FakeMaterial(ai_caption="", ai_caption_error="x" * 500)
    msg = nf.caption_ready_message(mat)
    assert "x" * 200 in msg
    assert "x" * 201 not in msg


def test_b4_caption_va_hashtag_cung_duoc_escape():
    mat = FakeMaterial(ai_caption="Giá <300k> & freeship", hashtags=["#a<b>"])
    msg = nf.caption_ready_message(mat)
    assert "&lt;300k&gt; &amp; freeship" in msg
    assert "#a&lt;b&gt;" in msg


def test_b5_loi_co_ky_tu_dac_biet_cung_duoc_escape():
    mat = FakeMaterial(ai_caption=None, ai_caption_error="lỗi ở <module x> & timeout")
    msg = nf.caption_ready_message(mat)
    assert "&lt;module x&gt; &amp; timeout" in msg


# ───────────────── (c) notify_material_ready — video hay chữ ─────────────────


def test_c1_file_nho_thi_gui_video(stub, tmp_path):
    path = tmp_path / "viral_9_reup.mp4"
    path.write_bytes(b"\x00" * 2048)

    NotifierService.notify_material_ready(FakeMaterial(id=9), str(path))

    assert [c[0] for c in stub.calls] == ["video"]
    assert stub.calls[0][1] == str(path)
    assert "Video sẵn sàng đăng tay" in stub.calls[0][2]


def test_c2_file_khong_ton_tai_thi_gui_chu(stub, tmp_path):
    NotifierService.notify_material_ready(FakeMaterial(id=9), str(tmp_path / "khong-co.mp4"))

    assert [c[0] for c in stub.calls] == ["text"]
    assert "khong-co.mp4" in stub.calls[0][1]  # vẫn nói tên file để Owner biết tải cái gì


def test_c3_khong_truyen_media_path_thi_gui_chu(stub):
    NotifierService.notify_material_ready(FakeMaterial(id=9))
    assert [c[0] for c in stub.calls] == ["text"]


def test_c4_file_qua_nguong_telegram_thi_gui_chu(stub, tmp_path, monkeypatch):
    path = tmp_path / "viral_9_reup.mp4"
    path.write_bytes(b"\x00" * 2048)
    monkeypatch.setattr(media_thumb, "telegram_video_within_size_limit", lambda p, *a, **k: False)

    NotifierService.notify_material_ready(FakeMaterial(id=9), str(path))

    assert [c[0] for c in stub.calls] == ["text"]


# ───────────────── (d) kênh nổ ⇒ hàm KHÔNG raise ─────────────────


def test_d1_kenh_no_thi_notify_material_ready_khong_raise(tmp_path):
    saved = list(NotifierService._channels)
    NotifierService._channels = [StubNotifier(explode=True)]
    try:
        path = tmp_path / "viral_1_reup.mp4"
        path.write_bytes(b"\x00" * 16)
        NotifierService.notify_material_ready(FakeMaterial(), str(path))  # không raise
        NotifierService.notify_material_ready(FakeMaterial(), None)
    finally:
        NotifierService._channels = saved


def test_d2_kenh_no_thi_notify_caption_ready_khong_raise():
    saved = list(NotifierService._channels)
    NotifierService._channels = [StubNotifier(explode=True)]
    try:
        NotifierService.notify_caption_ready(FakeMaterial(ai_caption="abc"))
    finally:
        NotifierService._channels = saved


def test_d3_material_hong_khong_lam_do_ham(stub):
    """Vật thiếu thuộc tính (soạn tin sẽ nổ) vẫn không được ném ngược lên việc chính."""

    class Broken:
        @property
        def title(self):
            raise RuntimeError("cột hỏng")

        @property
        def ai_caption(self):
            raise RuntimeError("cột hỏng")

    NotifierService.notify_material_ready(Broken(), None)
    NotifierService.notify_caption_ready(Broken())
    assert stub.calls == []


# ───────────────── (e) đường thật: material đi tới READY ─────────────────


@pytest.fixture
def fake_pipeline(tmp_path, monkeypatch):
    """yt-dlp + ReupProcessor giả (chép từ tests/test_viral_ready_without_account.py)."""
    reup_dir = tmp_path / "reup"
    monkeypatch.setattr(config, "REUP_DIR", reup_dir)
    monkeypatch.setattr(processor, "_get_runtime_int", lambda db, key, fallback: fallback)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    monkeypatch.setattr(ViralService, "ensure_reup_thumbnail", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(reup_variants, "record_reup_variant", lambda **k: None)

    def fake_run(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd]
        if "--dump-single-json" in argv:
            info = {"title": "Mèo béo <đỉnh>", "view_count": 98765, "formats": [{"vcodec": "h264", "ext": "mp4"}]}
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(info), stderr="")
        template = argv[argv.index("-o") + 1]
        out = template.replace("%(id)s", "src").replace("%(ext)s", "mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(b"\x00" * 2048)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(processor.subprocess, "run", fake_run)

    def fake_reup(input_path, platform="unknown", **kwargs):
        out = input_path.replace(".mp4", "_reup.mp4")
        with open(out, "wb") as fh:
            fh.write(b"\x01" * 4096)
        return ReupResult(success=True, output_path=out, metrics={"preset": kwargs.get("preset")})

    monkeypatch.setattr(reup_processor.ReupProcessor, "process", staticmethod(fake_reup))


def test_e1_material_toi_READY_thi_stub_nhan_dung_1_thong_bao(session_factory, fake_pipeline, stub):
    with session_factory() as db:
        mat = ViralMaterial(
            platform="facebook",
            url="https://www.facebook.com/reel/1",
            title="Mèo béo <đỉnh> & rẻ",
            views=0,
            status=ViralStatus.NEW,
        )
        db.add(mat)
        db.commit()
        mid = mat.id

    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        assert db.get(ViralMaterial, mid).status == ViralStatus.READY
        assert db.query(Job).count() == 0

    assert len(stub.calls) == 1, stub.calls
    kind, path, text = stub.calls[0]
    assert kind == "video"  # file giả 4 KB, thừa sức dưới ngưỡng 50 MB
    assert path.endswith("_reup.mp4")
    assert "Video sẵn sàng đăng tay" in text
    assert f"Material #{mid}" in text
    assert "98,765 lượt xem" in text  # views lấy từ preflight yt-dlp
    assert "&lt;đỉnh&gt;" in text  # tiêu đề người lạ viết vẫn được escape


def test_e2_co_account_thi_di_duong_job_cu_khong_ban_thong_bao_READY(session_factory, fake_pipeline, stub, monkeypatch):
    """Đường có account không được đổi: vẫn là ``notify_style_selection`` của job."""
    monkeypatch.setattr(NotifierService, "notify_style_selection", staticmethod(lambda job: None))
    with session_factory() as db:
        db.add(Account(name="fb", platform="facebook", is_active=True, login_status="ACTIVE"))
        db.add(
            ViralMaterial(
                platform="facebook",
                url="https://www.facebook.com/reel/2",
                title="",
                views=0,
                status=ViralStatus.NEW,
            )
        )
        db.commit()
        mid = db.query(ViralMaterial).one().id

    with session_factory() as db:
        ViralService.process_material(db, mid)
        assert db.get(ViralMaterial, mid).status == ViralStatus.DRAFTED
        assert db.query(Job).filter(Job.status == JobStatus.AWAITING_STYLE).count() == 1

    assert stub.calls == []


# ───────────────── (f) caption: nhánh chặn sớm "chưa có key" vẫn báo ─────────────────


@pytest.fixture
def reup_file(tmp_path, monkeypatch):
    reup_dir = tmp_path / "reup" / "tiktok"
    reup_dir.mkdir(parents=True)
    path = reup_dir / "viral_1_demo_reup.mp4"
    path.write_bytes(b"\x00" * 2048)
    monkeypatch.setattr(config, "REUP_DIR", tmp_path / "reup")
    return str(path)


@pytest.fixture
def no_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "NINE_ROUTER_CONFIG_FILE", tmp_path / "khong-co-9router.json")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")


def _material_for_caption(session_factory) -> int:
    with session_factory() as db:
        mat = ViralMaterial(
            platform="tiktok",
            url="https://www.tiktok.com/@demo/video/1",
            title="Video demo",
            views=10,
            status=ViralStatus.READY,
        )
        db.add(mat)
        db.commit()
        return mat.id


def test_f1_chua_co_key_van_phat_thong_bao_caption_loi(session_factory, reup_file, no_key, stub):
    mid = _material_for_caption(session_factory)
    with session_factory() as db:
        ok, reason = ViralService.generate_caption_for_material(db, mid)
        assert ok is False
        assert db.get(ViralMaterial, mid).ai_caption_error  # đã commit trước khi báo

    assert len(stub.calls) == 1
    text = stub.calls[0][-1]
    assert "Viết caption thất bại" in text
    assert f"Material #{mid}" in text


def test_f2_viet_duoc_caption_thi_phat_thong_bao_day_du(session_factory, reup_file, monkeypatch, stub, tmp_path):
    monkeypatch.setattr(config, "NINE_ROUTER_CONFIG_FILE", tmp_path / "khong-co-9router.json")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "AIzaSyFAKE-key-for-test-only")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "AIzaSyFAKE-key-for-test-only")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")

    from app.core.orchestrator import ContentOrchestrator

    monkeypatch.setattr(
        ContentOrchestrator,
        "generate_caption",
        lambda self, *a, **k: {"caption": "Caption <thử> nghiệm", "hashtags": ["#a", "#b"]},
    )

    mid = _material_for_caption(session_factory)
    with session_factory() as db:
        ok, _ = ViralService.generate_caption_for_material(db, mid)
        assert ok is True

    assert len(stub.calls) == 1
    text = stub.calls[0][-1]
    assert "Caption đã viết xong" in text
    assert "&lt;thử&gt;" in text
    assert "#a #b" in text


def test_f3_ai_no_thi_van_phat_thong_bao_loi(session_factory, reup_file, monkeypatch, stub, tmp_path):
    monkeypatch.setattr(config, "NINE_ROUTER_CONFIG_FILE", tmp_path / "khong-co-9router.json")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "AIzaSyFAKE-key-for-test-only")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "AIzaSyFAKE-key-for-test-only")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")

    from app.core.orchestrator import ContentOrchestrator

    def boom(self, *a, **k):
        raise RuntimeError("Whisper chết")

    monkeypatch.setattr(ContentOrchestrator, "generate_caption", boom)

    mid = _material_for_caption(session_factory)
    with session_factory() as db:
        ok, _ = ViralService.generate_caption_for_material(db, mid)
        assert ok is False

    assert len(stub.calls) == 1
    assert "Viết caption thất bại" in stub.calls[0][-1]
    assert "Whisper chết" in stub.calls[0][-1]


# ───────────────── (g) không kênh nào ⇒ gọi vẫn êm ─────────────────


def test_g1_khong_dang_ky_kenh_nao_thi_khong_no(no_channel, tmp_path):
    assert NotifierService._channels == []
    path = tmp_path / "viral_1_reup.mp4"
    path.write_bytes(b"\x00" * 16)

    NotifierService.notify_material_ready(FakeMaterial(), str(path))
    NotifierService.notify_material_ready(FakeMaterial(), None)
    NotifierService.notify_caption_ready(FakeMaterial(ai_caption="abc"))
    NotifierService.notify_caption_ready(FakeMaterial(ai_caption=None, ai_caption_error="x"))


def test_g2_khong_kenh_thi_material_van_ve_READY(session_factory, fake_pipeline, no_channel):
    """Bất biến quan trọng nhất: thiếu token Telegram KHÔNG được chặn xưởng nội dung."""
    with session_factory() as db:
        db.add(
            ViralMaterial(
                platform="facebook",
                url="https://www.facebook.com/reel/3",
                title="",
                views=0,
                status=ViralStatus.NEW,
            )
        )
        db.commit()
        mid = db.query(ViralMaterial).one().id

    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        assert db.get(ViralMaterial, mid).status == ViralStatus.READY
