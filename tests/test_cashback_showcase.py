"""🖼 Ảnh đăng bài: số liệu thật, tiền tạm tính, tên khách che."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from PIL import Image

from cashback_bot import showcase
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _financially_ready, _link

NOW = datetime(2026, 10, 28, 6, 0, tzinfo=timezone.utc)  # 13:00 28/10 giờ VN
ZALO = -3


def _seed(bot) -> None:
    _link(bot)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE link_requests SET created_at = '2026-10-21T09:00:00Z'")
        conn.execute("UPDATE telegram_users SET username = 'buyer_99'")
        conn.execute("INSERT INTO channel_identities (internal_user_id, channel, external_id, display_name, created_at) "
                     "VALUES (?, 'zalo', 'z1', 'Nguyễn Thị Hoa', '2026-10-22T00:00:00Z')", (ZALO,))
        conn.executemany(
            "INSERT INTO shopee_conversions (conversion_id, sub_id, order_sn, order_status, purchase_time, "
            "telegram_user_id, created_at, updated_at) VALUES (?, 's', ?, ?, ?, ?, '', '')",
            [("c1", "SN1", "PENDING", "2026-10-27T03:00:00Z", USER),
             ("c2", "SN1", "PENDING", "2026-10-27T03:00:00Z", USER),  # cùng đơn, món khác
             ("c3", "SN2", "COMPLETED", "2026-10-26T20:00:00Z", ZALO),  # 03:00 27/10 giờ VN
             ("c4", "SN3", "CANCELLED", "2026-10-27T03:00:00Z", USER)],
        )
        conn.executemany(
            "INSERT INTO cashback_entries (conversion_id, telegram_user_id, order_sn, item_name, commission_vnd, "
            "cashback_vnd, status, purchase_time, created_at, updated_at) VALUES (?, ?, ?, ?, 20000, ?, ?, ?, '', '')",
            [("c1", USER, "SN1", "Áo Polo Nam, cổ bẻ", 5_000, "pending", "2026-10-27T03:00:00Z"),
             ("c3", ZALO, "SN2", "Mực in HP", 7_000, "holding", "2026-10-26T20:00:00Z"),
             ("c3:clawback:1", ZALO, "SN2", "Mực in HP", -1_000, "pending", "2026-10-26T20:00:00Z"),
             ("c4", USER, "SN3", "Huỷ", 9_000, "cancelled", "2026-10-27T03:00:00Z")],
        )


def test_so_lieu_that_tam_tinh_che_ten(tmp_path):
    bot = _bot(tmp_path)
    _seed(bot)
    with bot.repo.connect() as conn:
        s = showcase.collect(conn, NOW)
    assert (s.members, s.links, s.orders, s.buyers, s.days_running) == (1, 1, 2, 2, 8)
    assert (s.pending_vnd, s.holding_vnd, s.available_vnd, s.recorded_vnd) == (4_000, 7_000, 0, 11_000)
    assert s.daily[0] == ("22/10", 0, 0) and s.daily[-2] == ("27/10", 0, 2) and s.daily[-1][0] == "Hôm nay"
    assert s.recent == [("B***r", 5_000, "Chờ sàn duyệt", "27/10"),
                        ("N***a", 7_000, "Đang giữ", "27/10")], "bỏ dòng huỷ và clawback; không có tên sản phẩm"
    post = showcase.post_text(s)
    assert "11.000đ hoàn tiền đã ghi nhận (tạm tính, chờ sàn duyệt)" in post
    assert "Đã chi trả" not in post, "chưa trả lần nào thì không viết như đã trả"
    assert "buyer_99" not in post and "Hoa" not in post
    image = Image.open(io.BytesIO(showcase.render_png(s)))
    assert image.format == "PNG" and image.width == showcase.WIDTH


def test_da_chi_tra_chi_hien_khi_co_luot_rut_da_tra(tmp_path):
    bot = _bot(tmp_path)
    _seed(bot)
    _financially_ready(bot)
    with bot.repo.connect() as conn:
        conn.execute("INSERT INTO cashback_payouts (telegram_user_id, amount_vnd, status, bank_code, account_no, account_name, "
                     "transfer_note, created_at, idempotency_key) VALUES (?, 20000, 'paid_confirmed', 'VCB', '0', 'A', "
                     "'n', '2026-10-28T00:00:00Z', 'k1')", (USER,))
        s = showcase.collect(conn, NOW)
    assert (s.paid_vnd, s.paid_count) == (20_000, 1)
    assert "✅ Đã chi trả 20.000đ qua 1 lượt rút" in showcase.post_text(s)
    showcase.render_png(s)


def test_che_ten():
    assert showcase.mask_name("Nguyễn Văn An", 5) == "N***n"
    assert showcase.mask_name("😀", 5) == "Khách Telegram"
    assert showcase.mask_name(None, -2) == "Khách Zalo"


def test_nut_anh_dang_bai_trong_thong_ke(tmp_path):
    bot = _bot(tmp_path)
    _seed(bot)
    stats = bot.admin_panel.handle_callback(ADMIN, "c:st:all", "private", NOW)
    assert ("🖼 Ảnh đăng bài", showcase.HOME) in [b for row in stats.inline_keyboard for b in row]
    home = bot.admin_panel.handle_callback(ADMIN, showcase.HOME, "private", NOW)
    assert "ẩn / hiện" in home.text and home.photo is None, "màn chỉnh chưa tạo ảnh"
    assert ("✅ Thành viên", "c:pb:t:members") in home.inline_keyboard[0]
    reply = _callback(bot, ADMIN, showcase.CARD)
    name, data, caption = reply.photo
    assert name.endswith(".png") and data.startswith(b"\x89PNG") and "tạm tính" in caption
    assert "<pre>" in reply.text
    assert reply.edit_message_id is None, "ảnh là tin mới, màn chỉnh ở lại"
    assert _callback(bot, ADMIN, showcase.HOME).edit_message_id == 5, "bật/tắt thì sửa tại chỗ"
    stranger = bot.admin_panel.handle_callback(USER, showcase.CARD, "private", NOW)
    assert stranger is None or stranger.photo is None, "chỉ admin"


def _press(bot, data: str):
    return bot.admin_panel.handle_callback(ADMIN, data, "private", NOW)


def test_an_hien_tung_muc_va_nho_lua_chon(tmp_path):
    bot = _bot(tmp_path)
    _seed(bot)
    full = _press(bot, showcase.CARD)
    for key in ("members", "money", "recent"):
        _press(bot, f"c:pb:t:{key}")
    home = _press(bot, showcase.HOME)
    assert ("⬜ Thành viên", "c:pb:t:members") in home.inline_keyboard[0], "bot nhớ lựa chọn"
    assert ("⬜ Hoàn tiền ghi nhận", "c:pb:t:money") in home.inline_keyboard[1]
    card = _press(bot, showcase.CARD)
    assert "thành viên" not in card.text and "hoàn tiền đã ghi nhận" not in card.text
    assert "🔗 1 link đã tạo · 🛒 2 đơn ghi nhận" in card.text and showcase.NOTE in card.text, "ghi chú luôn có"
    short = Image.open(io.BytesIO(card.photo[1]))
    assert short.height < Image.open(io.BytesIO(full.photo[1])).height, "mục tắt không chừa chỗ"

    _press(bot, "c:pb:d:14")
    _press(bot, "c:pb:n:6")
    _press(bot, "c:pb:t:hide_small")
    o = showcase.ShowcaseAdmin(bot.repo).options()
    with bot.repo.connect() as conn:
        conn.execute("INSERT INTO shopee_conversions (conversion_id, sub_id, order_sn, order_status, purchase_time, "
                     "telegram_user_id, created_at, updated_at) VALUES ('c5', 's', 'SN5', 'PENDING', "
                     "'2026-10-28T01:00:00Z', ?, '', '')", (USER,))
        conn.execute("INSERT INTO cashback_entries (conversion_id, telegram_user_id, order_sn, item_name, commission_vnd, "
                     "cashback_vnd, status, purchase_time, created_at, updated_at) VALUES ('c5', ?, 'SN5', 'Cáp', 900, "
                     "500, 'pending', '2026-10-28T01:00:00Z', '', '')", (USER,))
    assert (o.chart_days, o.recent_n, o.hide_small, o.recent) == (14, 6, True, True), "chọn số đơn thì bật lại mục"
    with bot.repo.connect() as conn:
        s = showcase.collect(conn, NOW, o)
    assert len(s.daily) == 14 and s.recent == [("B***r", 5_000, "Chờ sàn duyệt", "27/10"),
                                              ("N***a", 7_000, "Đang giữ", "27/10")], "đơn 500đ bị ẩn"
    showcase.render_png(s)
    with bot.repo.connect() as conn:
        assert showcase.collect(conn, NOW, showcase.Options()).recent[0][1] == 500, "mặc định hiện cả đơn nhỏ"

    for key in ("links", "orders", "chart", "recent"):
        _press(bot, f"c:pb:t:{key}")
    bare = _press(bot, showcase.CARD)
    assert bare.photo[1].startswith(b"\x89PNG"), "tắt hết vẫn tạo được ảnh (tiêu đề + ghi chú)"
    assert "Nút này không còn hiệu lực" in _press(bot, "c:pb:d:30").text


def test_an_don_nho():
    with_small = showcase.Options(hide_small=True)
    assert showcase.Options.load(with_small.dump()) == with_small
    assert showcase.Options.load("hỏng") == showcase.Options()
    assert showcase.Options.load('{"chart_days": 30, "members": "x"}') == showcase.Options()
