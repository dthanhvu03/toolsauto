"""
ADR-037 — lệnh Telegram nối vào luồng video, không chỉ luồng job cũ.

Trước bản này bộ lệnh chỉ chạm `Job` (cần tài khoản Facebook — Owner có 0), còn mọi thứ dựng
từ ADR-025 tới ADR-036 chỉ chạm Telegram ở hai chỗ: dán link vào và nhận video ra. Owner đưa
vào được, nhận ra được, nhưng không điều khiển được gì ở giữa.

Nguyên tắc như ADR-033/034: **gọi thật**, không đọc mã nguồn.
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
    for _ in range(60):
        if not [t for t in threading.enumerate() if t.name.startswith("tg-")]:
            return
        time.sleep(0.05)


@pytest.fixture
def bot(fake_db):
    client = StubClient()
    return TelegramCommandHandler(client), client


@pytest.fixture
def router(fake_db):
    client = StubClient()
    return TelegramEventRouter(client, TelegramCommandHandler(client)), client


SOURCE = {
    "id": 3, "platform": "tiktok", "handle": "thacaukechuyen", "min_views": 1000,
    "max_videos": 50, "enabled": True, "last_scanned_at": 1, "last_found": 5, "last_error": None,
}


# ── /nguon ──────────────────────────────────────────────────────────────────


def test_nguon_liet_ke_kem_nut_quet_va_tat(bot, monkeypatch):
    handler, client = bot
    _hooks(monkeypatch, {"viral.sources_summary": [SOURCE]})

    handler.handle_command("nguon")

    assert "thacaukechuyen" in client.text and "1,000" in client.text
    data = [b["callback_data"] for b in client.buttons()]
    assert "scan:3" in data and "tgsrc:3" in data


def test_nguon_dang_tat_thi_nut_doi_thanh_bat(bot, monkeypatch):
    handler, client = bot
    _hooks(monkeypatch, {"viral.sources_summary": [dict(SOURCE, enabled=False)]})

    handler.handle_command("nguon")

    assert "⚪ Tắt" in client.text
    assert any(b["text"] == "🟢 Bật" for b in client.buttons())


def test_nguon_co_loi_thi_hien_loi(bot, monkeypatch):
    handler, client = bot
    _hooks(monkeypatch, {"viral.sources_summary": [dict(SOURCE, last_error="TikTok chặn")]})

    handler.handle_command("nguon")

    assert "TikTok chặn" in client.text


def test_chua_co_nguon_thi_chi_cach_them(bot, monkeypatch):
    handler, client = bot
    _hooks(monkeypatch, {"viral.sources_summary": []})

    handler.handle_command("nguon")

    assert "Dán thẳng link" in client.text


# ── /moi và /sansang ────────────────────────────────────────────────────────


MAT = {"id": 976, "platform": "tiktok", "title": "Muốn giàu phải ra biển", "views": 12400,
       "url": "https://t/1", "clip_start_sec": None, "clip_length_sec": None}


def test_moi_liet_ke_kem_nut_xu_ly(bot, monkeypatch):
    handler, client = bot
    seen = _hooks(monkeypatch, {"viral.list_materials": [MAT]})

    handler.handle_command("moi")

    assert seen[0][1][1] == "NEW", "phải lọc đúng trạng thái NEW"
    assert "#976" in client.text and "12,400" in client.text
    assert "xuly:976" in [b["callback_data"] for b in client.buttons()]


def test_sansang_co_them_nut_chon_doan(bot, monkeypatch):
    handler, client = bot
    seen = _hooks(monkeypatch, {"viral.list_materials": [MAT]})

    handler.handle_command("sansang")

    assert seen[0][1][1] == "READY"
    data = [b["callback_data"] for b in client.buttons()]
    assert "gui:976" in data and "khung:976" in data


def test_hien_doan_cat_da_chon(bot, monkeypatch):
    handler, client = bot
    _hooks(monkeypatch, {"viral.list_materials": [dict(MAT, clip_start_sec=332, clip_length_sec=50)]})

    handler.handle_command("sansang")

    assert "từ 5:32" in client.text and "dài 50s" in client.text


@pytest.mark.parametrize("cmd,needle", [("moi", "Không có video mới"), ("sansang", "Chưa có video nào sẵn sàng")])
def test_rong_thi_noi_ro(bot, monkeypatch, cmd, needle):
    handler, client = bot
    _hooks(monkeypatch, {"viral.list_materials": []})

    handler.handle_command(cmd)

    assert needle in client.text


# ── nút bấm ─────────────────────────────────────────────────────────────────


def test_nut_quet_chay_nen_va_bao_ket_qua(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {"viral.scan_source": {"ok": True, "msg": "Tìm thấy 3 video mới, bỏ qua 1."}})

    r.dispatch({"callback_query": {"id": "c", "data": "scan:3", "message": {"message_id": 1}}})
    _wait()

    assert "Đang quét" in client.answers[0], "quét mất hàng chục giây ⇒ phải trả lời ngay"
    assert seen[0][0] == "viral.scan_source" and seen[0][1][1] == 3
    assert "3 video mới" in client.text


def test_nut_bat_tat_goi_dung_hook(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {"viral.toggle_source": {"ok": True, "msg": "Nguồn #3 nay TẮT."}})

    r.dispatch({"callback_query": {"id": "c", "data": "tgsrc:3", "message": {"message_id": 1}}})

    assert seen[0][0] == "viral.toggle_source"
    assert "TẮT" in client.text


def test_nut_xu_ly_tra_loi_ngay_roi_chay_nen(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {"viral.process_one": (True, "xong")})

    r.dispatch({"callback_query": {"id": "c", "data": "xuly:976", "message": {"message_id": 1}}})
    _wait()

    assert "Đang xử lý" in client.answers[0]
    assert [n for n, _ in seen] == ["viral.process_one"]
    assert seen[0][1][1] == 976


def test_nut_gui_lai_goi_dung_hook(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {"viral.resend_material": {"ok": True, "msg": "Đã gửi lại #976."}})

    r.dispatch({"callback_query": {"id": "c", "data": "gui:976", "message": {"message_id": 1}}})

    assert seen[0][0] == "viral.resend_material"
    assert "Đã gửi lại" in client.text


# ── dải khung hình + chọn mốc ───────────────────────────────────────────────


FRAMES = [(i, s) for i, s in enumerate([11, 57, 103, 148, 194, 240, 286, 332, 378, 424, 469, 515])]


def test_nut_chon_doan_gui_anh_luoi_va_12_nut(router, monkeypatch):
    """Telegram không cho bấm vào một vùng trong ảnh ⇒ phải một ảnh + nút riêng."""
    r, client = router
    _hooks(monkeypatch, {"viral.material_frames": {"frames": FRAMES, "sheet": "/x/sheet.jpg"}})

    r.dispatch({"callback_query": {"id": "c", "data": "khung:976", "message": {"message_id": 1}}})

    assert client.photos and client.photos[0][0] == "/x/sheet.jpg"
    data = [b["callback_data"] for b in client.buttons()]
    assert len(data) == 12
    assert "cut:976:332" in data
    assert any(b["text"] == "5:32" for b in client.buttons())


def test_khong_co_khung_thi_chi_cach_lay(router, monkeypatch):
    r, client = router
    _hooks(monkeypatch, {"viral.material_frames": {"frames": [], "sheet": None}})

    r.dispatch({"callback_query": {"id": "c", "data": "khung:976", "message": {"message_id": 1}}})

    assert "chưa có khung hình" in client.text.lower()
    assert "Xử lý" in client.text
    assert not client.photos


def test_ghep_anh_hong_thi_van_co_nut(router, monkeypatch):
    """Ảnh lưới là tiện ích phụ — hỏng thì vẫn phải chọn mốc được."""
    r, client = router
    _hooks(monkeypatch, {"viral.material_frames": {"frames": FRAMES, "sheet": None}})

    r.dispatch({"callback_query": {"id": "c", "data": "khung:976", "message": {"message_id": 1}}})

    assert not client.photos
    assert len([b for b in client.buttons()]) == 12


def test_bam_moc_thi_dat_clip_va_xu_ly_lai(router, monkeypatch):
    r, client = router
    seen = _hooks(monkeypatch, {
        "viral.set_clip": {"ok": True, "msg": "Đã đặt mốc giây 332"},
        "viral.process_one": (True, "xong"),
    })

    r.dispatch({"callback_query": {"id": "c", "data": "cut:976:332", "message": {"message_id": 1}}})
    _wait()

    assert [n for n, _ in seen] == ["viral.set_clip", "viral.process_one"]
    assert seen[0][1][1:] == (976, 332, None)
    assert "5:32" in client.text


def test_moc_hong_thi_bao_khong_nem(router, monkeypatch):
    r, client = router
    _hooks(monkeypatch, {})

    r.dispatch({"callback_query": {"id": "c", "data": "cut:976:abc", "message": {"message_id": 1}}})

    assert "không hợp lệ" in client.answers[0]


def test_dat_moc_that_bai_thi_bao_ro(router, monkeypatch):
    r, client = router
    _hooks(monkeypatch, {"viral.set_clip": {"ok": False, "msg": "Không tìm thấy material #976"}})

    r.dispatch({"callback_query": {"id": "c", "data": "cut:976:332", "message": {"message_id": 1}}})
    _wait()

    assert "Không tìm thấy" in client.text


# ── lệnh cũ phải nói rõ vì sao rỗng ─────────────────────────────────────────


def test_help_liet_ke_ca_lenh_moi(bot):
    handler, client = bot

    handler.handle_command("help")

    for cmd in ("/nguon", "/moi", "/sansang"):
        assert cmd in client.text
