"""PLAN-077: điều khoản theo phiên bản, chấp thuận thật, hỗ trợ/khiếu nại, cổng link chưa chứng minh chính sách."""

from __future__ import annotations

import inspect
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cashback_bot import admin_support, customer_desk, support, terms
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_ui import wallet_member_text
from cashback_bot.messages import how_to_calc
from cashback_bot.terms_content import DRAFT_SECTIONS
from cashback_bot.wallet import Balance, BankAccount, PayoutBlocked
from tests.test_cashback_bot import FakeClient, payload, service
from tests.test_cashback_wallet import _financially_ready, _order

ADMIN = 7
BUYER = 111
OTHER = 222
NOW = datetime(2026, 10, 21, 8, 8, tzinfo=timezone.utc)
LINK = "https://shopee.vn/product/9/8"


def _bot(tmp_path, **overrides):
    overrides.setdefault("admin_user_ids", frozenset({ADMIN}))
    overrides.setdefault("allowed_telegram_ids", frozenset({BUYER, OTHER}))
    return service(tmp_path, FakeClient(payload()), **overrides)


def _rows(tmp_path, sql, args=()):
    return sqlite3.connect(tmp_path / "cashback.sqlite").execute(sql, args).fetchall()


def _press(bot, user_id: int, data: str, chat_id: int | None = None, update_id: int = 99):
    update = {
        "update_id": update_id,
        "callback_query": {
            "id": "q", "from": {"id": user_id}, "data": data,
            "message": {"message_id": 5, "chat": {"type": "private", "id": user_id if chat_id is None else chat_id}},
        },
    }
    return bot.handle_update(update)[1]


def _buttons(reply) -> list[str]:
    return [data for row in reply.inline_keyboard or () for _label, data in row]


def _publish_v1(bot, now=NOW) -> int:
    panel = bot.admin_panel
    panel.handle_callback(ADMIN, "c:tm:new", "private", now)
    version_id = _rows(bot_path(bot), "SELECT id FROM customer_terms_versions WHERE version = 'V1'")[0][0]
    confirm = panel.handle_callback(ADMIN, f"c:tm:pub:{version_id}", "private", now)
    ok = [d for d in _buttons(confirm) if d.endswith(":ok")][0]
    panel.handle_callback(ADMIN, ok, "private", now)
    return version_id


def bot_path(bot):
    return Path(bot.settings.db_path).parent


def _counts(tmp_path) -> dict[str, int]:
    tables = (
        "cashback_entries", "cashback_payouts", "shopee_conversions", "shopee_conversion_changes",
        "settlement_batches", "settlement_adjustments", "link_policy_snapshots", "share_policies", "reserve_policies",
    )
    return {name: _rows(tmp_path, f"SELECT COUNT(*) FROM {name}")[0][0] for name in tables}


def _money_state(tmp_path):
    return (
        _rows(tmp_path, "SELECT * FROM cashback_entries ORDER BY conversion_id"),
        _rows(tmp_path, "SELECT conversion_id, validation_status, settlement_status, net_commission_vnd FROM shopee_conversions ORDER BY 1"),
        _rows(tmp_path, "SELECT COUNT(*) FROM cashback_payouts"),
    )


# --- Điều khoản (1–12) ----------------------------------------------------------------------


def test_01_02_tao_ban_nhap_va_cong_bo_sau_khi_xac_nhan_hash(tmp_path):
    bot = _bot(tmp_path)
    home = bot.admin_panel.handle_callback(ADMIN, "c:tm:home", "private", NOW)
    assert "Chưa có điều khoản công bố" in home.text
    assert "c:tm:new" in _buttons(home)
    draft = bot.admin_panel.handle_callback(ADMIN, "c:tm:new", "private", NOW)
    assert "Khách chưa thấy bản nháp" in draft.text
    assert _rows(tmp_path, "SELECT version, status FROM customer_terms_versions") == [("V1", "DRAFT")]
    assert "Để đơn được ghi nhận" in bot.handle_text(BUYER, "b", "/dieukien", update_id=1, now=NOW).text, "nháp chưa hiện cho khách"
    confirm = bot.admin_panel.handle_callback(ADMIN, "c:tm:pub:1", "private", NOW)
    assert "Không gửi tin cho khách" in confirm.text
    assert _rows(tmp_path, "SELECT status FROM customer_terms_versions") == [("DRAFT",)], "bước hỏi lại chưa công bố"
    wrong = bot.admin_panel.handle_callback(ADMIN, "c:tm:pub:1:000000000000:ok", "private", NOW)
    assert "Nội dung đã đổi" in wrong.text
    ok = [d for d in _buttons(confirm) if d.endswith(":ok")][0]
    done = bot.admin_panel.handle_callback(ADMIN, ok, "private", NOW)
    assert "Đã công bố V1" in done.text
    row = _rows(tmp_path, "SELECT status, approved_by, effective_from FROM customer_terms_versions")[0]
    assert row == ("PUBLISHED", f"admin:{ADMIN}", "2026-10-21T08:08:00Z")
    assert _rows(tmp_path, "SELECT COUNT(*) FROM customer_terms_acceptances") == [(0,)], "công bố không ghi chấp thuận"
    assert _rows(tmp_path, "SELECT COUNT(*) FROM admin_notifications WHERE chat_id = ?", (BUYER,)) == [(0,)], "không gửi tin khách"
    hist = bot.admin_panel.handle_callback(ADMIN, "c:menu:hist", "private", NOW)
    assert "Điều khoản: công bố V1" in hist.text and "Điều khoản: tạo bản nháp V1" in hist.text


def test_03_04_khong_sua_khong_xoa_ban_da_cong_bo(tmp_path):
    bot = _bot(tmp_path)
    _publish_v1(bot)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    for sql in (
        "UPDATE customer_terms_versions SET content = 'x'",
        "UPDATE customer_terms_versions SET title = 'x'",
        "UPDATE customer_terms_versions SET effective_from = '2020-01-01T00:00:00Z'",
        "UPDATE customer_terms_versions SET status = 'DRAFT'",
        "DELETE FROM customer_terms_versions",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)


def test_05_06_07_chap_thuan_A_khong_chuyen_sang_B(tmp_path):
    bot = _bot(tmp_path)
    v1 = _publish_v1(bot)
    page = _press(bot, BUYER, "u:p:rules")
    assert f"u:t:ok:{v1}" in _buttons(page)
    accepted = _press(bot, BUYER, f"u:t:ok:{v1}")
    assert accepted.toast == "Đã ghi nhận bạn đồng ý điều khoản."
    assert "Bạn đã đồng ý phiên bản này" in accepted.text
    with bot.repo.connect() as conn:
        v2 = terms.create_draft(conn, "V2", "Điều khoản V2", DRAFT_SECTIONS, "admin:7", NOW)
        terms.publish(conn, v2, terms.get(conn, v2).content_hash, "admin:7", NOW + timedelta(days=1))
    assert _rows(tmp_path, "SELECT id, status FROM customer_terms_versions ORDER BY id") == [(v1, "SUPERSEDED"), (v2, "PUBLISHED")]
    assert _rows(tmp_path, "SELECT terms_version_id FROM customer_terms_acceptances WHERE telegram_user_id = ?", (BUYER,)) == [(v1,)]
    page = bot.handle_text(BUYER, "b", "/dieukien", update_id=5, now=NOW + timedelta(days=1))
    assert "Phiên bản <b>V2</b>" in page.text and "Bạn chưa xác nhận phiên bản này" in page.text
    old = _press(bot, BUYER, f"u:t:ok:{v1}")
    assert "không còn hiện hành" in old.toast
    assert _rows(tmp_path, "SELECT COUNT(*) FROM customer_terms_acceptances") == [(1,)]


def test_08_15_xem_khong_phai_dong_y_va_khong_ghi_thay(tmp_path):
    bot = _bot(tmp_path)
    v1 = _publish_v1(bot)
    bot.handle_text(BUYER, "b", "/dieukien", update_id=1, now=NOW)
    for key, _label, _body in DRAFT_SECTIONS:
        section = _press(bot, BUYER, f"u:t:s:{key}")
        assert "phiên bản V1" in section.text
    assert _rows(tmp_path, "SELECT COUNT(*) FROM customer_terms_acceptances") == [(0,)]
    with bot.repo.connect() as conn:
        with pytest.raises(terms.TermsError):
            terms.accept(conn, BUYER, v1 + 1, "test", NOW)
    again = _press(bot, BUYER, f"u:t:ok:{v1}")
    again2 = _press(bot, BUYER, f"u:t:ok:{v1}")
    assert again2.toast == "Bạn đã đồng ý phiên bản này trước đó."
    assert again.toast != again2.toast
    assert _rows(tmp_path, "SELECT COUNT(*) FROM customer_terms_acceptances") == [(1,)]
    row = _rows(tmp_path, "SELECT terms_hash, acceptance_source FROM customer_terms_acceptances")[0]
    assert row == (_rows(tmp_path, "SELECT content_hash FROM customer_terms_versions")[0][0], "telegram_button")
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM customer_terms_acceptances")


def test_09_18_nguoi_dung_cu_khong_bi_ep_dong_y(tmp_path):
    bot = _bot(tmp_path)
    old = bot.handle_text(BUYER, "b", LINK, update_id=1, now=NOW)
    assert "Đã tạo link" in old.text
    _publish_v1(bot)
    assert bot.settings.terms_required is False
    new = bot.handle_text(BUYER, "b", LINK, update_id=2, now=NOW)
    assert "Đã tạo link" in new.text, "cờ bắt buộc mặc định tắt"
    assert "Hỗ trợ" in bot.handle_text(BUYER, "b", "/hotro", update_id=3, now=NOW).text
    assert _rows(tmp_path, "SELECT COUNT(*) FROM customer_terms_acceptances") == [(0,)]


def test_18_co_bat_buoc_chi_chan_tao_link_moi(tmp_path):
    bot = _bot(tmp_path, terms_required=True)
    assert "Đã tạo link" in bot.handle_text(BUYER, "b", LINK, update_id=1, now=NOW).text, "chưa có bản công bố thì không chặn"
    v1 = _publish_v1(bot)
    blocked = bot.handle_text(BUYER, "b", LINK, update_id=2, now=NOW)
    assert "Cần xác nhận điều khoản" in blocked.text
    assert f"u:t:ok:{v1}" in _buttons(blocked)
    assert _rows(tmp_path, "SELECT COUNT(*) FROM link_requests WHERE link_status = 'created'") == [(1,)]
    assert "Hỗ trợ" in bot.handle_text(BUYER, "b", "/hotro", update_id=3, now=NOW).text
    _press(bot, BUYER, f"u:t:ok:{v1}")
    assert "Đã tạo link" in bot.handle_text(BUYER, "b", LINK, update_id=4, now=NOW).text


def test_10_11_link_moi_ghi_phien_ban_dieu_khoan(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "b", LINK, update_id=1, now=NOW)
    v1 = _publish_v1(bot)
    bot.handle_text(BUYER, "b", LINK, update_id=2, now=NOW)
    _press(bot, BUYER, f"u:t:ok:{v1}")
    bot.handle_text(BUYER, "b", LINK, update_id=3, now=NOW)
    rows = _rows(tmp_path, "SELECT terms_version_id, acceptance_id IS NOT NULL FROM link_terms_context ORDER BY link_id")
    assert rows == [(None, 0), (v1, 0), (v1, 1)]
    with bot.repo.connect() as conn:
        assert terms.link_terms(conn, 1)[0] == "NO_PUBLISHED_TERMS"
        assert terms.link_terms(conn, 3)[0] == "ACCEPTED"
        assert terms.link_terms(conn, 999)[0] == "LEGACY_NOT_RECORDED"
    assert _rows(tmp_path, "SELECT COUNT(*) FROM link_policy_snapshots") == [(3,)], "snapshot tiền vẫn riêng"


def test_12_restart_khong_mat_lich_su(tmp_path):
    bot = _bot(tmp_path)
    v1 = _publish_v1(bot)
    _press(bot, BUYER, f"u:t:ok:{v1}")
    before = _rows(tmp_path, "SELECT * FROM customer_terms_acceptances")
    bot = _bot(tmp_path)
    assert _rows(tmp_path, "SELECT * FROM customer_terms_acceptances") == before
    assert "Bạn đã đồng ý" in bot.handle_text(BUYER, "b", "/dieukien", update_id=9, now=NOW).text


# --- Trải nghiệm khách (13–19) --------------------------------------------------------------


def test_13_14_dieukien_dung_phien_ban_va_khong_hua_rut_tien(tmp_path):
    bot = _bot(tmp_path)
    _publish_v1(bot)
    page = bot.handle_text(BUYER, "b", "/dieukien", update_id=1, now=NOW)
    assert "Phiên bản <b>V1</b> · hiệu lực từ 21/10/2026" in page.text
    assert "Ví hoàn tiền và chi trả chưa mở" in page.text
    body = " ".join(text for _k, _l, text in DRAFT_SECTIONS)
    assert "chưa mở" in body and "không phải</b> số thuế" in body
    assert "không phải số chắc chắn nhận" in body
    for banned in ("sẽ được hoàn", "rút tối thiểu", "trong vòng", "ngày làm việc", "cam kết hoàn", "bảo đảm nhận"):
        assert banned not in body.lower()
    assert "Chia sẻ link không chuyển quyền nhận hoàn tiền" in body
    assert "không có nghĩa</b> là bạn gian lận" in body
    for _key, _label, text in DRAFT_SECTIONS:
        assert len(text) < 3_500


def test_17_bam_dong_y_trong_chat_khac_bi_tu_choi(tmp_path):
    bot = _bot(tmp_path)
    v1 = _publish_v1(bot)
    reply = _press(bot, BUYER, f"u:t:ok:{v1}", chat_id=OTHER)
    assert reply.show_alert and "cuộc trò chuyện riêng" in reply.toast
    assert _rows(tmp_path, "SELECT COUNT(*) FROM customer_terms_acceptances") == [(0,)]
    group = bot.handle_update({
        "update_id": 98,
        "callback_query": {"id": "q", "from": {"id": BUYER}, "data": f"u:t:ok:{v1}",
                           "message": {"message_id": 5, "chat": {"type": "group", "id": -100}}},
    })[1]
    assert group.text == "" and _rows(tmp_path, "SELECT COUNT(*) FROM customer_terms_acceptances") == [(0,)]


def test_19_cachtinh_khong_mau_thuan_dieu_khoan():
    calc = how_to_calc(True)
    terms_text = {key: body for key, _label, body in DRAFT_SECTIONS}["ghi_nhan"]
    # Cùng ba ý: trừ dự phòng phí và thuế, dự phòng không phải thuế khách nộp, link giữ cách tính lúc tạo.
    assert "dự phòng phí và thuế" in calc and "dự phòng phí và thuế" in terms_text
    assert "không phải số thuế bạn phải nộp" in calc and "không phải</b> số thuế bạn phải nộp" in terms_text
    assert "Mỗi link giữ cách tính lúc bot tạo link" in calc and "link cũ vẫn giữ cách tính cũ" in terms_text
    assert "chưa phải tiền đã duyệt hay có thể rút" in calc


# --- Hỗ trợ (20–28) -------------------------------------------------------------------------


def _open(bot, user=BUYER, category="missing", text="Mua áo hôm 20/10 không thấy đơn", update_id=50, now=NOW):
    _press(bot, user, f"u:h:c:{category}")
    return bot.handle_text(user, "buyer", text, update_id=update_id, now=now)


def test_20_21_24_mo_ticket_khong_can_don_va_khong_trung_khi_retry(tmp_path):
    bot = _bot(tmp_path)
    bot.desk.admin_notifier = AdminNotifier(repo=bot.repo, telegram=None, enabled=True, chat_id=ADMIN)
    home = bot.handle_text(BUYER, "b", "/hotro", update_id=1, now=NOW)
    assert all(f"u:h:c:{code}" in _buttons(home) for code in support.CATEGORIES)
    assert "không bao giờ hỏi mật khẩu, OTP" in home.text
    created = _open(bot)
    assert "Đã nhận yêu cầu</b> #1" in created.text
    again = bot.handle_text(BUYER, "buyer", "Mua áo hôm 20/10 không thấy đơn", update_id=50, now=NOW)
    assert _rows(tmp_path, "SELECT COUNT(*) FROM support_tickets") == [(1,)]
    assert "Đã tạo link" not in again.text
    ticket = _rows(tmp_path, "SELECT telegram_user_id, category, link_id, conversion_id, status FROM support_tickets")[0]
    assert ticket == (BUYER, "missing", None, None, "OPEN")
    notices = _rows(tmp_path, "SELECT chat_id, message_html FROM admin_notifications WHERE event_type = 'SUPPORT_TICKET'")
    assert len(notices) == 1 and notices[0][0] == ADMIN and "Yêu cầu hỗ trợ #1" in notices[0][1]


def test_ticket_gan_link_cua_chinh_khach_khong_gan_cua_nguoi_khac(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "b", LINK, update_id=1, now=NOW)
    bot.handle_text(OTHER, "o", LINK, update_id=2, now=NOW)
    mine, theirs = [r[0] for r in _rows(tmp_path, "SELECT sub_id FROM link_requests ORDER BY id")]
    _open(bot, text=f"Link {mine} chưa thấy đơn", update_id=60)
    _open(bot, text=f"Link {theirs} của bạn tôi", update_id=61)
    assert _rows(tmp_path, "SELECT link_id FROM support_tickets ORDER BY id") == [(1,), (None,)]


def test_22_admin_xem_tra_loi_va_doi_trang_thai(tmp_path):
    bot = _bot(tmp_path)
    _open(bot)
    panel = bot.admin_panel
    home = panel.handle_callback(ADMIN, "c:hp:home", "private", NOW)
    assert "🆕 Mới: <b>1</b>" in home.text
    detail = panel.handle_callback(ADMIN, "c:hp:t:1", "private", NOW)
    assert "Mua áo hôm 20/10" in detail.text and "Dữ liệu đối chiếu" in detail.text
    assert {"c:hp:r:1", "c:hp:s:1:IN_REVIEW", "c:hp:s:1:WAITING_SHOPEE", "c:hp:s:1:RESOLVED"} <= set(_buttons(detail))
    panel.handle_callback(ADMIN, "c:hp:s:1:IN_REVIEW", "private", NOW)
    panel.handle_callback(ADMIN, "c:hp:r:1", "private", NOW)
    answered = bot.handle_text(ADMIN, "admin", "Mình đang kiểm tra báo cáo Shopee.", update_id=70, now=NOW)
    assert "Đã gửi trả lời cho khách" in answered.text
    sent = _rows(tmp_path, "SELECT chat_id, message_html FROM admin_notifications WHERE event_type = 'SUPPORT_CUSTOMER'")
    assert [chat for chat, _html in sent] == [BUYER]
    assert "Mình đang kiểm tra báo cáo Shopee." in sent[0][1]
    view = _press(bot, BUYER, "u:h:t:1")
    assert "Hỗ trợ:</b> Mình đang kiểm tra" in view.text


def test_23_khach_khac_khong_xem_duoc_ticket(tmp_path):
    bot = _bot(tmp_path)
    _open(bot)
    assert _press(bot, OTHER, "u:h:t:1").toast == "Không thấy yêu cầu này."
    assert _press(bot, OTHER, "u:h:r:1").toast == "Không thấy yêu cầu này."
    mine = _press(bot, OTHER, "u:h:mine")
    assert "chưa có yêu cầu nào" in mine.text
    with pytest.raises(support.SupportError):
        with bot.repo.connect() as conn:
            support.customer_reply(conn, 1, OTHER, "xin chào", NOW, None)


def test_25_26_cho_shopee_can_ly_do_va_khong_tu_tu_choi(tmp_path):
    bot = _bot(tmp_path)
    _open(bot)
    panel = bot.admin_panel
    ask = panel.handle_callback(ADMIN, "c:hp:s:1:WAITING_SHOPEE", "private", NOW)
    assert "Gõ lý do" in ask.text
    assert _rows(tmp_path, "SELECT status FROM support_tickets") == [("OPEN",)]
    bot.handle_text(ADMIN, "admin", "Đã gửi Shopee kiểm tra đơn", update_id=71, now=NOW)
    assert _rows(tmp_path, "SELECT status FROM support_tickets") == [("WAITING_SHOPEE",)]
    bot = _bot(tmp_path)
    bot.refresh_wallet(NOW + timedelta(days=90))
    assert _rows(tmp_path, "SELECT status FROM support_tickets") == [("WAITING_SHOPEE",)], "không có hẹn giờ tự từ chối"
    with bot.repo.connect() as conn:
        with pytest.raises(support.SupportError):
            support.transition(conn, 1, ADMIN, "REJECTED", "", NOW)
        support.transition(conn, 1, ADMIN, "RESOLVED", "Shopee đã ghi nhận đơn", NOW)
        with pytest.raises(support.SupportError):
            support.transition(conn, 1, ADMIN, "IN_REVIEW", None, NOW)
    events = _rows(tmp_path, "SELECT actor, action, from_status, to_status, note FROM support_ticket_events ORDER BY id")
    assert events[0] == (f"user:{BUYER}", "open", None, "OPEN", None)
    assert events[1] == (f"admin:{ADMIN}", "status", "OPEN", "WAITING_SHOPEE", "Đã gửi Shopee kiểm tra đơn")
    assert events[-1][2:] == ("WAITING_SHOPEE", "RESOLVED", "Shopee đã ghi nhận đơn")
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    for sql in ("UPDATE support_ticket_events SET note = 'x'", "DELETE FROM support_ticket_events", "DELETE FROM support_tickets"):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)


def test_khach_bo_sung_khi_cho_khach(tmp_path):
    bot = _bot(tmp_path)
    _open(bot)
    with bot.repo.connect() as conn:
        support.transition(conn, 1, ADMIN, "WAITING_CUSTOMER", None, NOW)
    _press(bot, BUYER, "u:h:r:1")
    reply = bot.handle_text(BUYER, "b", "Mã đơn 261023CC4UWJ0N", update_id=80, now=NOW)
    assert "Đã gửi bổ sung cho yêu cầu #1" in reply.text
    assert _rows(tmp_path, "SELECT status FROM support_tickets") == [("IN_REVIEW",)]
    bot.handle_text(BUYER, "b", "Mã đơn 261023CC4UWJ0N", update_id=80, now=NOW)
    assert _rows(tmp_path, "SELECT COUNT(*) FROM support_ticket_events WHERE action = 'customer_reply'") == [(1,)]


def test_27_noi_dung_gioi_han_va_che_bi_mat(tmp_path):
    bot = _bot(tmp_path)
    secret = "1234567890:" + "A" * 35
    text = f"thẻ 4111 1111 1111 1234 token {secret} " + "x" * 2_000
    _open(bot, text=text)
    stored = _rows(tmp_path, "SELECT message FROM support_tickets")[0][0]
    assert len(stored) == support.MAX_MESSAGE
    assert "4111" not in stored and "••••1234" in stored
    assert secret not in stored


def test_cho_ho_tro_khong_chan_link_thuan_va_het_han(tmp_path):
    bot = _bot(tmp_path)
    _press(bot, BUYER, "u:h:c:other")
    card = bot.handle_text(BUYER, "b", LINK, update_id=90, now=NOW)
    assert "Đã tạo link" in card.text, "chỉ dán link: tạo link như thường"
    _press(bot, BUYER, "u:h:c:other")
    later = bot.handle_text(BUYER, "b", "câu hỏi", update_id=91, now=datetime.now(timezone.utc) + timedelta(minutes=16))
    assert "Chưa nhận ra link" in later.text
    assert _rows(tmp_path, "SELECT COUNT(*) FROM support_tickets") == [(0,)]


def test_28_34_ticket_khong_cham_tien(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "b", LINK, update_id=1, now=NOW)
    sub = _rows(tmp_path, "SELECT sub_id FROM link_requests")[0][0]
    _order(bot, sub, commission=10_000)
    bot.refresh_wallet(NOW + timedelta(hours=1))
    before = _money_state(tmp_path)
    _open(bot, text=f"Link {sub} số hoàn sai")
    panel = bot.admin_panel
    for data in ("c:hp:home", "c:hp:l:new", "c:hp:t:1", "c:hp:s:1:IN_REVIEW", "c:hp:s:1:RESOLVED"):
        panel.handle_callback(ADMIN, data, "private", NOW)
    bot.handle_text(ADMIN, "admin", "Đã kiểm tra, số đúng theo hoa hồng Shopee", update_id=72, now=NOW)
    assert _rows(tmp_path, "SELECT status FROM support_tickets") == [("RESOLVED",)]
    assert _money_state(tmp_path) == before
    for data in ("c:hp:approve:1", "c:hp:paid:1", "c:hp:commission:1:0", "c:hp:s:1:APPROVED", "c:hp:s:1:SETTLED"):
        assert panel.handle_callback(ADMIN, data, "private", NOW).text == "Nút này không còn hiệu lực."
    source = inspect.getsource(support) + inspect.getsource(admin_support) + inspect.getsource(customer_desk)
    for forbidden in ("UPDATE cashback_entries", "UPDATE shopee_conversions", "cashback_payouts", "validation_status =", "settlement_status ="):
        assert forbidden not in source


def test_admin_chi_tiet_ticket_chi_hien_du_lieu_cua_khach_do(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(OTHER, "o", LINK, update_id=2, now=NOW)
    theirs = _rows(tmp_path, "SELECT sub_id FROM link_requests")[0][0]
    _open(bot)
    detail = bot.admin_panel.handle_callback(ADMIN, "c:hp:t:1", "private", NOW)
    assert theirs not in detail.text and "Khách chưa tạo link nào" in detail.text


# --- Thuế, thu hồi, an toàn tài chính (29–40) -----------------------------------------------


def test_29_30_san_sang_chi_tra_chi_doc_va_van_khoa(tmp_path):
    bot = _bot(tmp_path)
    home = bot.admin_panel.handle_callback(ADMIN, "c:rd:home", "private", NOW)
    assert "Ví và chi trả: <b>KHOÁ</b>" in home.text
    assert "Thuế người nhận: <b>PENDING_REVIEW</b>" in home.text
    assert _buttons(home) == ["c:rd:tax", "c:rd:claw", "c:menu:home"]
    tax = bot.admin_panel.handle_callback(ADMIN, "c:rd:tax", "private", NOW)
    assert "chỉ để <b>ước tính</b> số hoàn, không phải thuế của ai" in tax.text
    claw = bot.admin_panel.handle_callback(ADMIN, "c:rd:claw", "private", NOW)
    assert "không trừ hay thu tiền của khách" in claw.text
    names = {r[0] for r in _rows(tmp_path, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "payout_tax_policies" not in names and "shopee_settlements" not in names
    with pytest.raises(PayoutBlocked):
        bot.wallet.set_enabled(True)


def _legacy_unresolved_link(tmp_path) -> str:
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    conn.execute(
        """
        INSERT INTO link_requests (telegram_update_id, telegram_user_id, sub_id, original_url, affiliate_url, product_name,
            price_vnd, estimated_commission, estimated_cashback, cashback_rate_percent, link_status, delivery_status, created_at)
        VALUES (900, ?, 'legacyXX', ?, 'https://s.shopee.vn/x', 'Áo', 250000, 20000, 15000, 70, 'created', 'sent',
            '2026-10-20T08:00:00Z')
        """,
        (BUYER, LINK),
    )
    conn.commit()
    return "legacyXX"


def test_35_link_unresolved_khong_bao_gio_vao_vi(tmp_path):
    bot = _bot(tmp_path)
    _financially_ready(bot)
    bot.wallet.set_hold_days(0)
    sub = _legacy_unresolved_link(tmp_path)
    bot = _bot(tmp_path)
    assert _rows(tmp_path, "SELECT provenance FROM link_policy_snapshots WHERE link_id = 1") == [("unresolved",)]
    _order(bot, sub, status="COMPLETED", complete="2026-10-22T00:00:00Z", approved=True)
    bot.refresh_wallet(datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert _rows(tmp_path, "SELECT status FROM cashback_entries") == [("holding",)]
    assert _rows(tmp_path, "SELECT link_id FROM link_policy_snapshots") == [(1,)], "không sửa link cũ"
    assert _rows(tmp_path, "SELECT estimated_cashback FROM link_requests WHERE id = 1") == [(15_000,)]


def test_35_doi_chung_link_co_snapshot_van_vao_vi_khi_du_dieu_kien(tmp_path):
    bot = _bot(tmp_path)
    _financially_ready(bot)
    bot.wallet.set_hold_days(0)
    bot.handle_text(BUYER, "b", LINK, update_id=1, now=NOW)
    sub = _rows(tmp_path, "SELECT sub_id FROM link_requests")[0][0]
    _order(bot, sub, status="COMPLETED", complete="2026-10-22T00:00:00Z", approved=True)
    bot.refresh_wallet(datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert _rows(tmp_path, "SELECT status FROM cashback_entries") == [("available",)]


def test_36_40_khong_mo_vi_khong_tao_payout(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "b", LINK, update_id=1, now=NOW)
    sub = _rows(tmp_path, "SELECT sub_id FROM link_requests")[0][0]
    _order(bot, sub, status="COMPLETED", complete="2026-10-01T00:00:00Z")
    bot.refresh_wallet(NOW + timedelta(days=60))
    before = _counts(tmp_path)
    v1 = _publish_v1(bot)
    _press(bot, BUYER, f"u:t:ok:{v1}")
    _open(bot, update_id=55)
    for data in ("c:tm:home", "c:hp:home", "c:hp:t:1", "c:rd:home", "c:rd:tax", "c:rd:claw"):
        bot.admin_panel.handle_callback(ADMIN, data, "private", NOW)
    bot.refresh_wallet(NOW + timedelta(days=61))
    assert _counts(tmp_path) == before
    assert bot.wallet.settings().enabled is False
    assert _rows(tmp_path, "SELECT COUNT(*) FROM cashback_entries WHERE status = 'available'") == [(0,)]
    triggers = {r[0] for r in _rows(tmp_path, "SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert {"financial_lock_entry_insert", "financial_lock_entry_update", "financial_lock_payout_insert", "financial_lock_payout_paid"} <= triggers


# --- Dữ liệu cá nhân ------------------------------------------------------------------------


def test_tin_khong_phai_link_khong_luu_noi_dung(tmp_path):
    bot = _bot(tmp_path)
    text = "số tài khoản của tôi 0123456789 Nguyen Van A"
    bot.handle_text(BUYER, "b", text, update_id=1, now=NOW)
    stored = _rows(tmp_path, "SELECT original_url, reject_reason FROM link_requests")[0]
    assert stored == (f"[không phải link · {len(text)} ký tự]", "invalid_link")
    assert "0123456789" not in stored[0]


def test_admin_xem_khach_che_so_tai_khoan():
    bank = BankAccount("VCB", "0123456789", "NGUYEN VAN A")
    text = wallet_member_text(BUYER, "b", Balance(0, 0, 0, 0), [], bank)
    assert "0123456789" not in text
    assert "••••6789" in text and "NGUYEN VAN A" in text


def test_migrate_hai_lan(tmp_path):
    bot = _bot(tmp_path)
    bot.repo.migrate()
    bot.repo.migrate()
    names = {r[0] for r in _rows(tmp_path, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"customer_terms_versions", "customer_terms_acceptances", "link_terms_context", "support_tickets", "support_ticket_events"} <= names
