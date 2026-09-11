"""ADR-042 — nút Đã đăng / Chưa đăng và lệnh /dadang trên Telegram. Gọi thật router + handler."""
from __future__ import annotations

import pytest

from app.features.telegram_bot.command_handler import TelegramCommandHandler
from app.features.telegram_bot.event_router import TelegramEventRouter


class StubClient:
    def __init__(self):
        self.msgs, self.markups, self.answers = [], [], []

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)
        self.markups.append(reply_markup)

    def answer_callback_query(self, callback_id, text="", **kw):
        self.answers.append(text)

    @property
    def text(self):
        return " ".join(self.msgs)

    def buttons(self):
        return [b for m in self.markups if m for row in m["inline_keyboard"] for b in row]


@pytest.fixture
def fake_db(monkeypatch):
    import app.core.database.core as dbcore

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(dbcore, "SessionLocal", lambda: _S())


def _hooks(monkeypatch, mapping):
    from app.core import feature_hooks

    seen = []

    def _call(name, *args, **kw):
        seen.append((name, args))
        v = mapping.get(name)
        return v(*args, **kw) if callable(v) else v

    monkeypatch.setattr(feature_hooks, "call", _call)
    return seen


@pytest.fixture
def router(fake_db):
    c = StubClient()
    return TelegramEventRouter(c, TelegramCommandHandler(c)), c


@pytest.fixture
def bot(fake_db):
    c = StubClient()
    return TelegramCommandHandler(c), c


def _cb(data):
    return {"callback_query": {"id": "c", "data": data, "message": {"message_id": 1}}}


MAT = {"id": 976, "platform": "tiktok", "title": "x", "views": 1, "url": "u", "clip_start_sec": None,
       "clip_length_sec": None, "parent_material_id": None, "part_index": None, "part_total": None, "posted_at": None}


def test_bam_da_dang_goi_hook_va_tra_nut_lui(router, monkeypatch):
    r, c = router
    seen = _hooks(monkeypatch, {"viral.mark_posted": {"ok": True, "msg": "✅ #976 đã đăng — file máy: tiktok/da-dang/x.mp4"}})

    r.dispatch(_cb("dadang:976"))

    assert seen == [("viral.mark_posted", (seen[0][1][0], 976))]
    assert "da-dang" in c.text
    assert [b["callback_data"] for b in c.buttons()] == ["chuadang:976"], "bấm nhầm phải lùi được ngay tại chỗ"


def test_bam_chua_dang_tra_nut_nguoc_lai(router, monkeypatch):
    r, c = router
    _hooks(monkeypatch, {"viral.unmark_posted": {"ok": True, "msg": "↩️ #976 về lại"}})

    r.dispatch(_cb("chuadang:976"))

    assert [b["callback_data"] for b in c.buttons()] == ["dadang:976"]


def test_tu_choi_thi_bao_ly_do_khong_co_nut(router, monkeypatch):
    r, c = router
    _hooks(monkeypatch, {"viral.mark_posted": {"ok": False, "msg": "#976 đang ở trạng thái NEW"}})

    r.dispatch(_cb("dadang:976"))

    assert "trạng thái NEW" in c.text and not c.buttons()
    assert c.answers[0].startswith("⚠️")


def test_sansang_co_nut_da_dang(bot, monkeypatch):
    h, c = bot
    _hooks(monkeypatch, {"viral.list_materials": [MAT]})

    h.handle_command("sansang")

    assert "dadang:976" in [b["callback_data"] for b in c.buttons()]


def test_dadang_liet_ke_kem_gio_va_nut_chua_dang(bot, monkeypatch):
    h, c = bot
    seen = _hooks(monkeypatch, {"viral.list_materials": [dict(MAT, posted_at=1757560000)]})

    h.handle_command("dadang")

    assert seen[0][1][1] == "POSTED"
    assert "đăng lúc" in c.text
    data = [b["callback_data"] for b in c.buttons()]
    assert data == ["chuadang:976"], "đã đăng thì không còn Chọn đoạn / Chia phần / Gửi lại"


def test_dadang_rong_thi_chi_cach_dung(bot, monkeypatch):
    h, c = bot
    _hooks(monkeypatch, {"viral.list_materials": []})

    h.handle_command("dadang")

    assert "Đã đăng" in c.text


def test_help_nhac_dadang(bot):
    h, c = bot

    h.handle_command("help")

    assert "/dadang" in c.text
