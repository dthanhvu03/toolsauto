"""ADR-048: admin đổi tỷ lệ chia trong /admin → Chính sách."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from tests.test_cashback_reserve import ADMIN, LINK, NOW, _bot, _data, _rows, _wizard


def _share(bot, now, typed="65", when="w:now"):
    """Đi hết 2 bước, trả màn xem trước."""
    panel = bot.admin_panel
    panel.handle_callback(ADMIN, "c:sh:new", "private", now)
    step = panel.consume_text(ADMIN, typed, now)
    if when.startswith("w:"):
        return panel.handle_callback(ADMIN, _data(step, when), "private", now)
    return panel.consume_text(ADMIN, when, now)


def test_doi_ty_le_ngay_link_moi_dung_ty_le_moi(tmp_path):
    bot = _bot(tmp_path)
    old = bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW)
    assert "<b>12.462đ</b>" in old.text

    policy = bot.admin_panel.handle_callback(ADMIN, "c:menu:policy", "private", NOW)
    assert ("✏️ Đổi tỷ lệ chia", "c:sh:new") in policy.inline_keyboard[0]
    assert "Hiệu lực tỷ lệ: mặc định cấu hình" in policy.text

    preview = _share(bot, NOW)
    assert "Tỷ lệ chia: 70% → <b>65%</b>" in preview.text
    assert "Khách nhận: 62.314đ → <b>57.863đ</b>" in preview.text
    assert "Phần giữ lại: 26.706đ → <b>31.157đ</b>" in preview.text
    assert "1 link gần nhất: khách tổng 12.462đ → <b>11.572đ</b>" in preview.text

    done = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    assert done.toast == "Đã áp dụng tỷ lệ #1"
    assert "Tỷ lệ: <b>65% phần còn lại</b>" in done.text
    assert "Hiệu lực tỷ lệ: từ 16:00 23/10/2026" in done.text

    new = bot.handle_text(111, "buyer", LINK, update_id=2, now=NOW + timedelta(seconds=5))
    assert "<b>11.572đ</b>" in new.text
    saved = _rows(tmp_path, "SELECT estimated_cashback, cashback_rate_percent, estimate_policy FROM link_requests ORDER BY id")
    assert saved[0] == (12_462, 70, "v1.2-reserve-2026-10-23")
    assert saved[1] == (11_572, 65, "v1.2-reserve-2026-10-23+s1")
    assert "<b>12.462đ</b>" in bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW).text

    assert "rồi tính 65% phần còn lại" in bot.handle_text(111, "buyer", "/cachtinh", update_id=3).text
    home = bot.admin_panel.menu(ADMIN, NOW)
    assert "V1.2 · 65% phần còn lại" in home.text
    fee = bot.admin_panel.handle_callback(ADMIN, "c:menu:fee", "private", NOW)
    assert "Khách nhận (65%): <b>57.863đ</b>" in fee.text
    history = bot.admin_panel.handle_callback(ADMIN, "c:menu:hist", "private", NOW)
    assert "Tỷ lệ chia → 65%, từ 16:00 23/10/2026 · Áp dụng cho khách: đã áp dụng" in history.text


def test_lich_ty_le_va_lich_du_phong_khong_de_nhau(tmp_path):
    bot = _bot(tmp_path)
    reserve = _wizard(bot, NOW, tax="1,5")
    bot.admin_panel.handle_callback(ADMIN, _data(reserve, ":ok"), "private", NOW)
    share = _share(bot, NOW, typed="60", when="01/11 08:00")
    assert "Hiệu lực: <b>08:00 01/11/2026</b>" in share.text
    done = bot.admin_panel.handle_callback(ADMIN, _data(share, ":ok"), "private", NOW)
    assert "Sắp áp dụng: 60% từ 08:00 01/11/2026" in done.text

    bot.client.payload["productInfo"]["lastUpdate"] = "2026-11-01 00:30:00"
    before = bot.handle_text(111, "buyer", LINK, update_id=1, now=datetime(2026, 11, 1, 0, 59, tzinfo=timezone.utc))
    after = bot.handle_text(111, "buyer", LINK, update_id=2, now=datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc))
    assert "<b>13.652đ</b>" in before.text, "70% với thuế 1,5%"
    assert "<b>11.702đ</b>" in after.text, "60% vẫn giữ thuế 1,5%"
    assert _rows(tmp_path, "SELECT estimate_policy FROM link_requests ORDER BY id")[-1] == ("v1.2-reserve-2026-10-23+r1+s1",)


def test_nhap_sai_huy_het_han(tmp_path):
    bot = _bot(tmp_path)
    panel = bot.admin_panel
    panel.handle_callback(ADMIN, "c:sh:new", "private", NOW)
    assert "tối đa 70%" in panel.consume_text(ADMIN, "71", NOW).text
    assert "số nguyên" in panel.consume_text(ADMIN, "65,5", NOW).text
    when = panel.consume_text(ADMIN, "65", NOW)
    cancelled = panel.handle_callback(ADMIN, _data(when, ":no"), "private", NOW)
    assert cancelled.toast == "Đã hủy"
    assert "Tỷ lệ đang áp dụng không đổi" in cancelled.text

    preview = _share(bot, NOW)
    late = panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW + timedelta(minutes=11))
    assert "hết hạn" in late.text
    assert "chỉ dành cho quản trị" in panel.handle_callback(222, _data(preview, ":ok"), "private", NOW).text
    assert _rows(tmp_path, "SELECT COUNT(*) FROM share_policies") == [(0,)]


def test_mo_wizard_ty_le_huy_wizard_du_phong_dang_do(tmp_path):
    bot = _bot(tmp_path)
    panel = bot.admin_panel
    start = panel.handle_callback(ADMIN, "c:rs:new", "private", NOW)
    panel.handle_callback(ADMIN, _data(start, "k:P"), "private", NOW)
    panel.handle_callback(ADMIN, "c:sh:new", "private", NOW)
    reply = panel.consume_text(ADMIN, "65", NOW)
    assert "Tỷ lệ chia mới: <b>65%</b>" in reply.text
    assert _rows(tmp_path, "SELECT step FROM reserve_drafts") == [("cancelled",)]


def test_v11_luu_ty_le_nhung_khong_doi_so_khach(tmp_path):
    bot = _bot(tmp_path, v12=False)
    preview = _share(bot, NOW)
    assert "Đang chạy V1.1" in preview.text
    done = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    assert "tỷ lệ admin đặt có tác dụng khi bật V1.2" in done.text
    assert "Tỷ lệ: <b>70% hoa hồng ước tính</b>" in done.text
    card = bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW)
    assert "<b>14.000đ</b>" in card.text
    assert _rows(tmp_path, "SELECT cashback_rate_percent FROM link_requests") == [(70,)]


def test_bang_chan_ty_le_khong_hop_le(tmp_path):
    bot = _bot(tmp_path)
    bot.admin_panel.menu(ADMIN, NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    for bad in (7_100, 6_550, -100):
        try:
            conn.execute(
                "INSERT INTO share_policies (share_bps, effective_at, created_by, created_at) VALUES (?, 'x', 1, 'x')",
                (bad,),
            )
        except sqlite3.IntegrityError:
            continue
        raise AssertionError(f"share_bps={bad} lẽ ra bị CHECK chặn")
