"""💰 Tiền & ví: một ảnh chụp tiền (money_flow) cho mọi màn — Ví của anh, Ví khách, Dòng tiền, Kỳ thanh toán."""

from __future__ import annotations

from cashback_bot import money_flow
from tests.test_cashback_payout_lifecycle import T, _available, _ready, _rows
from tests.test_cashback_wallet import ADMIN, _callback, _order


def _bank(bot, received: int, cid: str) -> None:
    """CHỈ DB TEST: kỳ fixture có tiền về ngân hàng và đơn bot `cid` nằm trong kỳ."""
    with bot.repo.connect() as conn:
        batch, evidence = conn.execute("SELECT id, statement_evidence_id FROM settlement_batches").fetchone()
        conn.execute("UPDATE settlement_batches SET bank_received_vnd = ?, shopee_payout_vnd = ? WHERE id = ?",
                     (received, received, batch))
        conn.execute(
            "INSERT INTO settlement_items (batch_id, evidence_id, order_ref, conversion_id, is_bot, settled_vnd, "
            "match_status, created_at) VALUES (?, ?, ?, ?, 1, 0, 'MATCHED', 'x')", (batch, evidence, f"SN-{cid}", cid)
        )
        conn.execute(
            "INSERT INTO settlement_items (batch_id, evidence_id, order_ref, is_bot, settled_vnd, match_status, created_at) "
            "VALUES (?, ?, 'OWNER', 0, 4510, 'NOT_BOT', 'x')", (batch, evidence)
        )


def test_tien_cua_anh_bang_tien_ve_tru_phan_khach(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    _bank(bot, 22_585, "a")
    bot.refresh_wallet(T)
    with bot.repo.connect() as conn:
        position = money_flow.snapshot(conn)
    assert (position.received_vnd, position.customer_vnd, position.owner_vnd) == (22_585, 14_000, 8_585)
    assert (position.own_commission_vnd, position.customers.in_wallet_vnd, position.customers.waiting_vnd) == (4_510, 14_000, 0)
    reply = _callback(bot, ADMIN, "c:wl:own")
    assert "Thực nhận: 8.585đ" in reply.text and "Tiền hoàn khách" in reply.text
    for screen in ("c:menu:money", "c:menu:wallet", "c:in:m:30d"):
        text = _callback(bot, ADMIN, screen).text
        assert "Trong ví: <b>14.000đ</b>" in text, f"{screen}: cùng một số, cùng một tên"
    assert "Thực nhận: <b>8.585đ</b>" in _callback(bot, ADMIN, "c:menu:money").text
    assert "Thực nhận: <b>8.585đ</b>" in _callback(bot, ADMIN, "c:in:m:30d").text


def test_don_bi_tru_lai_thi_phan_anh_tang(tmp_path):
    bot = _ready(tmp_path)
    sub = _available(bot, 20_000, "a")
    _bank(bot, 22_585, "a")
    bot.refresh_wallet(T)
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-21T10:00:00Z", cid="a", approved=True)
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT cashback_vnd FROM cashback_entries WHERE conversion_id = 'a:clawback:1'") == [(-7_000,)]
    with bot.repo.connect() as conn:
        assert money_flow.snapshot(conn).customer_vnd == 7_000


def test_ky_chua_khop_nam_o_sap_ve(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO settlement_batches (period, status, shopee_payout_vnd, created_by, created_at, updated_at) "
            "VALUES ('2026-11', 'EVIDENCE_PENDING', 16392, 'test', 'x', 'x')"
        )
        position = money_flow.snapshot(conn)
    [soon] = position.upcoming
    assert (soon.period, soon.amount_vnd, soon.customer_vnd, soon.received_vnd) == ("2026-11", 16_392, 0, None)
    assert "Kỳ 2026-11 (chưa về): thuế chưa rõ = <b>16.392đ</b>" in _callback(bot, ADMIN, "c:wl:own").text
    money = _callback(bot, ADMIN, "c:menu:money").text
    assert "Sắp về: ~16.392đ (kỳ 2026-11)" in money and "Kỳ 2026-11: tiền về 16.392đ thì xác nhận" in money
    assert "Kỳ 2026-11: tiền về 16.392đ thì xác nhận" in _callback(bot, ADMIN, "c:menu:home").text


def test_du_hoa_hong_phi_thue_va_thuc_nhan(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    _bank(bot, 22_585, "a")
    with bot.repo.connect() as conn:
        conn.execute("UPDATE settlement_batches SET reported_commission_vnd = 25371, fee_vnd = 248, tax_withheld_vnd = 2538")
        conn.execute("UPDATE settlement_items SET settled_vnd = 20861 WHERE order_ref = 'SN-a'")
    bot.refresh_wallet(T)
    with bot.repo.connect() as conn:
        position = money_flow.snapshot(conn)
    assert (position.commission_vnd, position.fee_vnd, position.tax_vnd) == (25_371, 248, 2_538)
    assert position.commission_vnd - position.fee_vnd - position.tax_vnd == position.received_vnd
    kept = position.bot_commission_vnd - position.customer_vnd
    assert kept + position.own_commission_vnd - position.fee_vnd - position.tax_vnd == position.owner_vnd
    text = _callback(bot, ADMIN, "c:wl:own").text
    assert "Thuế Shopee giữ" in text and "TNCN + VAT" in text and "= Thực nhận" in text
    detail = _callback(bot, ADMIN, "c:sm:b:1").text
    assert "Tiền hoàn khách của kỳ: <b>14.000đ</b> · phần anh: <b>8.585đ</b>" in detail, "chi tiết kỳ cùng số với Ví của anh"


def test_ky_sap_ve_hien_hoa_hong_phi_thue(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO settlement_batches (period, status, reported_commission_vnd, adjustments_vnd, fee_vnd, "
            "fee_includes_vat, tax_withheld_vnd, shopee_payout_vnd, created_by, created_at, updated_at) "
            "VALUES ('2026-11', 'EVIDENCE_PENDING', 18415, 0, 181, 1, 1842, 16392, 'test', 'x', 'x')"
        )
    text = _callback(bot, ADMIN, "c:wl:own").text
    assert "hoa hồng 18.415đ − phí 181đ − thuế ~1.842đ = <b>16.392đ</b>" in text


def test_don_trong_ky_khop_la_shopee_da_tra_khong_con_can_kiem_tra(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    with bot.repo.connect() as conn:
        conn.execute("UPDATE shopee_conversions SET validation_status = 'NEEDS_REVIEW', review_status = 'needs_review'")
    home = _callback(bot, ADMIN, "c:cv:home").text
    assert f"{'Shopee đã trả':<19}{1:>4}" in home and f"{'Cần kiểm tra':<19}{0:>4}" in home
    detail = _callback(bot, ADMIN, "c:cv:o:a").text
    assert "Duyệt hoa hồng: <b>✅ Shopee đã trả</b>" in detail and "đã trả, kỳ đã khớp" in detail


def test_moi_man_tien_cung_tieu_de_va_quay_ve_tien_va_vi(tmp_path):
    bot = _ready(tmp_path)
    for screen in ("c:wl:own", "c:menu:wallet", "c:sm:home", "c:in:m:30d", "c:menu:moneycfg"):
        reply = _callback(bot, ADMIN, screen)
        assert reply.text.startswith("⚙️ Quản trị › Tiền &amp; ví"), screen
        assert "c:menu:money" in str(reply.inline_keyboard), screen
    for screen in ("c:menu:policy", "c:menu:fee", "c:menu:sim", "c:wl:cfg", "c:in:b", "c:rd:home"):
        reply = _callback(bot, ADMIN, screen)
        assert "Tiền &amp; ví › Cài đặt tiền" in reply.text, screen
        assert "c:menu:moneycfg" in str(reply.inline_keyboard) and "c:menu:home" in str(reply.inline_keyboard), screen
    settings = _callback(bot, ADMIN, "c:menu:settings")
    assert not {"c:menu:policy", "c:menu:fee", "c:rd:home"} & set(str(settings.inline_keyboard).split("'")), (
        "cài đặt tiền chỉ ở một chỗ")
    for screen in ("c:sm:home", "c:menu:wallet", "c:rd:home", "c:cv:home"):
        text = _callback(bot, ADMIN, screen).text
        assert "Ví khách vẫn khoá" not in text and "khoá cũ" not in text and "Quỹ có chứng từ" not in text, screen
