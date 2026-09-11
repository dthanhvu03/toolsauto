"""
ADR-041 — nút chia phần trên Telegram: hỏi số phần → tính ở nền → đưa duyệt → cắt lần lượt.

Gọi thật `TelegramEventRouter` / `TelegramCommandHandler` với client giả, hook giả — như
ADR-037. Tool KHÔNG được tự cắt: phải có bước Owner bấm ✅.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.features.telegram_bot.command_handler import TelegramCommandHandler
from app.features.telegram_bot.event_router import TelegramEventRouter


class StubClient:
    def __init__(self):
        self.msgs: list[str] = []
        self.markups: list[dict | None] = []
        self.answers: list[str] = []
        self.photos: list[tuple] = []

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)
        self.markups.append(reply_markup)

    def send_photo(self, path, caption="", **kw):
        self.photos.append((path, caption))

    def answer_callback_query(self, callback_id, text="", **kw):
        self.answers.append(text)

    @property
    def text(self) -> str:
        return " ".join(self.msgs)

    def buttons(self) -> list[dict]:
        out = []
        for m in self.markups:
            if m:
                for row in m["inline_keyboard"]:
                    out.extend(row)
        return out


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

    seen: list[tuple] = []

    def _call(name, *args, **kw):
        seen.append((name, args))
        value = mapping.get(name)
        if isinstance(value, Exception):
            raise value
        return value(*args, **kw) if callable(value) else value

    monkeypatch.setattr(feature_hooks, "call", _call)
    return seen


def _wait():
    for _ in range(80):
        if not [t for t in threading.enumerate() if t.name.startswith("tg-")]:
            return
        time.sleep(0.05)


@pytest.fixture
def router(fake_db):
    client = StubClient()
    return TelegramEventRouter(client, TelegramCommandHandler(client)), client


@pytest.fixture
def bot(fake_db):
    client = StubClient()
    return TelegramCommandHandler(client), client


def _cb(data):
    return {"callback_query": {"id": "c", "data": data, "message": {"message_id": 1}}}


MAT = {"id": 976, "platform": "tiktok", "title": "Muốn giàu phải ra biển", "views": 12400,
       "url": "https://t/1", "clip_start_sec": None, "clip_length_sec": None,
       "parent_material_id": None, "part_index": None, "part_total": None}


# ── /sansang ────────────────────────────────────────────────────────────────


def test_sansang_video_goc_co_nut_chia_phan(bot, monkeypatch):
    handler, client = bot
    _hooks(monkeypatch, {"viral.list_materials": [MAT]})

    handler.handle_command("sansang")

    assert "chia:976" in [b["callback_data"] for b in client.buttons()]


def test_sansang_phan_con_KHONG_co_nut_chia_va_hien_phan_may(bot, monkeypatch):
    handler, client = bot
    _hooks(monkeypatch, {"viral.list_materials": [dict(MAT, id=981, parent_material_id=976, part_index=2, part_total=3)]})

    handler.handle_command("sansang")

    assert "chia:981" not in [b["callback_data"] for b in client.buttons()], "phần con không chia tiếp"
    assert "Phần 2/3" in client.text and "#976" in client.text


def test_help_nhac_chia_phan(bot):
    handler, client = bot

    handler.handle_command("help")

    assert "Chia phần" in client.text


# ── chia → hỏi số phần ──────────────────────────────────────────────────────


def test_bam_chia_thi_hoi_may_phan_chua_tinh_gi(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {})

    r.dispatch(_cb("chia:976"))

    assert not seen, "chưa được gọi hook nào — chưa tốn gì"
    data = [b["callback_data"] for b in client.buttons()]
    assert data == ["chian:976:2", "chian:976:3", "chian:976:4"]


# ── chian → tính ở nền → đưa duyệt ──────────────────────────────────────────


def test_tinh_ke_hoach_chay_nen_gui_anh_va_nut_duyet(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {"viral.propose_split": {
        "ok": True, "msg": "x", "text": "🧩 Kế hoạch chia #976\nPhần 1/3: 0:00 → 1:40", "sheet": "/x/sheet.jpg",
    }})

    r.dispatch(_cb("chian:976:3"))
    _wait()

    assert "Đang nghe" in client.answers[0], "Whisper chậm ⇒ phải trả lời ngay"
    assert seen[0][0] == "viral.propose_split" and seen[0][1][1:] == (976, 3)
    assert client.photos and client.photos[0][0] == "/x/sheet.jpg"
    assert "Phần 1/3" in client.text
    data = [b["callback_data"] for b in client.buttons()]
    assert "chiaok:976" in data, "phải có nút DUYỆT — tool không tự cắt"
    assert "chian:976:2" in data and "chian:976:4" in data and "chian:976:3" not in data


def test_tinh_ke_hoach_that_bai_thi_bao_ro_khong_co_nut_duyet(router, monkeypatch):
    r, client = router
    _hooks(monkeypatch, {"viral.propose_split": {"ok": False, "msg": "#976 chưa có file gốc trên máy"}})

    r.dispatch(_cb("chian:976:3"))
    _wait()

    assert "chưa có file gốc" in client.text
    assert "chiaok:976" not in [b["callback_data"] for b in client.buttons()]


def test_khong_co_anh_luoi_van_co_nut_duyet(router, monkeypatch):
    r, client = router
    _hooks(monkeypatch, {"viral.propose_split": {"ok": True, "msg": "x", "text": "kế hoạch", "sheet": None}})

    r.dispatch(_cb("chian:976:2"))
    _wait()

    assert not client.photos
    assert "chiaok:976" in [b["callback_data"] for b in client.buttons()]


def test_du_lieu_nut_hong_thi_khong_nem(router, monkeypatch):
    r, client = router
    _hooks(monkeypatch, {})

    r.dispatch(_cb("chian:976:abc"))

    assert "không hợp lệ" in client.answers[0]


# ── chiaok → tạo phần rồi cắt LẦN LƯỢT ──────────────────────────────────────


def test_duyet_thi_tao_phan_va_xu_ly_tung_phan_theo_thu_tu(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {
        "viral.apply_split": {"ok": True, "msg": "Đã tạo 3 phần", "child_ids": [981, 982, 983]},
        "viral.process_one": (True, "xong"),
    })

    r.dispatch(_cb("chiaok:976"))
    _wait()

    assert "#981" in client.msgs[0] and "#983" in client.msgs[0]
    assert [n for n, _ in seen] == ["viral.apply_split"] + ["viral.process_one"] * 3
    assert [a[1] for n, a in seen if n == "viral.process_one"] == [981, 982, 983], "đúng thứ tự phần"


def test_mot_phan_bi_tu_choi_thi_bao_dung_phan_do(router, monkeypatch):
    r, client = router
    calls = iter([(True, ""), (False, "ffmpeg hỏng"), (True, "")])
    _hooks(monkeypatch, {
        "viral.apply_split": {"ok": True, "msg": "x", "child_ids": [981, 982, 983]},
        "viral.process_one": lambda db, cid: next(calls),
    })

    r.dispatch(_cb("chiaok:976"))
    _wait()

    assert "Phần 2/3" in client.text and "#982" in client.text and "ffmpeg hỏng" in client.text


def test_da_chia_roi_thi_tu_choi_ro_ly_do(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {"viral.apply_split": {"ok": False, "msg": "#976 đã chia rồi (#981, #982)."}})

    r.dispatch(_cb("chiaok:976"))
    _wait()

    assert "đã chia rồi" in client.text
    assert [n for n, _ in seen] == ["viral.apply_split"], "không được xử lý gì thêm"
