"""PLAN-085 giai đoạn A: link TikTok Shop qua RioHub, báo giá cùng cách tính với Shopee.
PLAN-095 (giai đoạn B): đồng bộ đơn. RioHub giả, không gọi mạng."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import timedelta
from unittest.mock import MagicMock

from cashback_bot import admin_stats, admin_tiktok, insights, reconciliation, tiktok_sync
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.messages import TIKTOK_BUY_BUTTON
from cashback_bot.riohub_client import ProductLink, RioHubError
from cashback_bot.tiktok_url import parse_tiktok_target
from cashback_bot.zalo_render import TIKTOK_BUY_LEAD, render
from tests.test_cashback_bot import NOW, FakeClient, payload, service

ADMIN = 7
BUYER = 111
LINK = "https://vt.tiktok.com/ZS9yNg6SvUjFB-tq8JF/"
PRODUCT = {  # giống phản hồi thật 2026-10-26: giá 300.000đ, hoa hồng 500 bps
    "id": "1732000000000000001", "title": "Máy mài chân KY Y5",
    "commission": {"rate": 500}, "sales_price": {"minimum_amount": "300000", "maximum_amount": "300000"},
}


class FakeRioHub:
    def __init__(self, product: dict | None = PRODUCT, error: RioHubError | None = None):
        self.product = product
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def create_product_link(self, product: str, sub_id: str) -> ProductLink:
        self.calls.append((product, sub_id))
        if self.error is not None:
            raise self.error
        return ProductLink("https://www.tiktok.com/t/ZSgCQR9y3/", "1732000000000000001", self.product,
                           None if self.product else "not_found")


class FakeAdmin:
    def __init__(self):
        self.failed: list[str] = []

    def notify_request_failed(self, error_type: str, **_kwargs) -> None:
        self.failed.append(error_type)

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def _bot(tmp_path, riohub=None, **overrides):
    overrides.setdefault("admin_user_ids", frozenset({ADMIN}))
    overrides.setdefault("allowed_telegram_ids", frozenset({ADMIN, BUYER}))
    bot = service(tmp_path, FakeClient(payload()), **overrides)
    bot.riohub = FakeRioHub() if riohub is None else riohub
    return bot


def _links(bot):
    with bot.repo.connect() as conn:
        return conn.execute(
            "SELECT telegram_user_id, platform, link_status, reject_reason, sub_id, affiliate_url, item_id, price_vnd, "
            "estimated_commission, estimated_cashback, commission_rate_bps FROM link_requests ORDER BY id"
        ).fetchall()


def test_nhan_link_tiktok_shop():
    accepted = (
        LINK, "mua cái này https://vt.tiktok.com/ZS9yNg6S/ nhé", "vt.tiktok.com/ZS9yNg6S/",
        "https://www.tiktok.com/t/ZSgCQR9y3/", "https://shop.tiktok.com/view/product/1732000000000000001?x=1",
        "https://www.tiktok.com/view/product/1732000000000000001",
    )
    for text in accepted:
        assert parse_tiktok_target(text), text
    assert parse_tiktok_target("vt.tiktok.com/ZS9yNg6S/") == "https://vt.tiktok.com/ZS9yNg6S/"
    for text in ("https://www.tiktok.com/@shop/video/7300000000000000000", "https://s.shopee.vn/abc123",
                 "https://evil.com/vt.tiktok.com/x", "https://user:pw@vt.tiktok.com/ZS9yNg6S/", "xin chào"):
        assert parse_tiktok_target(text) is None, text


def test_admin_tao_link_tiktok_va_bao_gia(tmp_path):
    bot = _bot(tmp_path)
    reply = bot.handle_text(ADMIN, "admin", LINK, update_id=1, now=NOW)
    assert "🎵 TikTok Shop" in reply.text and "Máy mài chân KY Y5" in reply.text and "300.000đ" in reply.text
    assert "TikTok xác nhận đơn hợp lệ" in reply.text and "Shopee" not in reply.text
    assert reply.markup()["inline_keyboard"][0][0] == {"text": TIKTOK_BUY_BUTTON, "url": "https://www.tiktok.com/t/ZSgCQR9y3/"}
    (row,) = _links(bot)
    assert (row["platform"], row["link_status"], row["item_id"], row["price_vnd"]) == ("tiktok", "created", 1732000000000000001, 300_000)
    assert row["estimated_commission"] == 15_000 and row["commission_rate_bps"] == 500
    assert 0 < row["estimated_cashback"] < 15_000 and f"<b>{row['estimated_cashback']:,}đ</b>".replace(",", ".") in reply.text
    assert bot.riohub.calls == [(LINK, row["sub_id"])] and "-" not in row["sub_id"], "sub_id của bot không có dấu -"
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM link_policy_snapshots").fetchone()[0] == 1, "cùng snapshot như Shopee"
    replay = bot.handle_text(ADMIN, "admin", LINK, update_id=1, now=NOW)
    assert replay.text == reply.text and replay.button_label == TIKTOK_BUY_BUTTON, "Telegram gửi lại cùng update"
    zalo = render(reply)[0]
    assert zalo[-1].text.startswith(TIKTOK_BUY_LEAD) and "Bấm link ở tin dưới" in zalo[0].text


def test_che_do_mac_dinh_chi_admin(tmp_path):
    bot = _bot(tmp_path)
    reply = bot.handle_text(BUYER, "khach", LINK, update_id=1, now=NOW)
    assert "chưa hỗ trợ link TikTok Shop" in reply.text and bot.riohub.calls == []
    assert [(r["platform"], r["link_status"], r["reject_reason"]) for r in _links(bot)] == [("shopee", "rejected", "tiktok_not_open")]
    bot.repo.set_state(admin_tiktok.MODE_KEY, "all")
    assert "TikTok Shop" in bot.handle_text(BUYER, "khach", LINK, update_id=2, now=NOW).text
    bot.repo.set_state(admin_tiktok.MODE_KEY, "off")
    assert "chưa hỗ trợ" in bot.handle_text(ADMIN, "admin", LINK, update_id=3, now=NOW).text


def test_chua_co_khoa_riohub_thi_chua_ho_tro(tmp_path):
    bot = _bot(tmp_path)
    bot.riohub = None
    assert "chưa hỗ trợ link TikTok Shop" in bot.handle_text(ADMIN, "admin", LINK, update_id=1, now=NOW).text


def test_loi_riohub(tmp_path):
    bot = _bot(tmp_path, riohub=FakeRioHub(error=RioHubError("not_promotable", 422, "product_not_promotable")))
    assert "không có hoa hồng TikTok" in bot.handle_text(ADMIN, "a", LINK, update_id=1, now=NOW).text
    admin = FakeAdmin()
    bot = _bot(tmp_path / "b", riohub=FakeRioHub(error=RioHubError("creator", 424, "creator_token_invalid")))
    bot.admin_notifier = admin
    assert "Chưa tạo được link" in bot.handle_text(ADMIN, "a", LINK, update_id=1, now=NOW).text
    assert admin.failed == ["riohub_creator"] and _links(bot)[0]["reject_reason"] == "tiktok_creator"
    bot = _bot(tmp_path / "c", riohub=FakeRioHub(product=None))
    assert "Chưa lấy được thông tin sản phẩm TikTok" in bot.handle_text(ADMIN, "a", LINK, update_id=1, now=NOW).text
    assert _links(bot)[0]["reject_reason"] == "tiktok_no_product"


def test_man_admin_tiktok(tmp_path):
    bot = _bot(tmp_path)
    panel = bot.admin_panel
    blocked = panel.handle_callback(ADMIN, "c:tk:m:all:ok", "private", NOW)
    assert "Chưa có khoá RioHub" in blocked.text and admin_tiktok.current_mode(bot.repo) == "admin"
    panel = replace(panel, tiktok_configured=True)
    home = panel.handle_callback(ADMIN, "c:tk:home", "private", NOW)
    assert "🧪 Chỉ admin thử" in home.text and "Đồng bộ đơn (mỗi 2 giờ): chưa chạy lần nào" in home.text
    ask = panel.handle_callback(ADMIN, "c:tk:m:all", "private", NOW)
    assert "Mở cho khách?" in ask.text and admin_tiktok.current_mode(bot.repo) == "admin", "mở cho khách phải xác nhận"
    done = panel.handle_callback(ADMIN, "c:tk:m:all:ok", "private", NOW)
    assert "🟢 Mở cho khách" in done.text and admin_tiktok.current_mode(bot.repo) == "all"
    panel.handle_callback(ADMIN, "c:tk:m:off", "private", NOW)
    history = panel.handle_callback(ADMIN, "c:menu:hist", "private", NOW).text
    assert "TikTok Shop: 🧪 Chỉ admin thử → 🟢 Mở cho khách" in history and "🟢 Mở cho khách → ⚪ Tắt" in history


def test_cot_platform_cho_link_cu(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "khach", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    assert [r["platform"] for r in _links(bot)] == ["shopee"]
    conn = sqlite3.connect(bot.settings.db_path)
    assert "platform" in {row[1] for row in conn.execute("PRAGMA table_info(link_requests)")}


# --- Giai đoạn B: đồng bộ đơn (PLAN-095) --------------------------------------------------------------


class FakeOrders(FakeRioHub):
    def __init__(self, rows=(), error: RioHubError | None = None):
        super().__init__()
        self.rows = list(rows)
        self.order_error = error
        self.windows: list[tuple[int, int]] = []

    def iter_orders(self, start: int, end: int):
        self.windows.append((start, end))
        if self.order_error is not None:
            raise self.order_error
        yield from self.rows


def _order(sub_id: str, status: int = 1, actual=None, **extra) -> dict:
    row = {
        "order_id": "5800000000000001", "sku_id": "1730000000000009", "product_id": "1732000000000000001",
        "product_name": "Máy mài chân KY Y5", "sub_id": sub_id, "status": status, "quantity": 1,
        "fully_refunded": 0, "est_commission": "15000.00", "actual_commission": actual, "pit": "0.00",
        "commission_gmv": "300000.00", "settlement_status": "SETTLED" if status == 2 else "AWAITING PAYMENT",
        "create_time": int((NOW - timedelta(hours=3)).timestamp()),
    }
    return {**row, **extra}


def _tiktok_link(bot) -> str:
    bot.handle_text(ADMIN, "admin", LINK, update_id=1, now=NOW)
    return _links(bot)[0]["sub_id"]


def _conversion(bot):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT * FROM shopee_conversions WHERE conversion_id LIKE 'tt:%'").fetchone()


def _entry(bot):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT * FROM cashback_entries WHERE conversion_id LIKE 'tt:%'").fetchone()


def test_dong_bo_don_tiktok_ghi_so_nhu_shopee(tmp_path):
    bot = _bot(tmp_path)
    sub = _tiktok_link(bot)
    client = FakeOrders([_order(sub), _order("", order_id="5800000000000002"), {"order_id": "x"}])
    result = tiktok_sync.run(bot.repo, client, NOW)
    assert (result.rows, result.matched_new, result.skipped) == (3, 1, 1), "dòng thiếu khoá bị bỏ qua"
    row = _conversion(bot)
    assert row["conversion_id"] == "tt:5800000000000001:1730000000000009" and row["order_status"] == "PENDING"
    assert row["validation_status"] == "PENDING" and row["net_commission_vnd"] == 15_000 and row["gmv_vnd"] == 300_000
    assert row["telegram_user_id"] == ADMIN and row["item_name"] == "Máy mài chân KY Y5"
    bot.refresh_wallet(NOW)
    entry = _entry(bot)
    link = _links(bot)[0]
    assert entry["status"] == "pending" and entry["cashback_vnd"] == link["estimated_cashback"], "cùng cách tính lúc báo giá"
    with bot.repo.connect() as conn:
        notice = conn.execute("SELECT message_html FROM admin_notifications WHERE event_type = 'ORDER_ORDER_NEW'").fetchone()
    assert notice is not None and "TikTok vừa ghi nhận" in notice[0] and "Shopee" not in notice[0]
    page = bot.desk.orders_page(ADMIN)
    assert "chờ TikTok xác minh" in page.text and "Đã ghi nhận <b>1</b> đơn" in page.text


def test_don_tiktok_chot_va_huy(tmp_path):
    bot = _bot(tmp_path)
    sub = _tiktok_link(bot)
    tiktok_sync.run(bot.repo, FakeOrders([_order(sub)]), NOW)
    tiktok_sync.run(bot.repo, FakeOrders([_order(sub, status=2, actual="14000.00", settled_at_iso="2026-10-26T01:00:00Z")]),
                    NOW + timedelta(hours=2))
    row = _conversion(bot)
    assert (row["order_status"], row["net_commission_vnd"], row["complete_time"]) == ("COMPLETED", 14_000, "2026-10-26T01:00:00Z")
    assert row["validation_status"] == "PENDING" and row["settlement_status"] != "SETTLED", "không bao giờ tự gán APPROVED / SETTLED"
    bot.refresh_wallet(NOW + timedelta(days=30))
    assert _entry(bot)["status"] == "holding", "ví TikTok vẫn khoá: chưa có nguồn đối soát tiền thật"
    tiktok_sync.run(bot.repo, FakeOrders([_order(sub, status=3)]), NOW + timedelta(hours=4))
    bot.refresh_wallet(NOW + timedelta(days=30))
    assert _conversion(bot)["order_status"] == "CANCELLED" and _entry(bot)["status"] == "cancelled"


def test_loi_riohub_giu_moc_va_thu_lai_som(tmp_path):
    bot = _bot(tmp_path)
    assert tiktok_sync.run(bot.repo, FakeOrders([]), NOW) is not None
    end = bot.repo.get_state(tiktok_sync.LAST_END_KEY)
    failing = FakeOrders(error=RioHubError("creator", 424, "creator_token_invalid"))
    assert tiktok_sync.run(bot.repo, failing, NOW + timedelta(hours=2)) is None
    assert bot.repo.get_state(tiktok_sync.LAST_END_KEY) == end and bot.repo.get_state(tiktok_sync.ERROR_KEY) == "creator:creator_token_invalid"
    assert failing.windows[0][0] == int(end) - tiktok_sync.OVERLAP_SEC, "lần sau đọc lại 24 giờ trước mốc cũ"
    with bot.repo.connect() as conn:
        check = {c.code: c for c in insights.operations(conn, NOW + timedelta(hours=2))}["tiktok"]
    assert not check.ok and "creator_token_invalid" in check.value, "🛠 Vận hành báo đồng bộ TikTok hỏng"
    attempt = (NOW + timedelta(hours=2)).timestamp()
    bot.repo.set_state(tiktok_sync.ATTEMPT_KEY, str(attempt))
    assert not tiktok_sync.due(bot.repo, attempt + 600) and tiktok_sync.due(bot.repo, attempt + 15 * 60)


def test_chay_nen_moi_2_gio(tmp_path):
    bot = _bot(tmp_path)
    assert tiktok_sync.maybe_start(bot.repo, None) is None, "chưa có khoá RioHub thì không chạy"
    start = NOW.timestamp()
    thread = tiktok_sync.maybe_start(bot.repo, FakeOrders([]), now=start)
    thread.join(5)
    assert bot.repo.get_state(tiktok_sync.OK_KEY) and bot.repo.get_state(tiktok_sync.ERROR_KEY) == ""
    assert tiktok_sync.maybe_start(bot.repo, FakeOrders([]), now=start + 3600) is None
    later = tiktok_sync.maybe_start(bot.repo, FakeOrders([]), now=start + 2 * 3600)
    assert later is not None
    later.join(5)
    assert "Đồng bộ đơn (mỗi 2 giờ):" in bot.admin_panel.handle_callback(ADMIN, "c:tk:home", "private", NOW).text


def test_doi_soat_shopee_bo_qua_don_tiktok(tmp_path):
    bot = _bot(tmp_path)
    tiktok_sync.run(bot.repo, FakeOrders([_order(_tiktok_link(bot))]), NOW)
    reconciliation.evaluate(bot.repo, NOW + timedelta(days=50), run_id=99, run_success=True)
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversion_reconciliation WHERE conversion_id LIKE 'tt:%'").fetchone()[0] == 0


# --- Rà soát 2026-10-26, đợt 1 ------------------------------------------------------------------------


def _press(bot, user_id: int, data: str):
    update = {"update_id": 900, "callback_query": {"id": f"q-{data}", "from": {"id": user_id}, "data": data,
                                                    "message": {"message_id": 5, "chat": {"type": "private"}}}}
    return bot.handle_update(update)[1]


def test_nut_xem_don_tiktok_mo_duoc(tmp_path):
    bot = _bot(tmp_path)
    tiktok_sync.run(bot.repo, FakeOrders([_order(_tiktok_link(bot))]), NOW)
    detail = _press(bot, ADMIN, f"u:o:d:{_conversion(bot)['conversion_id']}")
    assert "không còn hiệu lực" not in (detail.text + (detail.toast or "")) and "TikTok" in detail.text
    assert len(f"u:o:d:{_conversion(bot)['conversion_id']}".encode()) <= 64, "giới hạn callback_data của Telegram"


def test_don_tiktok_huy_sau_khi_chot_khong_tang_hoan(tmp_path):
    bot = _bot(tmp_path)
    sub = _tiktok_link(bot)
    tiktok_sync.run(bot.repo, FakeOrders([_order(sub, status=2, actual="9000.00")]), NOW)
    tiktok_sync.run(bot.repo, FakeOrders([_order(sub, status=3)]), NOW + timedelta(hours=2))
    assert _conversion(bot)["net_commission_vnd"] == 9_000, "huỷ giữ số đã ghi, không về số ước tính"
    with bot.repo.connect() as conn:
        notice = conn.execute("SELECT message_html FROM admin_notifications WHERE event_type = 'ORDER_ORDER_UPDATE' "
                              "ORDER BY id DESC").fetchone()[0]
    assert "Đơn đã huỷ" in notice and "Hoàn tạm tính" not in notice and "TikTok" in notice


def test_bam_man_khac_thi_thoi_cho_go(tmp_path):
    bot = _bot(tmp_path)
    panel = bot.admin_panel
    for start in ("c:in:f", "c:in:t:net", "c:rt:e:finance_years"):
        panel.handle_callback(ADMIN, start, "private", NOW)
        panel.handle_callback(ADMIN, "c:menu:home", "private", NOW)
        assert panel.consume_text(ADMIN, "12", NOW) is None, start
    reply = bot.handle_text(ADMIN, "admin", "https://shopee.vn/product/9/8", update_id=50, now=NOW)
    assert "Đã tạo link" in reply.text, "link Shopee không bị nuốt thành từ khoá tìm"


# --- Rà soát 2026-10-26, đợt 2: TikTok đúng nền tảng -------------------------------------------------


def test_cot_platform_va_khoa_tien_tiktok_o_tang_db(tmp_path):
    bot = _bot(tmp_path)
    tiktok_sync.run(bot.repo, FakeOrders([_order(_tiktok_link(bot), status=2, actual="9000.00")]), NOW)
    row = _conversion(bot)
    assert (row["platform"], row["validation_source"]) == ("tiktok", "riohub_orders")
    with bot.repo.connect() as conn:  # dòng có từ trước khi có cột: migrate gán lại theo mã «tt:»
        conn.execute("UPDATE shopee_conversions SET platform = 'shopee'")
    bot.repo.migrate()
    assert _conversion(bot)["platform"] == "tiktok"
    bot.refresh_wallet(NOW + timedelta(days=30))
    with bot.repo.connect() as conn:
        conn.execute("UPDATE shopee_conversions SET settlement_status = 'SETTLED' WHERE platform = 'tiktok'")
    try:
        with bot.repo.connect() as conn:
            conn.execute("UPDATE cashback_entries SET status = 'available' WHERE conversion_id LIKE 'tt:%'")
        raise AssertionError("khoản TikTok không được vào ví khi chưa có nguồn đối soát TikTok")
    except sqlite3.IntegrityError as exc:
        assert "platform" in str(exc)


def test_thong_ke_shopee_va_duyet_hoa_hong_tach_tiktok(tmp_path):
    bot = _bot(tmp_path)
    tiktok_sync.run(bot.repo, FakeOrders([_order(_tiktok_link(bot))]), NOW)
    with bot.repo.connect() as conn:
        stats = admin_stats._shopee_stats(conn, "2000-01-01T00:00:00Z")
    assert stats.orders_total == 0, "đơn TikTok không cộng vào khối Shopee"
    conv = _conversion(bot)["conversion_id"]
    listing = bot.admin_panel.handle_callback(ADMIN, "c:cv:l:pending", "private", NOW)
    assert any(label.startswith("📋 🎵") or "🎵" in label for row in listing.inline_keyboard for label, _d in row)
    detail = bot.admin_panel.handle_callback(ADMIN, f"c:cv:o:{conv}", "private", NOW)
    assert "🎵 TikTok Shop" in detail.text and "RioHub" in detail.text and "TikTok chưa chốt đơn" in detail.text
    assert "Tiền TikTok đã trả" in detail.text and "báo cáo Shopee" not in detail.text


def test_bao_admin_don_tiktok_moi_va_loi_dong_bo(tmp_path):
    bot = _bot(tmp_path)
    admin = AdminNotifier(bot.repo, MagicMock(), enabled=True, chat_id=ADMIN)
    sub = _tiktok_link(bot)
    tiktok_sync.maybe_start(bot.repo, FakeOrders([_order(sub)]), admin, now=NOW.timestamp()).join(5)
    failing = FakeOrders(error=RioHubError("creator", 424, "creator_token_invalid"))
    for hours in (3, 4):
        tiktok_sync.maybe_start(bot.repo, failing, admin, now=(NOW + timedelta(hours=hours)).timestamp()).join(5)
    with bot.repo.connect() as conn:
        rows = dict(conn.execute("SELECT event_type, message_html FROM admin_notifications "
                                 "WHERE event_type LIKE 'TIKTOK_%'").fetchall())
        failed = conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE event_type = 'TIKTOK_SYNC_FAILED'").fetchone()[0]
    assert "Có 1 đơn TikTok mới qua bot" in rows["TIKTOK_NEW_ORDERS"]
    assert "mất kết nối với RioHub" in rows["TIKTOK_SYNC_FAILED"] and failed == 1, "mỗi loại lỗi một lần mỗi ngày"


def test_gui_lai_link_tiktok_bi_tu_choi_tra_dung_ly_do(tmp_path):
    bot = _bot(tmp_path)
    first = bot.handle_text(BUYER, "khach", LINK, update_id=7, now=NOW)
    again = bot.handle_text(BUYER, "khach", LINK, update_id=7, now=NOW)
    assert "chưa hỗ trợ link TikTok Shop" in first.text and again.text == first.text
