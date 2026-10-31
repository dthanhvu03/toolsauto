"""PLAN-107: thẻ link gọn, câu chờ đơn, thanh tiến trình /donhang, hướng dẫn chia sẻ. Không gọi mạng."""

from __future__ import annotations

from cashback_bot import messages
from cashback_bot.messages import (
    HUONGDAN,
    ORDERS_EMPTY,
    _render_card,
    order_progress,
    orders_summary_reply,
    render_success,
    render_success_v12,
    tip_reply,
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
    assert "khoảng 1 ngày" in tip_reply("u:tip").text


def test_the_link_4_dong_luu_y_o_trang_rieng():
    """Chủ bot 2026-10-31: thẻ chỉ còn tên, giá tham khảo, số hoàn, lời bấm nút; lưu ý ở trang 🛡️ riêng."""
    card = render_success_v12("Áo thun cổ tròn", 250_000, 12_000, "https://s.shopee.vn/x", extra_vnd=1, capped=True)
    assert card.text.split("\n") == [
        "🛍️ <b>Áo thun cổ tròn</b>", "🏷️ Giá tham khảo: 250.000đ",
        "💰 <b>Hoàn dự kiến: khoảng</b> <b>12.000đ</b> · <i>có thể cao hơn</i>", messages.BUY_HINT]
    [[(label, data)]] = card.inline_keyboard
    assert label == messages.TIP_LABEL and data == "u:tip:2c", "cờ V1.2 + món giá cao đi theo nút"
    tip = tip_reply(data).text
    for line in (messages.BUY_RULE, messages.CART_RULE, messages.VOUCHER_RULE, messages.CAPPED_RULE,
                 messages.ORDER_DELAY_RULE, messages.TRUST_LINE, "sau dự phòng phí và thuế", "Chưa phải tiền có thể rút."):
        assert line in tip
    plain = tip_reply(render_success("Áo", 250_000, 12_000, "https://s.shopee.vn/x").inline_keyboard[0][0][1]).text
    assert "Món giá cao" not in plain and "dự phòng phí" not in plain, "V1.1, không giá cao"
    assert "Shopee xác nhận" in tip_reply("u:tip").text, "thẻ cũ không cờ vẫn mở được"
    tiktok = tip_reply(render_success_v12("Son", 1, 3_000, "https://vt.tiktok.com/x", tiktok=True).inline_keyboard[0][0][1])
    assert messages.TIKTOK_VOUCHER_RULE in tiktok.text and "TikTok xác nhận" in tiktok.text
    free = render_success("Son môi", 199_000, 0, "https://shopee.vn/x")
    assert "không có tiền hoàn" in free.text and free.inline_keyboard is None, "không có hoàn: không có trang lưu ý"


def test_zalo_the_va_link_mua_mot_tin():
    card = _render_card("Son môi", 199_000, 3_000, "https://vt.tiktok.com/x", tiktok=True)
    messages_out, menu = render(card)
    assert len(messages_out) == 1, "thẻ và link mua chung một tin"
    text = messages_out[0].text
    assert text.index("Hoàn dự kiến") < text.index("Bấm link này để mua") < text.index("https://vt.tiktok.com/x")
    assert "tin dưới" not in text and "Bấm 🛒 Mua" not in text, "bỏ câu bấm nút của Telegram"
    assert menu and menu[0].startswith("u:tip")


def test_huong_dan_chia_se_thang_vao_bot():
    assert "Chọn Telegram rồi chọn bot này" in HUONGDAN and "Sao chép liên kết" in HUONGDAN
    assert "Shopee hoặc TikTok Shop" in with_tiktok(HUONGDAN), "câu gốc TikTok còn nguyên"
