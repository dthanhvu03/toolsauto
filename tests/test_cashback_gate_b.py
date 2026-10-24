"""PLAN-079 Gate B pre-activation audit: mốc kích hoạt, ngưỡng, chế độ tài khoản test, tin thử, kiểm tra chỉ đọc.

Dùng Telegram giả lập; không gửi tin thật. Restart được mô phỏng bằng dựng lại service trên cùng DB, hoặc gọi
sync_activation với thời điểm chọn trước khi cần thứ tự thời gian chính xác.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from cashback_bot import gate_b_check, order_notify
from cashback_bot.notify_dispatch import Dispatcher, NotifyConfig
from cashback_bot.order_notify import BASELINE_KEY, HISTORY_KEY, STATE_KEY, significant_change
from cashback_bot.telegram_api import TelegramDeliveryError
from tests.test_cashback_bot import NOW as QUOTE_NOW
from tests.test_cashback_order_notifications import OTHER, FakeTelegram, _events, _link_for
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _link

IDS = frozenset({USER, OTHER})


def _start(tmp_path, enabled=False, test_ids=frozenset()):
    """Một lần khởi động bot trên DB ở tmp_path (gọi lại = restart)."""
    return _bot(tmp_path, allowed_telegram_ids=IDS, customer_notifications_enabled=enabled,
                customer_notification_test_ids=test_ids)


def _restart_at(bot, cfg: NotifyConfig, moment: datetime) -> None:
    """Restart ở thời điểm chọn trước: ghi chế độ / mốc như lúc khởi động và gắn hook theo cờ mới."""
    order_notify.sync_activation(bot.repo, cfg, moment)
    bot.repo.conversion_hooks[:] = [order_notify.make_hook(cfg)]


def _conv(bot, sub, cid="o1", purchase="2026-10-21T09:00:00Z", status="PENDING", commission=10_000):
    bot.repo.record_shopee_conversion(
        conversion_id=cid, sub_id=sub, order_sn=f"SN-{cid}", order_status=status, conversion_status="",
        purchase_time=purchase, gross_commission_vnd=commission, net_commission_vnd=commission,
        raw_json=json.dumps({"top": {}, "order": {"items": [{"is_fraud": 0, "fraud_reason": ""}]}}),
        details={"item_name": "Áo", "gmv_vnd": 250_000, "item_qty": 1, "validation_month": "2026-10"},
    )


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _flush(bot, cfg: NotifyConfig, telegram, now=None, admin=False):
    return Dispatcher(bot.repo, telegram, admin, ADMIN if admin else None, cfg.enabled, cfg.test_ids).flush(
        limit=10, now=now
    )


def _history(bot):
    return json.loads(bot.repo.get_state(HISTORY_KEY) or "[]")


# --- A. Mốc kích hoạt ----------------------------------------------------------------------------


def test_a1_tat_sang_bat_lan_dau_dat_moc_trong_db_va_khong_gui_lich_su(tmp_path):
    off = _start(tmp_path)
    assert off.repo.get_state(STATE_KEY) == "off" and off.repo.get_state(BASELINE_KEY) is None
    sub = _link(off)
    _conv(off, sub, status="UNPAID")  # đơn thật có từ trước khi bật (như 2 đơn production)
    assert [(e["status"], e["last_error"]) for e in _events(off)] == [("suppressed", "feature_off")]

    on = _start(tmp_path, enabled=True)  # restart với cờ bật
    baseline = on.repo.get_state(BASELINE_KEY)
    assert baseline is not None and on.repo.get_state(STATE_KEY) == "on"
    assert [h["mode"] for h in _history(on)] == ["off", "on"] and _history(on)[-1]["baseline"] == baseline
    for _ in range(3):
        _conv(on, sub, status="UNPAID")  # đồng bộ lại y hệt
    assert len(_events(on)) == 1, "không sinh lại tin cho đơn lịch sử"
    assert _flush(on, NotifyConfig(True), FakeTelegram()).sent == 0


def test_a2_restart_khi_dang_bat_giu_nguyen_moc(tmp_path):
    first = _start(tmp_path, enabled=True)
    baseline = first.repo.get_state(BASELINE_KEY)
    first.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")  # như đã bật từ trước
    again = _start(tmp_path, enabled=True)
    assert again.repo.get_state(BASELINE_KEY) == "2026-10-01T00:00:00Z" != baseline
    assert [h["mode"] for h in _history(again)] == ["on"], "restart cùng chế độ không ghi lịch sử mới"


def test_a2b_db_cua_gate_a_co_moc_chua_co_che_do_khong_dat_lai_moc(tmp_path):
    bot = _start(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute("DELETE FROM bot_state WHERE key IN (?, ?)", (STATE_KEY, HISTORY_KEY))
    bot.repo.set_state(BASELINE_KEY, "2026-10-02T00:00:00Z")  # Gate A ghi mốc khi bật, chưa ghi chế độ
    on = _start(tmp_path, enabled=True)
    assert on.repo.get_state(BASELINE_KEY) == "2026-10-02T00:00:00Z"


def test_a3_bat_tat_bat_dat_moc_moi_khong_gui_don_va_tin_luc_tat(tmp_path):
    now = datetime.now(timezone.utc)
    on = NotifyConfig(True)
    bot = _start(tmp_path)
    sub = _link(bot)
    _restart_at(bot, on, now - timedelta(hours=3))
    _conv(bot, sub, cid="a", purchase=_stamp(now - timedelta(hours=2, minutes=50)))
    with bot.repo.connect() as conn:  # tin ghi lúc bật lần 1, bot dừng trước khi kịp gửi
        conn.execute("UPDATE admin_notifications SET created_at = ?", (_stamp(now - timedelta(hours=2, minutes=40)),))
    assert _events(bot)[0]["status"] == "pending"

    _restart_at(bot, NotifyConfig(False), now - timedelta(hours=2))  # tắt; dừng trước vòng gửi đầu tiên
    _conv(bot, sub, cid="b", purchase=_stamp(now - timedelta(minutes=110)))  # mua và đồng bộ lúc tắt
    _restart_at(bot, on, now - timedelta(hours=1))  # bật lại
    assert bot.repo.get_state(BASELINE_KEY) == _stamp(now - timedelta(hours=1))
    _conv(bot, sub, cid="c", purchase=_stamp(now - timedelta(minutes=90)))  # mua lúc tắt, đồng bộ sau khi bật lại
    _conv(bot, sub, cid="d", purchase=_stamp(now - timedelta(minutes=30)))  # mua sau khi bật lại
    telegram = FakeTelegram()
    _flush(bot, on, telegram, now=now + timedelta(minutes=1))
    by_key = {e["event_key"].split(":")[1]: (e["status"], e["last_error"]) for e in _events(bot)}
    assert by_key == {
        "a": ("suppressed", "before_activation"),
        "b": ("suppressed", "feature_off"),
        "c": ("suppressed", "historical"),
        "d": ("sent", None),
    }
    assert len(telegram.sent) == 1
    assert [h["mode"] for h in _history(bot)] == ["off", "on", "off", "on"]


def test_a4_tin_cho_gui_truoc_restart_van_gui_sau_restart(tmp_path):
    bot = _start(tmp_path, enabled=True)
    bot.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")
    _conv(bot, _link(bot))
    again = _start(tmp_path, enabled=True)
    telegram = FakeTelegram()
    assert _flush(again, NotifyConfig(True), telegram).sent == 1 and telegram.sent[0][0] == USER


def test_a5_dong_bo_sat_luc_bat_theo_thoi_diem_mua(tmp_path):
    now = datetime.now(timezone.utc)
    cfg = NotifyConfig(True)
    bot = _start(tmp_path)
    sub = _link(bot)
    _restart_at(bot, cfg, now)
    _conv(bot, sub, cid="truoc", purchase=_stamp(now - timedelta(seconds=1)))
    _conv(bot, sub, cid="sau", purchase=_stamp(now))
    _conv(bot, sub, cid="khongro", purchase=None)
    states = {e["event_key"].split(":")[1]: (e["status"], e["last_error"]) for e in _events(bot)}
    assert states == {
        "truoc": ("suppressed", "historical"),
        "sau": ("pending", None),
        "khongro": ("suppressed", "no_purchase_time"),
    }


def test_a6_don_lich_su_co_thay_doi_moi_sau_khi_bat_thi_bao_cap_nhat(tmp_path):
    off = _start(tmp_path)
    sub = _link(off)
    _conv(off, sub, status="UNPAID")
    on = _start(tmp_path, enabled=True)
    _conv(on, sub, status="PAID")
    update = _events(on)[-1]
    assert (update["category"], update["status"]) == ("order_update", "pending")
    assert "Người mua đã thanh toán đơn" in update["message_html"]


def test_a8_tin_khach_khong_ket_sau_tin_admin_khi_tat_thong_bao_admin(tmp_path):
    bot = _start(tmp_path, enabled=True)
    bot.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")
    for n in range(12):
        bot.repo.enqueue_admin_event(f"admin:{n}", "SYNC_RESULT", ADMIN, "x")
    _conv(bot, _link(bot))
    telegram = FakeTelegram()
    assert _flush(bot, NotifyConfig(True), telegram).sent == 1 and telegram.sent[0][0] == USER
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE status = 'pending' AND audience = 'admin'"
                            ).fetchone()[0] == 12, "tin admin vẫn chờ, không bị đánh dấu gì"


def test_a9_bi_429_dung_vong_gui(tmp_path):
    bot = _start(tmp_path, enabled=True)
    bot.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")
    sub = _link(bot)
    _conv(bot, sub, cid="x1")
    _conv(bot, sub, cid="x2")
    result = _flush(bot, NotifyConfig(True), FakeTelegram([TelegramDeliveryError("rate_limited", retry_after=7)]))
    assert (result.sent, result.retry) == (0, 1)
    first, second = _events(bot)
    assert first["status"] == "retry" and (second["status"], second["attempt_count"]) == ("pending", 0)


# --- B. Ngưỡng ----------------------------------------------------------------------------------


def test_b_nguong_500d_hoac_10_phan_tram_tren_tien_hoan():
    assert significant_change(12_157, 11_657)       # giảm 500đ (4%): đủ theo 500đ
    assert not significant_change(12_157, 11_658)   # giảm 499đ (4%): chưa đủ cả hai
    assert significant_change(960, 864)             # giảm 96đ = 10%: đủ theo 10%
    assert not significant_change(960, 865)         # giảm 95đ (9,9%)
    assert significant_change(0, 500) and not significant_change(0, 499)  # từ 0: chỉ xét 500đ
    assert significant_change(120, 0)               # về 0 luôn báo
    assert not significant_change(None, 5_000) and not significant_change(5_000, None)
    assert not significant_change(7_000, 7_000)


def test_b_don_huy_ngay_lan_dau_khong_hien_so_hoan(tmp_path):
    bot = _start(tmp_path, enabled=True)
    bot.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")
    _conv(bot, _link(bot), status="CANCELLED")
    html = _events(bot)[0]["message_html"]
    assert "không được tính" in html and "Hoàn tạm tính: <b>" not in html and "/hotro" in html


def test_b_trang_thai_quan_trong_khong_phu_thuoc_nguong(tmp_path):
    bot = _start(tmp_path, enabled=True)
    bot.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")
    sub = _link(bot)
    _conv(bot, sub, cid="h", commission=1_000)
    _conv(bot, sub, cid="h", status="CANCELLED", commission=1_000)  # hoa hồng không đổi
    titles = [e["message_html"].split("\n")[0] for e in _events(bot)]
    assert titles[0].startswith("📦") and len(titles) == 2 and "huỷ" in titles[1]


# --- D. Chế độ tài khoản test và tin thử ---------------------------------------------------------


def test_d_che_do_test_chi_gui_tai_khoan_test(tmp_path):
    bot = _start(tmp_path, enabled=True, test_ids=frozenset({OTHER}))
    assert bot.repo.get_state(STATE_KEY) == "test"
    bot.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")
    _conv(bot, _link(bot), cid="that")  # khách thật
    _conv(bot, _link_for(bot, OTHER), cid="test")
    states = {e["chat_id"]: (e["status"], e["last_error"]) for e in _events(bot)}
    assert states == {USER: ("suppressed", "not_test_account"), OTHER: ("pending", None)}
    assert "chưa bật gửi thông báo đơn hàng" in bot.handle_text(USER, "u", "/thongbao", update_id=31, now=QUOTE_NOW).text
    assert "chưa bật" not in bot.handle_text(OTHER, "o", "/thongbao", update_id=32, now=QUOTE_NOW).text


def test_d_test_sang_bat_cho_moi_khach_dat_moc_moi(tmp_path):
    now = datetime.now(timezone.utc)
    bot = _start(tmp_path)
    _restart_at(bot, NotifyConfig(True, frozenset({OTHER})), now - timedelta(hours=1))
    _restart_at(bot, NotifyConfig(True), now)
    assert bot.repo.get_state(BASELINE_KEY) == _stamp(now)
    assert [h["mode"] for h in _history(bot)] == ["off", "test", "on"]


def _smoke(bot, data):
    return bot.admin_panel.handle_callback(ADMIN, data, "private", datetime.now(timezone.utc))


def _smoke_rows(bot):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT * FROM admin_notifications WHERE source_ref = 'smoke' ORDER BY id").fetchall()


def test_d1_d2_d3_tin_thu_dung_tai_khoan_tuy_chon_va_chong_trung(tmp_path):
    bot = _start(tmp_path, enabled=True, test_ids=IDS)
    _link(bot)
    _link_for(bot, OTHER)
    home = _smoke(bot, "c:nt:home")
    assert "THỬ VỚI TÀI KHOẢN TEST" in home.text and "c:nt:s" in str(home.inline_keyboard)
    assert "♻️ Xử lý lại" in str(_smoke(bot, "c:nt:s").inline_keyboard)

    _smoke(bot, f"c:nt:s:n:{USER}")
    telegram = FakeTelegram()
    _flush(bot, NotifyConfig(True, IDS), telegram)
    assert [chat for chat, _html, _m in telegram.sent] == [USER] and "Tin thử" in telegram.sent[0][1]
    repeat = _smoke(bot, f"c:nt:s:r:{USER}")
    assert "Không tạo tin thứ hai" in repeat.text and len(_smoke_rows(bot)) == 1
    assert len(telegram.sent) == 1

    _callback(bot, USER, "u:n:t:orders")  # tài khoản test tắt thông báo đơn mới
    notice = _smoke(bot, f"c:nt:s:n:{USER}")
    assert "khách tắt loại tin" in notice.text
    assert _smoke_rows(bot)[-1]["status"] == "suppressed"

    refused = _smoke(bot, "c:nt:s:n:999")
    assert "Chỉ gửi tin thử" in refused.text and len(_smoke_rows(bot)) == 2


def test_d4_tai_khoan_test_chan_bot_khong_anh_huong_tai_khoan_khac(tmp_path):
    bot = _start(tmp_path, enabled=True, test_ids=IDS)
    _link(bot)
    _link_for(bot, OTHER)
    _smoke(bot, f"c:nt:s:n:{OTHER}")
    _smoke(bot, f"c:nt:s:n:{USER}")
    telegram = FakeTelegram([TelegramDeliveryError("permanent", status_code=403), None])
    _flush(bot, NotifyConfig(True, IDS), telegram)
    assert [chat for chat, _h, _m in telegram.sent] == [USER]
    assert [(r["chat_id"], r["status"]) for r in _smoke_rows(bot)] == [(OTHER, "failed"), (USER, "sent")]
    assert "khách đã chặn bot" in _smoke(bot, f"c:nt:s:n:{OTHER}").text


def test_d_tin_thu_an_khi_khong_co_tai_khoan_test(tmp_path):
    bot = _start(tmp_path, enabled=True)
    assert "c:nt:s" not in str(_smoke(bot, "c:nt:home").inline_keyboard)
    assert "Chưa có CUSTOMER_NOTIFICATIONS_TEST_IDS" in _smoke(bot, "c:nt:s").text
    assert "Chỉ gửi tin thử" in _smoke(bot, f"c:nt:s:n:{USER}").text and _smoke_rows(bot) == []


def test_d_kiem_tra_chi_doc_bat_tin_lot_ra_ngoai_tai_khoan_test(tmp_path):
    bot = _start(tmp_path, enabled=True)
    bot.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")
    db = bot.settings.db_path
    ok = gate_b_check.run(db, frozenset({OTHER}), None)
    assert ok[-1] == "OK" and "financial lock triggers 6/6" in ok and "wallet_enabled=0 available=0 payouts=0" in ok
    _conv(bot, _link(bot))  # cờ bật cho mọi khách: USER có tin chờ gửi
    lines = gate_b_check.run(db, frozenset({OTHER}), None)
    assert "FAIL tin đơn tới khách ngoài danh sách test" in lines
    assert gate_b_check.main(["--db", str(db), "--test-ids", str(OTHER)]) == 1


def test_lich_su_cau_hinh_ghi_tin_thu_va_tin_gioi_thieu_bang_chu(tmp_path):
    bot = _start(tmp_path, enabled=True, test_ids=IDS)
    _link(bot)
    _smoke(bot, f"c:nt:s:n:{USER}")
    _smoke(bot, f"c:nt:s:r:{USER}")
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO admin_change_audit (admin_user_id, action, after_json, result, created_at) "
            "VALUES (?, 'customer_notify_intro', ?, 'applied', '2026-10-24T09:42:09Z')",
            (ADMIN, json.dumps({"chat_id": 5589380966, "key": "orders_intro:5589380966"})),
        )
    text = _smoke(bot, "c:menu:hist").text
    assert "customer_notify_" not in text, "không còn mã kỹ thuật thô"
    assert f"Thông báo khách: tin thử mới tới tài khoản test …{str(USER)[-3:]}" in text
    assert "xử lý lại sự kiện thử (chống trùng)" in text
    assert "tin giới thiệu thông báo đơn tới khách …966" in text and "5589380966" not in text
