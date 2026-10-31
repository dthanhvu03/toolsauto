"""PLAN-107: thẻ link gọn, câu chờ đơn, thanh tiến trình /donhang, hướng dẫn chia sẻ. Không gọi mạng."""

from __future__ import annotations

from cashback_bot import messages
from cashback_bot.messages import (
    HUONGDAN,
    ORDERS_EMPTY,
    TIP_ALERT,
    _NOTE_TIKTOK_V12,
    _render_card,
    order_progress,
    orders_summary_reply,
    with_tiktok,
)
from cashback_bot.zalo_render import render


def _row(order_status="PENDING", validation="UNKNOWN", entry=None, **extra) -> dict:
    return {"conversion_id": "c1", "order": "…1234", "date": "30/10", "product": "Áo thun", "order_status": order_status,
            "validation_status": validation, "settlement_status": "NOT_VERIFIED", "cashback": 5_000, "sub_id": "x",
            "policy": "V1.2", "entry_status": entry, **extra}


def test_thanh_tien_trinh_theo_du_lieu_san():
    assert order_progress(_row()) == "✅ Đã mua › ⏳ Hoàn thành › ⚪ Sàn duyệt › ⚪ Vào ví"
    assert order_progress(_row("COMPLETED")) == "✅ Đã mua › ✅ Hoàn thành › ⏳ Sàn duyệt › ⚪ Vào ví"
    assert order_progress(_row("COMPLETED", "APPROVED")) == "✅ Đã mua › ✅ Hoàn thành › ✅ Sàn duyệt › ⏳ Vào ví"
    assert order_progress(_row("COMPLETED", "APPROVED", "available")).count("✅") == 4
    stats = {"total": 2, "waiting": 1, "approved": 0, "ineligible": 1, "estimated": 5_000}
    page = orders_summary_reply(stats, [_row(), _row("CANCELLED", conversion_id="c2")], 1, 1).text
    assert page.count("✅ Đã mua ›") == 1, "đơn huỷ không có thanh tiến trình"
    assert "khoảng 1 ngày" in page and "chờ Shopee xác minh" not in page, "thanh tiến trình thay chữ trạng thái"


def test_cho_don_noi_dung_khoang_1_ngay_khong_hua_15_phut():
    assert "khoảng 1 ngày" in ORDERS_EMPTY and "phút" not in ORDERS_EMPTY
    assert "khoảng 1 ngày" in TIP_ALERT and len(TIP_ALERT) <= 200


def test_the_tiktok_gon_va_zalo_cung_noi_dung():
    card = _render_card("Son môi", 199_000, 3_000, "https://vt.tiktok.com/x", _NOTE_TIKTOK_V12, tiktok=True)
    assert messages.TIKTOK_BUY_RULE in card.text and messages.TIKTOK_VOUCHER_RULE in card.text
    assert "xu" not in card.text.split("ⓘ")[0], "TikTok không có xu"
    assert len([line for line in card.text.split("\n") if line]) <= 8
    zalo = "\n".join(message.text for message in render(card)[0])
    for line in (messages.CART_RULE, messages.TIKTOK_VOUCHER_RULE, messages.TIKTOK_BUY_RULE):
        assert line in zalo, "Zalo dùng cùng chữ thẻ"
    free = _render_card("Son môi", 199_000, 0, "https://shopee.vn/x", "n")
    assert messages.CART_RULE not in free.text, "không có hoàn thì không nhắc điều kiện hoàn"


def test_huong_dan_chia_se_thang_vao_bot():
    assert "Chọn Telegram rồi chọn bot này" in HUONGDAN and "Sao chép liên kết" in HUONGDAN
    assert "Shopee hoặc TikTok Shop" in with_tiktok(HUONGDAN), "câu gốc TikTok còn nguyên"
