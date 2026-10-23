"""PLAN-062 / ADR-047: admin áp dụng phí và thuế dự phòng cho báo giá V1.2."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from tests.test_cashback_bot import FakeClient, payload, repo, service

ADMIN = 7
NOW = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)  # 16:00 giờ VN
LINK = "https://shopee.vn/product/9/8"


def _bot(tmp_path, v12=True, **overrides):
    store = repo(tmp_path)
    if v12:
        with store.connect() as conn:
            conn.execute("ALTER TABLE link_requests ADD COLUMN estimate_policy TEXT")
    client = FakeClient(payload(last_update="2026-10-23 08:30:00"))
    overrides.setdefault("admin_user_ids", frozenset({ADMIN}))
    return service(tmp_path, client, estimate_policy="v1.2" if v12 else "v1.1", **overrides)


def _data(reply, suffix):
    return [d for row in reply.inline_keyboard for _label, d in row if d.endswith(suffix)][0]


def _wizard(bot, now, kind="k:H", fee=None, tax="1,5", when="w:now"):
    """Đi hết 4 bước, trả màn xem trước."""
    panel = bot.admin_panel
    step = panel.handle_callback(ADMIN, "c:rs:new", "private", now)
    step = panel.handle_callback(ADMIN, _data(step, kind), "private", now)
    step = panel.consume_text(ADMIN, fee, now) if fee else panel.handle_callback(ADMIN, _data(step, ":keep"), "private", now)
    step = panel.consume_text(ADMIN, tax, now) if tax else panel.handle_callback(ADMIN, _data(step, ":keep"), "private", now)
    if when.startswith("w:"):
        return panel.handle_callback(ADMIN, _data(step, when), "private", now)
    return panel.consume_text(ADMIN, when, now)


def _rows(tmp_path, sql):
    return sqlite3.connect(tmp_path / "cashback.sqlite").execute(sql).fetchall()


def test_ap_dung_ngay_link_moi_dung_muc_moi(tmp_path):
    bot = _bot(tmp_path)
    old = bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW)
    assert "<b>12.462đ</b>" in old.text

    preview = _wizard(bot, NOW)
    assert "Thuế dự phòng: 10% → <b>1,5%</b>" in preview.text
    assert "Loại hình: Chưa khai báo → <b>Hộ kinh doanh</b>" in preview.text
    assert "khách nhận 62.314đ → <b>68.264đ</b>" in preview.text
    assert "1 link gần nhất: tổng 12.462đ → <b>13.652đ</b>" in preview.text
    assert _rows(tmp_path, "SELECT COUNT(*) FROM reserve_policies") == [(0,)]

    done = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    assert done.toast == "Đã áp dụng mức #1"
    assert "Loại hình: <b>Hộ kinh doanh</b>" in done.text
    assert "Thuế dự phòng: <b>1,5%</b>" in done.text
    assert "Hiệu lực: từ 16:00 23/10/2026" in done.text

    new = bot.handle_text(111, "buyer", LINK, update_id=2, now=NOW + timedelta(seconds=5))
    assert "<b>13.652đ</b>" in new.text
    saved = _rows(tmp_path, "SELECT telegram_update_id, estimated_cashback, estimate_policy FROM link_requests ORDER BY id")
    assert saved[0] == (1, 12_462, "v1.2-reserve-2026-10-23")
    assert saved[1] == (2, 13_652, "v1.2-reserve-2026-10-23+r1")
    replay = bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW)
    assert "<b>12.462đ</b>" in replay.text, "link cũ giữ số đã báo"

    calc = bot.handle_text(111, "buyer", "/cachtinh", update_id=3)
    assert "dự phòng thuế 1,5%" in calc.text
    policy = bot.admin_panel.handle_callback(ADMIN, "c:menu:policy", "private", NOW)
    assert "Dự phòng thuế (1,5%): -1.500đ" in policy.text
    history = bot.admin_panel.handle_callback(ADMIN, "c:menu:hist", "private", NOW)
    assert "Dự phòng Hộ kinh doanh: phí 0,98%, thuế 1,5%, từ 16:00 23/10/2026 · Áp dụng cho khách: đã áp dụng" in history.text


def test_hen_gio_chua_ap_dung_truoc_moc(tmp_path):
    bot = _bot(tmp_path)
    preview = _wizard(bot, NOW, tax="5", when="01/11 08:00")
    assert "Hiệu lực: <b>08:00 01/11/2026</b>" in preview.text
    done = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    assert "SẮP ÁP DỤNG" in done.text
    assert "Hộ kinh doanh · phí 0,98% · thuế 5% · từ 08:00 01/11/2026" in done.text
    assert "Thuế dự phòng: <b>10%</b>" in done.text

    bot.client.payload["productInfo"]["lastUpdate"] = "2026-11-01 00:30:00"
    before = bot.handle_text(111, "buyer", LINK, update_id=1, now=datetime(2026, 11, 1, 0, 59, tzinfo=timezone.utc))
    after = bot.handle_text(111, "buyer", LINK, update_id=2, now=datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc))
    assert "<b>12.462đ</b>" in before.text
    assert "<b>13.162đ</b>" in after.text


def test_nut_00h_ngay_mai(tmp_path):
    bot = _bot(tmp_path)
    preview = _wizard(bot, NOW, when="w:tmr")
    assert "Hiệu lực: <b>00:00 24/10/2026</b>" in preview.text


def test_huy_va_het_han_khong_doi_muc(tmp_path):
    bot = _bot(tmp_path)
    preview = _wizard(bot, NOW)
    cancelled = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":no"), "private", NOW)
    assert cancelled.toast == "Đã hủy"
    assert "Mức đang áp dụng không đổi" in cancelled.text
    again = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    assert "đã được xử lý" in again.text

    preview = _wizard(bot, NOW)
    late = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW + timedelta(minutes=11))
    assert "hết hạn" in late.text
    assert _rows(tmp_path, "SELECT COUNT(*) FROM reserve_policies") == [(0,)]


def test_chan_nguoi_la_chat_nhom_nonce_sai(tmp_path):
    bot = _bot(tmp_path, admin_user_ids=frozenset({ADMIN, 8}))
    preview = _wizard(bot, NOW)
    ok = _data(preview, ":ok")
    stranger = bot.admin_panel.handle_callback(222, ok, "private", NOW)
    assert "chỉ dành cho quản trị" in stranger.text
    group = bot.admin_panel.handle_callback(ADMIN, ok, "group", NOW)
    assert "chỉ dành cho quản trị" in group.text
    other_admin = bot.admin_panel.handle_callback(8, ok, "private", NOW)
    assert "không hợp lệ" in other_admin.text
    parts = ok.split(":")
    parts[3] = "deadbeef"
    forged = ":".join(parts)
    assert "không hợp lệ" in bot.admin_panel.handle_callback(ADMIN, forged, "private", NOW).text
    assert _rows(tmp_path, "SELECT COUNT(*) FROM reserve_policies") == [(0,)]


def test_nut_buoc_cu_hien_lai_buoc_hien_tai(tmp_path):
    bot = _bot(tmp_path)
    panel = bot.admin_panel
    start = panel.handle_callback(ADMIN, "c:rs:new", "private", NOW)
    fee_step = panel.handle_callback(ADMIN, _data(start, "k:P"), "private", NOW)
    again = panel.handle_callback(ADMIN, _data(start, "k:H"), "private", NOW)
    assert again.text == fee_step.text
    restarted = panel.handle_callback(ADMIN, "c:rs:new", "private", NOW)
    stale = panel.handle_callback(ADMIN, _data(fee_step, ":keep"), "private", NOW)
    assert "đã được xử lý" in stale.text
    assert "Bước 1/4" in restarted.text


def test_admin_dan_link_giua_wizard_van_tao_link(tmp_path):
    bot = _bot(tmp_path)
    panel = bot.admin_panel
    start = panel.handle_callback(ADMIN, "c:rs:new", "private", NOW)
    panel.handle_callback(ADMIN, _data(start, "k:P"), "private", NOW)
    reply = bot.handle_text(ADMIN, "owner", LINK, update_id=5, now=NOW)
    assert "Đã tạo link hoàn tiền" in reply.text or "chưa được mở" in reply.text


def test_ngay_sai_va_gioi_han(tmp_path):
    bot = _bot(tmp_path)
    panel = bot.admin_panel
    start = panel.handle_callback(ADMIN, "c:rs:new", "private", NOW)
    panel.handle_callback(ADMIN, _data(start, "k:P"), "private", NOW)
    assert "tối đa 50%" in panel.consume_text(ADMIN, "60", NOW).text
    panel.consume_text(ADMIN, "1", NOW)
    panel.consume_text(ADMIN, "2", NOW)
    assert "đã qua" in panel.consume_text(ADMIN, "01/10", NOW).text
    assert "không hợp lệ" in panel.consume_text(ADMIN, "31/02", NOW).text
    assert "Chưa đọc được ngày" in panel.consume_text(ADMIN, "mai nhé", NOW).text
    assert "quá xa" in panel.consume_text(ADMIN, "01/11/2028", NOW).text


def test_v11_luu_duoc_nhung_khong_doi_so_khach(tmp_path):
    bot = _bot(tmp_path, v12=False)
    preview = _wizard(bot, NOW)
    assert "Đang chạy V1.1" in preview.text
    done = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    assert "Đang chạy V1.1" in done.text
    card = bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW)
    assert "<b>14.000đ</b>" in card.text


def test_chua_ap_dung_lan_nao_dung_env(tmp_path):
    bot = _bot(tmp_path, estimate_tax_reserve_bps=500)
    fee = bot.admin_panel.handle_callback(ADMIN, "c:menu:fee", "private", NOW)
    assert "Loại hình: <b>Chưa khai báo</b>" in fee.text
    assert "Thuế dự phòng: <b>5%</b>" in fee.text
    assert "Hiệu lực: mặc định cấu hình" in fee.text
    card = bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW)
    saved = _rows(tmp_path, "SELECT estimate_policy FROM link_requests")
    assert saved == [("v1.2-reserve-2026-10-23",)]
    assert "<b>13.162đ</b>" in card.text
