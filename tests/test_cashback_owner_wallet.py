"""/admin → 👛 Ví khách → 💼 Ví của anh: tiền Shopee đã về tài khoản chia cho khách và cho chủ bot (chỉ đọc)."""

from __future__ import annotations

from cashback_bot import payouts
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
        position = payouts.owner_position(conn)
    assert (position.received_vnd, position.customer_vnd, position.owner_vnd) == (22_585, 14_000, 8_585)
    assert (position.own_orders_vnd, position.in_wallet_vnd, position.waiting_vnd) == (4_510, 14_000, 0)
    reply = _callback(bot, ADMIN, "c:wl:own")
    assert "Tiền của anh: <b>8.585đ</b>" in reply.text
    assert [line.split() for line in reply.text.splitlines() if line.startswith("Trong ví khách")] == [
        ["Trong", "ví", "khách", "14.000"]]
    assert "c:wl:own" in str(_callback(bot, ADMIN, "c:menu:wallet").inline_keyboard)


def test_don_bi_tru_lai_thi_phan_anh_tang(tmp_path):
    bot = _ready(tmp_path)
    sub = _available(bot, 20_000, "a")
    _bank(bot, 22_585, "a")
    bot.refresh_wallet(T)
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-21T10:00:00Z", cid="a", approved=True)
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT cashback_vnd FROM cashback_entries WHERE conversion_id = 'a:clawback:1'") == [(-7_000,)]
    with bot.repo.connect() as conn:
        assert payouts.owner_position(conn).customer_vnd == 7_000


def test_ky_chua_khop_nam_o_sap_ve(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO settlement_batches (period, status, shopee_payout_vnd, created_by, created_at, updated_at) "
            "VALUES ('2026-11', 'EVIDENCE_PENDING', 16392, 'test', 'x', 'x')"
        )
        position = payouts.owner_position(conn)
    assert position.upcoming == (payouts.OwnerPeriod("2026-11", 16_392, 0, False),)
    assert "Kỳ 2026-11: 16.392đ (chưa về)" in _callback(bot, ADMIN, "c:wl:own").text
