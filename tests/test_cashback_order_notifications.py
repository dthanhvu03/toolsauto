"""PLAN-079: theo dõi đơn của khách, thông báo đơn qua hàng đợi bền, chống trùng, gửi lại, tuỳ chọn, theo dõi admin.

Dùng Telegram giả lập; không gửi tin thật.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from cashback_bot import customer_orders, order_notify
from cashback_bot.messages import order_update_notice
from cashback_bot.notify_dispatch import Dispatcher
from cashback_bot.telegram_api import TelegramDeliveryError
from tests.test_cashback_bot import NOW as QUOTE_NOW
from tests.test_cashback_reserve import _bot as reserve_bot
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _link, _order

OTHER = 222
BASE = "2026-10-01T00:00:00Z"


class FakeTelegram:
    def __init__(self, errors=None):
        self.sent: list[tuple[int, str, dict | None]] = []
        self.errors = list(errors or [])

    def send_message(self, chat_id, html, reply_markup=None, disable_notification=False):
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        self.sent.append((chat_id, html, reply_markup))
        return 1000 + len(self.sent)


def _ready(tmp_path, enabled=True, **overrides):
    overrides.setdefault("allowed_telegram_ids", frozenset({USER, OTHER}))
    bot = _bot(tmp_path, customer_notifications_enabled=enabled, **overrides)
    bot.repo.set_state(order_notify.BASELINE_KEY, BASE)
    return bot


def _events(bot, status=None):
    sql = "SELECT * FROM admin_notifications WHERE audience = 'customer' AND category LIKE 'order_%'"
    with bot.repo.connect() as conn:
        rows = conn.execute(sql + " ORDER BY id").fetchall()
    return [r for r in rows if status is None or r["status"] == status]


def _flush(bot, telegram, now=None, enabled=True):
    return Dispatcher(bot.repo, telegram, False, None, enabled).flush(limit=50, now=now)


def _link_for(bot, user):
    bot.handle_text(user, "u", "https://shopee.vn/product/9/8", update_id=7000 + user, now=QUOTE_NOW)
    with bot.repo.connect() as conn:
        return conn.execute("SELECT sub_id FROM link_requests WHERE telegram_user_id = ? ORDER BY id DESC", (user,)).fetchone()[0]


# --- Thông báo đơn (1–16) ----------------------------------------------------------------------


def test_01_41_don_moi_dung_sub_id_bao_dung_nguoi_tao_link(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="PENDING", commission=10_000)
    (event,) = _events(bot)
    assert (event["chat_id"], event["status"], event["event_key"]) == (USER, "pending", "conversion:o1:first_matched")
    assert "Có đơn mới qua link của bạn" in event["message_html"] and "<b>7.000đ</b>" in event["message_html"]
    assert "Chưa phải tiền có thể rút" in event["message_html"]
    assert json.loads(event["reply_markup_json"])["inline_keyboard"][0][0]["callback_data"] == "u:o:d:o1"
    telegram = FakeTelegram()
    assert _flush(bot, telegram).sent == 1
    assert telegram.sent[0][0] == USER
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT status, telegram_message_id FROM admin_notifications WHERE id = ?", (event["id"],)).fetchone()
    assert tuple(row) == ("sent", 1001)


def test_02_03_04_don_khong_thuoc_bot_khong_sub_id_sub_sai(tmp_path):
    bot = _ready(tmp_path)
    for cid, sub in (("x1", "NOTOURS1"), ("x2", None), ("x3", "")):
        bot.repo.record_shopee_conversion(cid, sub, "SN" + cid, "PENDING", "", "2026-10-21T09:00:00Z", 1000, 1000)
    assert _events(bot) == []


def test_05_xung_dot_gan_nguoi_nhan_khong_bao(tmp_path):
    bot = _ready(tmp_path)
    mine = _link(bot)
    theirs = _link_for(bot, OTHER)
    _order(bot, mine, commission=10_000)
    _order(bot, theirs, status="COMPLETED", commission=20_000)  # cùng đơn, Sub ID trỏ link khác
    assert len(_events(bot)) == 1, "chỉ tin đơn mới ban đầu; xung đột thì không báo thay đổi"
    _order(bot, mine, status="CANCELLED", commission=20_000)
    assert len(_events(bot)) == 1
    assert all(e["chat_id"] == USER for e in _events(bot))


def test_06_don_chua_thanh_toan_khong_noi_da_thanh_toan(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), status="UNPAID", commission=10_000)
    html = _events(bot)[0]["message_html"]
    assert "Người mua chưa thanh toán đơn" in html and "đã thanh toán" not in html


def test_07_08_09_trang_thai_co_y_nghia(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="UNPAID", commission=10_000)
    _order(bot, sub, status="PAID", commission=10_000)
    _order(bot, sub, status="COMPLETED", commission=10_000)
    _order(bot, sub, status="CANCELLED", commission=10_000)
    texts = [e["message_html"] for e in _events(bot)]
    assert len(texts) == 4
    assert "Người mua đã thanh toán đơn" in texts[1]
    assert "Đơn hàng đã hoàn thành" in texts[2] and "đang chờ Shopee xác minh" in texts[2] and "đã được Shopee duyệt" not in texts[2]
    assert "Đơn đã huỷ" in texts[3] and "/hotro" in texts[3]


def test_10_gian_lan_dien_dat_trung_lap(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, commission=10_000)
    _order(bot, sub, commission=10_000, fraud=True)
    html = _events(bot)[-1]["message_html"]
    assert "không đủ điều kiện" in html.lower() and "/hotro" in html
    assert "gian lận" not in html.lower() and "fraud" not in html.lower()


def test_11_12_13_14_hoa_hong_doi_theo_nguong(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, commission=10_000)
    _order(bot, sub, commission=9_800)  # 7.000 → 6.860: dưới ngưỡng
    assert len(_events(bot)) == 1
    _order(bot, sub, commission=20_000)  # tăng
    assert "6.860đ → <b>14.000đ</b>" in _events(bot)[-1]["message_html"]
    _order(bot, sub, commission=5_000)  # giảm
    assert "14.000đ → <b>3.500đ</b>" in _events(bot)[-1]["message_html"]
    _order(bot, sub, commission=0)
    assert "3.500đ → <b>0đ</b>" in _events(bot)[-1]["message_html"]
    count = len(_events(bot))
    bot.repo.record_shopee_conversion("o1", sub, "SN-o1", None, None, None, None, None)  # response thiếu field
    assert len(_events(bot)) == count


def test_15_37_dong_bo_y_het_10_lan_mot_tin(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    for _ in range(10):
        _order(bot, sub, commission=10_000)
    assert len(_events(bot)) == 1
    telegram = FakeTelegram()
    _flush(bot, telegram)
    _flush(bot, telegram)
    assert len(telegram.sent) == 1


def test_16_hook_loi_khong_lam_hong_ghi_don(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)

    def broken(*_args):
        raise RuntimeError("boom")

    bot.repo.conversion_hooks.insert(0, broken)
    _order(bot, sub, commission=10_000)
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM shopee_conversions").fetchone()[0] == 1
    assert len(_events(bot)) == 1, "hook sau vẫn chạy"


def test_38_gom_thay_doi_trong_mot_lan_dong_bo(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="PENDING", commission=10_000)
    _order(bot, sub, status="COMPLETED", commission=20_000)
    html = _events(bot)[-1]["message_html"]
    assert len(_events(bot)) == 2
    assert "Đơn hàng đã hoàn thành" in html and "7.000đ → <b>14.000đ</b>" in html


# --- Đơn hàng của tôi (17–26) -------------------------------------------------------------------


def test_17_20_donhang_tong_quan_va_chi_tiet(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, commission=17_368, cid="o1")
    _order(bot, sub, commission=1_372, cid="o2")
    bot.refresh_wallet(datetime(2026, 10, 22, tzinfo=timezone.utc))
    page = bot.handle_text(USER, "b", "/donhang", update_id=801, now=QUOTE_NOW)
    assert "Đã ghi nhận <b>2</b> đơn qua link của bạn" in page.text
    assert "⏳ 2 chờ xác minh" in page.text and "đã duyệt" not in page.text, "chỉ hiện số khác 0"
    assert "💰 Hoàn tạm tính: <b>13.117đ</b>" in page.text
    assert "Chưa có khoản nào vào ví." in page.text
    assert "<b>1. Áo Polo Nam</b>" in page.text and "🛒 Mua 21/10/2026 · Đang xử lý" in page.text
    assert [label for row in page.inline_keyboard for label, _d in row][:2] == ["1. Áo Polo Nam · 960đ", "2. Áo Polo Nam · 12.157đ"]
    detail = _callback(bot, USER, "u:o:d:o1")
    assert "📦 <b>Áo Polo Nam</b>" in detail.text and "mua 21/10/2026" in detail.text
    assert "💰 Hoàn tạm tính: <b>12.157đ</b>" in detail.text and "V1.1" not in detail.text
    assert "✅ Shopee ghi nhận đơn qua link của bạn" in detail.text and "⏳ Đơn đang được xử lý" in detail.text
    assert "⏳ Chờ Shopee duyệt hoa hồng" in detail.text and "✅ Shopee đã duyệt" not in detail.text
    assert "⏳ Chờ Shopee thanh toán hoa hồng cho chương trình" in detail.text and "Tiền hoàn chưa vào ví" in detail.text
    assert "raw" not in detail.text.lower() and "SN-o1" not in detail.text
    assert "u:h:c:amount" in [d for row in detail.inline_keyboard for _l, d in row]


def test_18_chua_co_don(tmp_path):
    bot = _ready(tmp_path)
    page = bot.handle_text(USER, "b", "/donhang", update_id=802, now=QUOTE_NOW)
    assert "Chưa có đơn nào mua qua link bạn đã tạo" in page.text and "/hotro" in page.text
    assert "u:p:guide" in str(page.inline_keyboard)


def test_chi_tiet_don_huy_va_da_thanh_toan(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="COMPLETED", commission=10_000, cid="ok")
    _order(bot, sub, status="CANCELLED", commission=10_000, cid="huy")
    done = _callback(bot, USER, "u:o:d:ok").text
    assert "✅ Người mua đã thanh toán đơn" in done and "✅ Đơn hàng đã hoàn thành" in done
    assert "⏳ Chờ Shopee duyệt hoa hồng" in done, "hoàn thành chưa phải đã duyệt"
    cancelled = _callback(bot, USER, "u:o:d:huy").text
    assert "❌ Đơn đã huỷ" in cancelled and "không được tính" in cancelled and "Hoàn tạm tính" not in cancelled
    assert "⏳" not in cancelled, "đơn huỷ không hiện các bước chờ"
    page = bot.handle_text(USER, "b", "/donhang", update_id=805, now=QUOTE_NOW).text
    assert "❌ Không đủ điều kiện hoa hồng" in page and "❌ 1 không đủ điều kiện" in page


def test_19_phan_trang(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    for i in range(12):
        _order(bot, sub, commission=1_000, cid=f"c{i:02d}")
    first = _callback(bot, USER, "u:o:l:1")
    assert "Trang 1/3" in first.text and "u:o:l:2" in str(first.inline_keyboard)
    last = _callback(bot, USER, "u:o:l:3")
    assert "<b>11. Áo Polo Nam</b>" in last.text and "<b>12. Áo Polo Nam</b>" in last.text, "đánh số liên tục qua các trang"
    assert "Trang 3/3" in last.text and sum(d.startswith("u:o:d:") for row in last.inline_keyboard for _l, d in row) == 2
    assert "Trang 3/3" in _callback(bot, USER, "u:o:l:99").text


def test_21_22_khong_xem_duoc_don_nguoi_khac(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), commission=10_000, cid="mine")
    assert _callback(bot, OTHER, "u:o:d:mine").toast == "Không thấy đơn này trong các đơn của bạn."
    assert "Chưa có đơn nào mua qua link" in bot.handle_text(OTHER, "o", "/donhang", update_id=2, now=QUOTE_NOW).text
    assert "Nút này không còn hiệu lực" in _callback(bot, USER, "u:o:d:../x").toast
    group = bot.handle_update({"update_id": 5, "callback_query": {"id": "q", "from": {"id": USER}, "data": "u:o:d:mine",
                                                                   "message": {"message_id": 1, "chat": {"type": "group", "id": -1}}}})[1]
    assert group.text == ""


def test_23_link_chia_se_van_thuoc_nguoi_tao(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)  # USER tạo, người khác mua
    _order(bot, sub, commission=10_000)
    assert "<b>1</b> đơn" in bot.handle_text(USER, "b", "/donhang", update_id=803, now=QUOTE_NOW).text
    assert _events(bot)[0]["chat_id"] == USER


def test_25_snapshot_v12(tmp_path):
    bot = reserve_bot(tmp_path, customer_notifications_enabled=True, allowed_telegram_ids=frozenset({USER}))
    bot.repo.set_state(order_notify.BASELINE_KEY, BASE)
    bot.handle_text(USER, "b", "https://shopee.vn/product/9/8", update_id=1, now=datetime(2026, 10, 23, 9, tzinfo=timezone.utc))
    with bot.repo.connect() as conn:
        sub = conn.execute("SELECT sub_id FROM link_requests").fetchone()[0]
    _order(bot, sub, commission=100_000)
    assert "<b>62.314đ</b>" in _events(bot)[0]["message_html"]


def test_26_link_khong_chung_minh_duoc_chinh_sach(tmp_path):
    bot = _ready(tmp_path)
    bot.handle_text(USER, "b", "/start", update_id=804, now=QUOTE_NOW)
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO link_requests (telegram_update_id, telegram_user_id, sub_id, original_url, affiliate_url, product_name, "
            "price_vnd, estimated_commission, estimated_cashback, cashback_rate_percent, link_status, delivery_status, created_at) "
            "VALUES (900, ?, 'legacyXX', 'x', 'y', 'Áo', 1, 20000, 1, 70, 'created', 'sent', '2026-10-20T08:00:00Z')", (USER,)
        )
    _order(bot, "legacyXX", commission=10_000)
    assert "chưa xác định được" in _events(bot)[0]["message_html"]
    assert "chưa xác định" in _callback(bot, USER, "u:o:d:o1").text


# --- Gửi tin (27–41) ----------------------------------------------------------------------------


def test_27_28_29_su_kien_cung_transaction_va_khong_trung(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    hook = bot.repo.conversion_hooks[0]
    with bot.repo.connect() as conn:
        conn.execute("BEGIN")
        values = {"telegram_user_id": USER, "matched_link_id": 1, "order_sn": "SN9", "order_status": "PENDING",
                  "net_commission_vnd": 1000, "validation_status": "PENDING", "purchase_time": "2026-10-21T00:00:00Z"}
        hook(conn, "rb", None, values, [], "2026-10-24T00:00:00Z")
        conn.rollback()
    assert _events(bot) == [], "rollback thì không có tin"
    _order(bot, sub, commission=10_000)
    with bot.repo.connect() as conn:
        assert order_notify.enqueue_event(conn, event_key="conversion:o1:first_matched", event_type="X", chat_id=USER,
                                          message_html="x", audience="customer", category="order_new") is False


def test_30_36_het_gio_hoac_dung_giua_chung_khong_tu_gui_lai(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), commission=10_000)
    telegram = FakeTelegram([TelegramDeliveryError("ambiguous")])
    assert _flush(bot, telegram).unknown == 1
    _flush(bot, telegram)
    assert telegram.sent == [] and _events(bot)[0]["status"] == "unknown"
    _order(bot, _link(bot), commission=10_000, cid="o2")
    with bot.repo.connect() as conn:
        event_id = conn.execute("SELECT id FROM admin_notifications WHERE event_key = 'conversion:o2:first_matched'").fetchone()[0]
    assert bot.repo.claim_admin_event(event_id)  # gửi dở thì bot dừng
    assert bot.repo.recover_sending() == 1
    _flush(bot, FakeTelegram())
    assert [e["status"] for e in _events(bot)] == ["unknown", "unknown"]


def test_31_32_429_va_5xx_thu_lai_co_gian_cach(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), commission=10_000)
    now = datetime.now(timezone.utc)
    telegram = FakeTelegram([TelegramDeliveryError("rate_limited", retry_after=40, status_code=429)])
    assert _flush(bot, telegram, now).retry == 1
    assert _flush(bot, telegram, now + timedelta(seconds=10)).sent == 0
    assert _flush(bot, telegram, now + timedelta(seconds=41)).sent == 1
    _order(bot, _link(bot), commission=10_000, cid="o2")
    errors = [TelegramDeliveryError("transient", status_code=502)] * 5
    telegram = FakeTelegram(errors)
    for minute in range(0, 40, 1):
        _flush(bot, telegram, now + timedelta(minutes=minute))
    assert _events(bot)[-1]["status"] == "failed" and _events(bot)[-1]["attempt_count"] == 5


def test_33_khach_chan_bot_khong_anh_huong_khach_khac(tmp_path):
    bot = _ready(tmp_path)
    mine = _link(bot)
    _order(bot, mine, commission=10_000, cid="a")
    _order(bot, _link_for(bot, OTHER), commission=10_000, cid="b")
    telegram = FakeTelegram([TelegramDeliveryError("permanent", status_code=403), None])
    result = _flush(bot, telegram)
    assert (result.failed, result.sent) == (1, 1) and telegram.sent[0][0] == OTHER
    _order(bot, mine, commission=10_000, cid="c")  # khách chưa nhắn lại bot
    _flush(bot, FakeTelegram())
    assert _events(bot)[-1]["status"] == "suppressed" and _events(bot)[-1]["last_error"] == "blocked"
    bot.handle_text(USER, "b", "/start", update_id=50, now=QUOTE_NOW)
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT notify_blocked_at FROM telegram_users WHERE telegram_user_id = ?", (USER,)).fetchone()[0] is None


def test_34_khach_chua_bat_dau_bot(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        order_notify.enqueue_event(conn, event_key="k", event_type="ORDER_ORDER_NEW", chat_id=999, message_html="x",
                                   audience="customer", category="order_new")
    _flush(bot, FakeTelegram())
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT status, last_error FROM admin_notifications WHERE event_key = 'k'").fetchone()
    assert tuple(row) == ("suppressed", "not_started")


def test_35_restart_co_tin_cho_gui(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), commission=10_000)
    bot = _ready(tmp_path)
    telegram = FakeTelegram()
    assert _flush(bot, telegram).sent == 1


def test_39_40_tuy_chon_va_co_toan_cuc(tmp_path):
    bot = _ready(tmp_path)
    page = bot.handle_text(USER, "b", "/thongbao", update_id=1, now=QUOTE_NOW)
    assert "✅ 📦 Đơn mới được ghi nhận" in page.text
    off = _callback(bot, USER, "u:n:t:orders")
    assert "⬜ 📦 Đơn mới được ghi nhận" in off.text and "Đã lưu" in off.text
    _order(bot, _link(bot), commission=10_000)
    assert _events(bot)[0]["status"] == "suppressed" and _events(bot)[0]["last_error"] == "pref_off"
    _callback(bot, OTHER, "u:n:t:updates")
    with bot.repo.connect() as conn:
        assert customer_orders.prefs(conn, USER) == {"orders": False, "updates": True, "support": True, "wallet": True}
        assert customer_orders.prefs(conn, OTHER) == {"orders": True, "updates": False, "support": True, "wallet": True}
    bot2 = _ready(tmp_path / "off", enabled=False)
    _order(bot2, _link(bot2), commission=10_000)
    assert _events(bot2)[0]["last_error"] == "feature_off"
    assert "chưa bật gửi thông báo đơn hàng tự động" in bot2.handle_text(USER, "b", "/thongbao", update_id=2, now=QUOTE_NOW).text
    assert _flush(bot2, FakeTelegram(), enabled=True).sent == 0, "bật cờ sau không gửi dồn tin đã bỏ qua"


def test_don_lich_su_truoc_moc_kich_hoat_khong_bao_don_moi(tmp_path):
    bot = _ready(tmp_path)
    bot.repo.set_state(order_notify.BASELINE_KEY, "2026-10-22T00:00:00Z")
    sub = _link(bot)
    _order(bot, sub, commission=10_000)  # mua 21/10, trước mốc
    assert (_events(bot)[0]["status"], _events(bot)[0]["last_error"]) == ("suppressed", "historical")
    _order(bot, sub, status="COMPLETED", commission=10_000)
    assert _events(bot)[-1]["status"] == "pending", "thay đổi thật sau mốc vẫn được xét"


def test_bat_co_lan_dau_dat_moc_kich_hoat(tmp_path):
    bot = _bot(tmp_path, customer_notifications_enabled=True)
    assert bot.repo.get_state(order_notify.BASELINE_KEY) is not None
    bot2 = _bot(tmp_path / "b")
    assert bot2.repo.get_state(order_notify.BASELINE_KEY) is None


def test_tin_qua_cu_khong_gui(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), commission=10_000)
    result = _flush(bot, FakeTelegram(), now=datetime.now(timezone.utc) + timedelta(days=4))
    assert result.suppressed == 1 and _events(bot)[0]["last_error"] == "stale"


# --- Hỗ trợ, tài chính (42–50) ------------------------------------------------------------------


def test_42_43_44_tin_ho_tro_qua_hang_doi_chung(tmp_path):
    bot = _ready(tmp_path, enabled=False)
    _callback(bot, USER, "u:h:c:missing")
    bot.handle_text(USER, "b", "Không thấy đơn", update_id=60, now=QUOTE_NOW)
    bot.admin_panel.handle_callback(ADMIN, "c:hp:r:1", "private", QUOTE_NOW)
    bot.handle_text(ADMIN, "a", "Mình đang kiểm tra", update_id=61, now=QUOTE_NOW)
    with bot.repo.connect() as conn:
        rows = conn.execute("SELECT audience, category, status FROM admin_notifications WHERE event_type = 'SUPPORT_CUSTOMER'").fetchall()
    assert [tuple(r) for r in rows] == [("customer", "support", "pending")]
    telegram = FakeTelegram()
    assert _flush(bot, telegram, enabled=False).sent == 1, "trả lời hỗ trợ không phụ thuộc cờ thông báo đơn"
    assert _flush(bot, telegram, enabled=False).sent == 0


def test_45_46_47_khong_bao_duyet_da_tra_rut_duoc_khi_chua_co_bang_chung(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-21T10:00:00Z")
    bot.refresh_wallet(datetime(2026, 12, 1, tzinfo=timezone.utc))
    with bot.repo.connect() as conn:
        texts = " ".join(r[0] for r in conn.execute("SELECT message_html FROM admin_notifications WHERE chat_id = ?", (USER,)))
    assert "đã được Shopee duyệt" not in texts and "Shopee đã thanh toán hoa hồng" not in texts
    assert "vào ví" not in texts.lower() and "có thể rút: " not in texts.lower()
    approved = order_update_notice("••••0001", statuses=[], ineligible=False, approved=True, old_cashback=None, new_cashback=None)
    assert "đã được Shopee duyệt" in approved and "chưa thanh toán" in approved and "Chưa phải tiền có thể rút" in approved


def test_48_49_50_khong_cham_vi(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-01T00:00:00Z")
    bot.refresh_wallet(datetime(2026, 12, 1, tzinfo=timezone.utc))
    _flush(bot, FakeTelegram())
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM cashback_entries WHERE status = 'available'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM cashback_payouts").fetchone()[0] == 0
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert {"financial_lock_entry_insert", "financial_lock_payout_insert", "financial_lock_payout_progress"} <= triggers
    assert bot.wallet.settings().enabled is False


# --- Màn admin ----------------------------------------------------------------------------------


def test_man_admin_thong_bao_khach(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), commission=10_000)
    _flush(bot, FakeTelegram([TelegramDeliveryError("permanent", status_code=403)]))
    home = bot.admin_panel.handle_callback(ADMIN, "c:nt:home", "private", QUOTE_NOW)
    assert "❌ Gửi lỗi: <b>1</b>" in home.text and "Khách chặn bot: <b>1</b>" in home.text
    failed = bot.admin_panel.handle_callback(ADMIN, "c:nt:l:failed", "private", QUOTE_NOW)
    assert "permanent:403" in failed.text and "c:nt:r:" in str(failed.inline_keyboard)
    event_id = _events(bot)[0]["id"]
    ask = bot.admin_panel.handle_callback(ADMIN, f"c:nt:r:{event_id}", "private", QUOTE_NOW)
    assert "Gửi lại đúng tin" in ask.text and _events(bot)[0]["status"] == "failed"
    bot.admin_panel.handle_callback(ADMIN, f"c:nt:r:{event_id}:ok", "private", QUOTE_NOW)
    assert _events(bot)[0]["status"] == "pending"
    preview = bot.admin_panel.handle_callback(ADMIN, "c:nt:pv", "private", QUOTE_NOW)
    assert "Mẫu tin" in preview.text and "chưa dùng" in preview.text
    assert "chỉ dành cho quản trị" in bot.admin_panel.handle_callback(USER, "c:nt:home", "private", QUOTE_NOW).text
    for data in ("c:nt:send_all", "c:nt:r:abc", "c:nt:l:sent"):
        assert "không còn hiệu lực" in bot.admin_panel.handle_callback(ADMIN, data, "private", QUOTE_NOW).text


def test_migrate_hai_lan_va_cot_moi(tmp_path):
    bot = _ready(tmp_path)
    bot.repo.migrate()
    bot.repo.migrate()
    with bot.repo.connect() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(admin_notifications)")}
        assert {"audience", "category", "next_retry_at", "telegram_message_id", "reply_markup_json", "source_ref"} <= cols
        assert conn.execute("SELECT COUNT(*) FROM customer_notification_prefs").fetchone()[0] == 0


def test_tin_ho_tro_khi_khach_tat_loai_tin(tmp_path):
    bot = _ready(tmp_path)
    bot.handle_text(USER, "b", "/start", update_id=805, now=QUOTE_NOW)
    _callback(bot, USER, "u:n:t:support")
    bot.repo.enqueue_admin_event("support_customer:1:1", "SUPPORT_CUSTOMER", USER, "x")
    _flush(bot, FakeTelegram())
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT status, last_error FROM admin_notifications WHERE event_key = 'support_customer:1:1'").fetchone()
    assert tuple(row) == ("suppressed", "pref_off")
