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

    assert [c[0] for c in stub.calls] == ["buttons"]  # ADR-042: tin chữ cũng mang nút Đã đăng
    assert "khong-co.mp4" in stub.calls[0][1]  # vẫn nói tên file để Owner biết tải cái gì


def test_c3_khong_truyen_media_path_thi_gui_chu(stub):
    NotifierService.notify_material_ready(FakeMaterial(id=9))
    assert [c[0] for c in stub.calls] == ["buttons"]  # ADR-042: tin chữ cũng mang nút Đã đăng


def test_c4_file_qua_nguong_telegram_thi_gui_chu(stub, tmp_path, monkeypatch):
    path = tmp_path / "viral_9_reup.mp4"
    path.write_bytes(b"\x00" * 2048)
    monkeypatch.setattr(media_thumb, "telegram_video_within_size_limit", lambda p, *a, **k: False)

    NotifierService.notify_material_ready(FakeMaterial(id=9), str(path))

    assert [c[0] for c in stub.calls] == ["buttons"]  # ADR-042: tin chữ cũng mang nút Đã đăng


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


# ───────── (h) ADR-027: một tin gộp — file + caption bấm-là-chép ─────────


@pytest.fixture
def fake_ai(monkeypatch, tmp_path):
    """Có key AI + ContentOrchestrator giả trả caption cố định."""
    monkeypatch.setattr(config, "NINE_ROUTER_CONFIG_FILE", tmp_path / "khong-co-9router.json")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "AIzaSyFAKE-key-for-test-only")
    monkeypatch.setattr(config, "GOOGLE_API_KEY", "AIzaSyFAKE-key-for-test-only")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")

    from app.core.orchestrator import ContentOrchestrator

    state = {"calls": 0, "caption": "Xem tới cuối <mới> tin được!", "hashtags": ["#cauca", "#fish"]}

    def fake(self, *a, **k):
        state["calls"] += 1
        return {"caption": state["caption"], "hashtags": state["hashtags"]}

    monkeypatch.setattr(ContentOrchestrator, "generate_caption", fake)
    return state


def _new_material(session_factory, url="https://www.facebook.com/reel/27"):
    with session_factory() as db:
        mat = ViralMaterial(platform="facebook", url=url, title="Mèo béo", views=0, status=ViralStatus.NEW)
        db.add(mat)
        db.commit()
        return mat.id


# --- soạn tin ---


def test_h1_khoi_code_gom_ca_caption_lan_hashtag_trong_MOT_khoi():
    """Hai khối thì Owner phải chạm hai lần rồi tự ghép — mất đúng cái tiện của ADR-027."""
    mat = FakeMaterial(ai_caption="Câu mở đầu", hashtags=["#a", "#b"])
    block = nf.material_caption_block(mat)

    assert block.count("<code>") == 1 and block.count("</code>") == 1
    body = block.split("<code>")[1].split("</code>")[0]
    assert body == "Câu mở đầu\n\n#a #b"


def test_h2_caption_va_hashtag_do_nguoi_la_viet_van_duoc_escape():
    block = nf.material_caption_block(FakeMaterial(ai_caption="Rẻ <vô địch> & bền", hashtags=["#a&b"]))

    assert "&lt;vô địch&gt;" in block and "&amp;" in block
    assert "<vô địch>" not in block


def test_h3_khong_co_caption_thi_khoi_rong():
    assert nf.material_caption_block(FakeMaterial(ai_caption=None)) == ""
    assert nf.material_caption_block(FakeMaterial(ai_caption="   ")) == ""


def test_h4_tin_ready_co_caption_thi_bo_cau_nhac_mo_web():
    """File đã đính kèm ngay trong tin — nhắc mở web nữa là thừa và sai ý ADR-027."""
    text = nf.material_ready_message(FakeMaterial(ai_caption="Có caption"), "/x/viral_1_reup.mp4")

    assert "chạm vào để chép" in text
    assert "/app/viral" not in text


def test_h5_khong_viet_duoc_caption_thi_neu_ly_do_ngay_trong_tin():
    text = nf.material_ready_message(
        FakeMaterial(ai_caption=None, ai_caption_error="Chưa cấu hình key AI"), "/x/a.mp4"
    )

    assert "Chưa có caption: Chưa cấu hình key AI" in text


def test_h6_with_caption_false_thi_chi_con_phan_dau():
    mat = FakeMaterial(ai_caption="Có caption")

    head = nf.material_ready_message(mat, "/x/a.mp4", with_caption=False)

    assert "<code>a.mp4</code>" in head
    assert "chạm vào để chép" not in head


# --- tách tin khi quá hạn 1024 của caption tin có media ---


def test_h7_tin_dai_thi_tach_hai_tin_va_khoi_caption_khong_bi_cat(stub, tmp_path):
    video = tmp_path / "viral_9_reup.mp4"
    video.write_bytes(b"\x00" * 1024)
    caption = "x" * 1200  # chắc chắn vượt 1024
    mat = FakeMaterial(id=9, ai_caption=caption, hashtags=["#dai"])

    NotifierService.notify_material_ready(mat, str(video))

    assert [c[0] for c in stub.calls] == ["video", "text"]
    assert "chạm vào để chép" not in stub.calls[0][-1]  # video đi với phần đầu ngắn
    block = stub.calls[1][-1]
    assert caption in block and "#dai" in block  # nguyên vẹn, không cụt đuôi


def test_h8_tin_ngan_thi_van_chi_mot_tin_kem_video(stub, tmp_path):
    video = tmp_path / "viral_10_reup.mp4"
    video.write_bytes(b"\x00" * 1024)
    mat = FakeMaterial(id=10, ai_caption="Ngắn gọn", hashtags=["#a"])

    NotifierService.notify_material_ready(mat, str(video))

    assert len(stub.calls) == 1
    kind, path, text = stub.calls[0]
    assert kind == "video" and "chạm vào để chép" in text


# --- đường thật: material đi tới READY ---


def test_h9_bat_o_thi_tu_viet_caption_va_ban_DUNG_MOT_tin_gop(session_factory, fake_pipeline, fake_ai, stub):
    mid = _new_material(session_factory)

    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        mat = db.get(ViralMaterial, mid)
        assert mat.status == ViralStatus.READY
        assert mat.ai_caption == "Xem tới cuối <mới> tin được!"

    assert fake_ai["calls"] == 1
    assert len(stub.calls) == 1, stub.calls  # KHÔNG có tin caption rời của ADR-022
    kind, path, text = stub.calls[0]
    assert kind == "video" and path.endswith("_reup.mp4")
    assert "chạm vào để chép" in text
    assert "&lt;mới&gt;" in text and "#cauca #fish" in text


def test_h10_tat_o_thi_khong_goi_AI_va_tin_nhu_cu(session_factory, fake_pipeline, fake_ai, stub, monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: False)
    mid = _new_material(session_factory, url="https://www.facebook.com/reel/28")

    with session_factory() as db:
        ok, _ = ViralService.process_material(db, mid)
        assert ok
        assert db.get(ViralMaterial, mid).ai_caption is None

    assert fake_ai["calls"] == 0
    assert len(stub.calls) == 1
    assert "/app/viral" in stub.calls[0][-1]  # quay về đúng câu chữ ADR-022


def test_h11_AI_no_thi_van_ban_tin_video_kem_ly_do(session_factory, fake_pipeline, fake_ai, stub, monkeypatch):
    """Caption là việc phụ: material đã READY và file đã có, thông báo không được mất."""
    from app.core.orchestrator import ContentOrchestrator

    def boom(self, *a, **k):
        raise RuntimeError("Whisper chết")

    monkeypatch.setattr(ContentOrchestrator, "generate_caption", boom)
    mid = _new_material(session_factory, url="https://www.facebook.com/reel/29")

    with session_factory() as db:
        ok, _ = ViralService.process_material(db, mid)
        assert ok
        assert db.get(ViralMaterial, mid).status == ViralStatus.READY

    assert len(stub.calls) == 1
    text = stub.calls[0][-1]
    assert "Video sẵn sàng đăng tay" in text
    assert "Chưa có caption" in text


def test_h12_bam_tay_tren_web_van_ban_tin_caption_rieng_nhu_cu(session_factory, reup_file, fake_ai, stub):
    """ADR-021/022 không đổi: `notify` mặc định True nên đường bấm tay giữ nguyên."""
    mid = _material_for_caption(session_factory)

    with session_factory() as db:
        ok, _ = ViralService.generate_caption_for_material(db, mid)
        assert ok

    assert len(stub.calls) == 1
    assert "Caption đã viết xong" in stub.calls[0][-1]


def test_h13_doc_o_cai_dat_hong_thi_video_van_READY_va_van_co_thong_bao(
    session_factory, fake_pipeline, fake_ai, stub, monkeypatch
):
    """
    Hồi quy: bản đầu chỉ bọc try/except quanh lời gọi AI, không bọc lượt đọc ô cài đặt.
    Đọc `runtime_settings` cũng đụng DB — hỏng ở đó là ngoại lệ thoát ra và đánh FAILED
    một video đã xử lý xong, đã commit READY. Suite bắt được ca này ở 3 test khác.
    """
    from app.core import settings as runtime_settings

    def no_table(*a, **k):
        raise RuntimeError("no such table: runtime_settings")

    monkeypatch.setattr(runtime_settings, "get_bool", no_table)
    mid = _new_material(session_factory, url="https://www.facebook.com/reel/30")

    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        assert db.get(ViralMaterial, mid).status == ViralStatus.READY

    assert fake_ai["calls"] == 0
    assert len(stub.calls) == 1
    assert "Video sẵn sàng đăng tay" in stub.calls[0][-1]


# ───────── (i) ADR-030: dòng vị trí trong Drive ─────────

DRIVE_REL = "videos/2026-09/949 - Nay tui đi câu mực nha anh em.mp4"


def test_i1_co_drive_path_thi_tin_bao_VI_TRI_chu_khong_hua_la_link():
    """
    Drive for Desktop chỉ gắn ổ đĩa — tool không biết link drive.google.com. Gọi nó là
    "link" rồi đưa ra chữ không bấm được chính là nhãn nói dối kiểu ADR-023.
    """
    text = nf.material_ready_message(FakeMaterial(id=949), "/x/viral_949_reup.mp4", drive_path=DRIVE_REL)

    assert "Trong Drive" in text and DRIVE_REL in text
    assert "link" not in text.lower()


def test_i2_khong_bat_drive_thi_tin_y_nhu_cu():
    text = nf.material_ready_message(FakeMaterial(id=949), "/x/viral_949_reup.mp4")

    assert "Trong Drive" not in text


def test_i3_duong_dan_drive_cung_duoc_escape():
    text = nf.material_ready_message(FakeMaterial(), "/x/a.mp4", drive_path='videos/2026-09/1 - <a> & "b".mp4')

    assert "&lt;a&gt;" in text and "&amp;" in text


def test_i4_tach_tin_thi_phan_dau_di_kem_video_van_giu_dong_drive(stub, tmp_path):
    """Video quá 50MB không gửi được file — lúc đó dòng vị trí Drive là đường duy nhất
    để Owner lấy video, càng không được rơi mất khi tin bị tách."""
    video = tmp_path / "viral_9_reup.mp4"
    video.write_bytes(b"\x00" * 1024)
    mat = FakeMaterial(id=9, ai_caption="x" * 1200, hashtags=["#dai"])

    NotifierService.notify_material_ready(mat, str(video), drive_path=DRIVE_REL)

    assert [c[0] for c in stub.calls] == ["video", "text"]
    assert DRIVE_REL in stub.calls[0][-1]


def test_i5_khong_gui_duoc_video_thi_tin_chu_van_co_dong_drive(stub):
    NotifierService.notify_material_ready(FakeMaterial(id=9), None, drive_path=DRIVE_REL)

    assert len(stub.calls) == 1 and stub.calls[0][0] == "buttons"  # ADR-042: kèm nút Đã đăng
    assert DRIVE_REL in stub.calls[0][1]


# ───────── (j) ADR-029 mục 6: hợp đồng "không bao giờ raise" của caption ─────────


def test_j1_db_hong_luc_chuan_bi_thi_tra_False_chu_khong_nem(session_factory, monkeypatch):
    """
    Hồi quy: `db.query`, `find_reup_path`, `ai_provider_ready` từng nằm NGOÀI mọi try, trong
    khi docstring hứa "KHÔNG BAO GIỜ raise". Chưa nổ ra hậu quả chỉ vì cả hai người gọi đều
    tự bọc — tức đúng nhờ may mắn của người gọi, không nhờ thiết kế.
    """
    monkeypatch.setattr(
        ViralService, "find_reup_path",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("đĩa hỏng"))),
    )
    mid = _material_for_caption(session_factory)

    with session_factory() as db:
        ok, msg = ViralService.generate_caption_for_material(db, mid)

    assert ok is False
    assert "chuẩn bị viết caption" in msg and "đĩa hỏng" in msg


def test_j2_session_van_dung_duoc_sau_khi_hong(session_factory, monkeypatch):
    """Lỗi DB làm session hỏng; không rollback thì vòng lặp sau của processor hỏng theo."""
    goi = {"rollback": 0}
    mid = _material_for_caption(session_factory)

    monkeypatch.setattr(
        ViralService, "find_reup_path",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nổ"))),
    )

    with session_factory() as db:
        real_rollback = db.rollback
        monkeypatch.setattr(db, "rollback", lambda: (goi.__setitem__("rollback", goi["rollback"] + 1), real_rollback())[1])
        ViralService.generate_caption_for_material(db, mid)
        # session còn dùng được: truy vấn tiếp không nổ
        assert db.get(ViralMaterial, mid) is not None

    assert goi["rollback"] == 1


# ───────── (k) ADR-035: tin phải nói video dài bao nhiêu, cắt từ đâu ─────────


def test_k1_dong_thoi_luong_co_du_dai_moc_cat_va_do_dai_goc():
    """Owner nhận video mà không biết dài bao nhiêu thì phải mở ra xem — đúng việc đã bỏ công
    loại bỏ ở ADR-032."""
    mat = FakeMaterial(id=976)
    mat.clip_start_sec = 332

    text = nf.material_ready_message(mat, "/x/a.mp4", duration=90, source_duration=573)

    assert "⏱ Dài 1:30 · cắt từ 5:32 (gốc 9:33)" in text


def test_k2_khong_co_moc_thi_ghi_tu_dau():
    mat = FakeMaterial(id=976)
    mat.clip_start_sec = None

    text = nf.material_ready_message(mat, "/x/a.mp4", duration=90, source_duration=573)

    assert "cắt từ đầu (gốc 9:33)" in text


def test_k3_khong_biet_do_dai_goc_thi_KHONG_doan_bua():
    """File gốc đã dọn thì bỏ hẳn phần trong ngoặc, không hiện số sai."""
    mat = FakeMaterial(id=976)
    mat.clip_start_sec = None

    text = nf.material_ready_message(mat, "/x/a.mp4", duration=90)

    assert "⏱ Dài 1:30 · cắt từ đầu" in text
    assert "gốc" not in text


def test_k4_khong_do_duoc_thi_bo_han_dong_do():
    mat = FakeMaterial(id=976)

    text = nf.material_ready_message(mat, "/x/a.mp4", duration=0)

    assert "⏱" not in text


@pytest.mark.parametrize("giay,mong_doi", [(0, "0:00"), (9, "0:09"), (90, "1:30"), (573, "9:33"), (3661, "61:01")])
def test_k5_dinh_dang_phut_giay(giay, mong_doi):
    assert nf._mmss(giay) == mong_doi


def test_k6_notify_do_do_dai_va_truyen_vao_tin(stub, tmp_path, monkeypatch):
    """Đo ở NotifierService, không ở formatting — formatting phải giữ thuần."""
    video = tmp_path / "viral_9_reup.mp4"
    video.write_bytes(b"\x00" * 1024)
    monkeypatch.setattr(
        "app.core.media.thumbnail.media_info",
        lambda p: {"duration": 90.0, "width": 576, "height": 1024},
    )

    NotifierService.notify_material_ready(FakeMaterial(id=9), str(video), source_duration=573)

    assert "⏱ Dài 1:30" in stub.calls[0][-1] and "(gốc 9:33)" in stub.calls[0][-1]


def test_k7_do_do_dai_hong_thi_van_gui_tin(stub, tmp_path, monkeypatch):
    video = tmp_path / "viral_9_reup.mp4"
    video.write_bytes(b"\x00" * 1024)

    def boom(_p):
        raise RuntimeError("ffprobe chết")

    monkeypatch.setattr("app.core.media.thumbnail.media_info", boom)

    NotifierService.notify_material_ready(FakeMaterial(id=9), str(video))

    assert len(stub.calls) == 1
    assert "Video sẵn sàng đăng tay" in stub.calls[0][-1]
