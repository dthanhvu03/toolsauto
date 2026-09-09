"""
ADR-034 — dán link vào chat Telegram là xong.

Trước bản này `_handle_message` có đúng một dòng `if not text.startswith("/"): return`, tức
**mọi tin không phải lệnh đều bị vứt** — kể cả link Owner gửi vào.

Nguyên tắc như ADR-033: **gọi thật**, không đọc mã nguồn.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.features.telegram_bot.event_router import TelegramEventRouter


class StubClient:
    def __init__(self):
        self.msgs: list[str] = []
        self.markups: list[dict | None] = []
        self.answers: list[str] = []

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)
        self.markups.append(reply_markup)

    def answer_callback_query(self, callback_id, text="", **kw):
        self.answers.append(text)

    @property
    def text(self) -> str:
        return " ".join(self.msgs)


class StubCommands:
    def __init__(self):
        self.calls: list[tuple] = []

    def handle_command(self, cmd, args=None):
        self.calls.append((cmd, args))


@pytest.fixture
def bot(monkeypatch):
    """Router thật + hook giả; DB không cần vì hook bị thay."""
    import app.core.database.core as dbcore

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(dbcore, "SessionLocal", lambda: _FakeSession())
    client, cmds = StubClient(), StubCommands()
    return TelegramEventRouter(client, cmds), client, cmds


def _fake_hooks(monkeypatch, mapping):
    from app.core import feature_hooks

    seen: list[tuple] = []

    def _call(name, *args, **kw):
        seen.append((name, args))
        value = mapping.get(name)
        if callable(value):
            return value(*args, **kw)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(feature_hooks, "call", _call)
    return seen


def _wait_threads(prefix="tg-"):
    for _ in range(60):
        alive = [t for t in threading.enumerate() if t.name.startswith(prefix)]
        if not alive:
            return
        time.sleep(0.05)
    for t in threading.enumerate():
        if t.name.startswith(prefix):
            t.join(timeout=5)


# ── lệnh vẫn đi đường cũ ────────────────────────────────────────────────────


def test_tin_bat_dau_bang_gach_cheo_van_la_lenh(bot):
    router, client, cmds = bot

    router.dispatch({"message": {"text": "/health"}})

    assert cmds.calls == [("health", [])]
    assert client.msgs == []


def test_tin_khong_co_link_thi_im_lang(bot):
    router, client, cmds = bot

    router.dispatch({"message": {"text": "hôm nay trời đẹp quá"}})

    assert client.msgs == [] and cmds.calls == []


# ── link video ──────────────────────────────────────────────────────────────


VIDEO_URL = "https://www.tiktok.com/@thacaukechuyen/video/7679052117176372487"


def test_link_video_tao_material_va_xu_ly_nen(bot, monkeypatch):
    router, client, _ = bot
    seen = _fake_hooks(monkeypatch, {
        "viral.add_link": {"kind": "material", "ok": True, "msg": "Đã thêm #42", "id": 42},
        "viral.process_one": (True, "xong"),
    })

    router.dispatch({"message": {"text": VIDEO_URL}})
    _wait_threads()

    assert [n for n, _ in seen] == ["viral.add_link", "viral.process_one"]
    assert seen[0][1][1] == VIDEO_URL, "phải truyền đúng URL xuống hook"
    assert seen[1][1][1] == 42, "phải xử lý đúng material vừa tạo"
    assert "Đã thêm #42" in client.text and "Đang tải" in client.text


def test_link_video_kem_nut_them_kenh(bot, monkeypatch):
    """Kênh TikTok không liệt kê được bằng @handle thì đây là đường DUY NHẤT thêm nó (ADR-028)."""
    router, client, _ = bot
    _fake_hooks(monkeypatch, {
        "viral.add_link": {"kind": "material", "ok": True, "msg": "Đã thêm #42", "id": 42},
        "viral.process_one": None,
    })

    router.dispatch({"message": {"text": VIDEO_URL}})
    _wait_threads()

    markup = next(m for m in client.markups if m)
    btn = markup["inline_keyboard"][0][0]
    assert btn["callback_data"] == "src:42"
    assert len(btn["callback_data"]) <= 64, "Telegram giới hạn callback_data 64 byte"


def test_boc_duoc_link_lan_trong_chu_khi_bam_chia_se(bot, monkeypatch):
    """App TikTok gửi kèm cả chữ mô tả chứ không phải link trần."""
    router, client, _ = bot
    seen = _fake_hooks(monkeypatch, {
        "viral.add_link": {"kind": "material", "ok": True, "msg": "ok", "id": 1},
        "viral.process_one": None,
    })

    router.dispatch({"message": {"text": f"Xem video của @thacaukechuyen! {VIDEO_URL} thử xem"}})
    _wait_threads()

    assert seen[0][1][1] == VIDEO_URL


@pytest.mark.parametrize("suffix", [".", ",", ")"])
def test_bo_dau_cau_dinh_o_cuoi_link(bot, monkeypatch, suffix):
    router, client, _ = bot
    seen = _fake_hooks(monkeypatch, {
        "viral.add_link": {"kind": "material", "ok": True, "msg": "ok", "id": 1},
        "viral.process_one": None,
    })

    router.dispatch({"message": {"text": f"link đây {VIDEO_URL}{suffix}"}})
    _wait_threads()

    assert seen[0][1][1] == VIDEO_URL


# ── link kênh ───────────────────────────────────────────────────────────────


def test_link_kenh_tao_nguon_va_khong_xu_ly_video(bot, monkeypatch):
    router, client, _ = bot
    seen = _fake_hooks(monkeypatch, {
        "viral.add_link": {"kind": "source", "ok": True, "msg": "Đã thêm nguồn tiktok @abc", "id": 3},
    })

    router.dispatch({"message": {"text": "https://www.tiktok.com/@abc"}})
    _wait_threads()

    assert [n for n, _ in seen] == ["viral.add_link"], "kênh thì không xử lý video nào"
    assert "nguồn tự quét" in client.text
    assert all(m is None for m in client.markups), "kênh thì không cần nút thêm nguồn"


# ── hỏng thì báo, không im lặng, không ném ──────────────────────────────────


def test_hook_tu_choi_thi_bao_ly_do(bot, monkeypatch):
    router, client, _ = bot
    _fake_hooks(monkeypatch, {
        "viral.add_link": {"kind": "material", "ok": False, "msg": "Link đã có trong kho", "id": None},
    })

    router.dispatch({"message": {"text": VIDEO_URL}})
    _wait_threads()

    assert "⚠️" in client.text and "đã có trong kho" in client.text


def test_hook_no_thi_bao_loi_khong_nem(bot, monkeypatch):
    router, client, _ = bot
    _fake_hooks(monkeypatch, {"viral.add_link": RuntimeError("DB chết")})

    router.dispatch({"message": {"text": VIDEO_URL}})
    _wait_threads()

    assert "❌" in client.text and "DB chết" in client.text


def test_xu_ly_nen_no_thi_bao_chu_khong_im(bot, monkeypatch):
    router, client, _ = bot

    def boom(db, material_id):
        raise RuntimeError("ffmpeg chết")

    _fake_hooks(monkeypatch, {
        "viral.add_link": {"kind": "material", "ok": True, "msg": "ok", "id": 9},
        "viral.process_one": boom,
    })

    router.dispatch({"message": {"text": VIDEO_URL}})
    _wait_threads()

    assert "thất bại" in client.text


# ── nút "thêm cả kênh này làm nguồn" ────────────────────────────────────────


def test_nut_them_kenh_goi_dung_hook(bot, monkeypatch):
    router, client, _ = bot
    seen = _fake_hooks(monkeypatch, {
        "viral.add_source_from_material": {"ok": True, "msg": "Đã thêm nguồn tiktok @abc", "id": 5},
    })

    router.dispatch({"callback_query": {"id": "cb1", "data": "src:42", "message": {"message_id": 1}}})

    assert seen[0][0] == "viral.add_source_from_material"
    assert seen[0][1][1] == 42
    assert "✅" in client.answers[0]
    assert "Đã thêm nguồn" in client.text


def test_nut_them_kenh_that_bai_thi_bao_ro(bot, monkeypatch):
    router, client, _ = bot
    _fake_hooks(monkeypatch, {
        "viral.add_source_from_material": {"ok": False, "msg": "Nguồn đã có (#3)"},
    })

    router.dispatch({"callback_query": {"id": "cb1", "data": "src:42", "message": {"message_id": 1}}})

    assert "⚠️" in client.answers[0] and "đã có" in client.text


# ── poller chỉ nghe chat của Owner ──────────────────────────────────────────


class _StubPoller:
    """Dựng lại đúng logic lọc của TelegramPoller mà không cần token."""

    def __init__(self, chat_id, router):
        from app.features.telegram_bot.poller import TelegramPoller

        self.authorized_chat_id = str(chat_id)
        self.event_router = router
        self._process_update = TelegramPoller._process_update.__get__(self)


def test_tin_tu_chat_la_bi_bo_qua():
    seen = []
    poller = _StubPoller("111", type("R", (), {"dispatch": lambda self, u: seen.append(u)})())

    poller._process_update({"message": {"chat": {"id": "999"}, "text": "/health"}})
    poller._process_update({"message": {"chat": {"id": "111"}, "text": "/health"}})

    assert len(seen) == 1


def test_nut_bam_tu_chat_la_cung_bi_bo_qua():
    """
    Hồi quy: bản cũ chỉ lọc `message`, KHÔNG lọc `callback_query`. Từ ADR-034 tin nhắn link
    làm tool tải và xử lý hộ người gửi, nên phải siết cho đều.
    """
    seen = []
    poller = _StubPoller("111", type("R", (), {"dispatch": lambda self, u: seen.append(u)})())

    poller._process_update({"callback_query": {"data": "src:1", "message": {"chat": {"id": "999"}}}})
    poller._process_update({"callback_query": {"data": "src:1", "message": {"chat": {"id": "111"}}}})

    assert len(seen) == 1


# ── bot báo còn sống ────────────────────────────────────────────────────────


def test_bao_bot_san_sang_khong_nem_khi_khong_co_kenh():
    from app.core.notifier.service import NotifierService

    NotifierService.notify_bot_ready()  # không có kênh nào đăng ký ⇒ không được nổ


def test_maintenance_chao_sau_khi_poller_chay():
    """Chào trước khi poller sống thì lời chào nói dối."""
    import pathlib

    from app.features.system_panel.workers import maintenance

    code = pathlib.Path(maintenance.__file__).read_text(encoding="utf-8")

    assert code.index("CURRENT_POLLER.start()") < code.index("notify_bot_ready()")
