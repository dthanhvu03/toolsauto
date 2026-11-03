"""Mở khoá tài chính theo kỳ đối soát (2026-11-03, chủ bot yêu cầu).

- Khoá cũ đòi bảng nháp `shopee_settlements` / `payout_tax_policies` (migration 007, không bao giờ chạy). Nay khoá
  đọc dữ liệu thật: kỳ đối soát MATCHED + quyết định thuế mới nhất APPROVED. DB cũ được migrate tự thay trigger.
- Shopee không có trường «đã duyệt» trong báo cáo đơn: đơn nằm trong kỳ MATCHED (SETTLED) là bằng chứng duyệt.
- Shopee trừ hoa hồng sau khi đã vào ví: trừ vào ví, được âm (đã có từ PLAN-088, xem test_b4 ở payout_safety).

Mọi dữ liệu «đủ điều kiện» chỉ nằm trong DB test (fixture), không có công tắc bỏ qua trong code.
"""

from __future__ import annotations

import sqlite3

import pytest

from cashback_bot import db
from tests.test_cashback_payout_lifecycle import ACCOUNT, T, _ready, _rows
from tests.test_cashback_wallet import USER, _bot, _financially_ready, _link, _order

OLD_LOCK = """
CREATE TRIGGER financial_lock_payout_insert BEFORE INSERT ON cashback_payouts
WHEN NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies')
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;
"""


def _settled(bot, cid: str, validation: str, commission: int = 20_000) -> None:
    """Đơn hoàn thành nằm trong kỳ MATCHED, Shopee chưa có trường «đã duyệt» (validation_status giữ nguyên)."""
    _order(bot, _link(bot), status="COMPLETED", commission=commission, complete="2026-10-21T10:00:00Z", cid=cid)
    with bot.repo.connect() as conn:
        conn.execute(
            "UPDATE shopee_conversions SET validation_status = ?, settlement_status = 'SETTLED' WHERE conversion_id = ?",
            (validation, cid),
        )


def test_migrate_thay_khoa_cu_bang_khoa_theo_ky_doi_soat(tmp_path):
    bot = _bot(tmp_path)
    with bot.repo.connect() as conn:  # DB production trước 2026-11-03: trigger đòi bảng nháp
        conn.execute("DROP TRIGGER financial_lock_payout_insert")
        conn.executescript(OLD_LOCK)
    bot.repo.migrate()
    bot.repo.migrate()  # chạy lại không đổi gì
    sql = _rows(bot, "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'financial_lock%'")
    names = {name for name, _ in sql}
    assert set(db.FINANCIAL_LOCK_TRIGGERS) <= names
    assert not [name for name, text in sql if "shopee_settlements" in text or "payout_tax_policies" in text]
    _financially_ready(bot)
    tables = {r[0] for r in _rows(bot, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "shopee_settlements" not in tables and "payout_tax_policies" not in tables
    assert bot.wallet.settings().locked_reasons == ()
    bot.wallet.set_enabled(True)
    assert bot.wallet.settings().enabled is True


def test_chua_co_ky_khop_thi_trigger_van_chan(tmp_path):
    bot = _bot(tmp_path)
    _financially_ready(bot)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE settlement_batches SET status = 'PARTIALLY_MATCHED'")
        with pytest.raises(sqlite3.IntegrityError, match="financial_lock"):
            conn.execute(
                "INSERT INTO cashback_payouts (telegram_user_id, amount_vnd, status, bank_code, account_no, account_name, "
                "created_at) VALUES (?, 1, 'requested', 'MB', '1', 'A', 'x')", (USER,)
            )


@pytest.mark.parametrize("validation", ["NEEDS_REVIEW", "PENDING", "UNKNOWN"])
def test_don_nam_trong_ky_khop_vao_vi_khong_can_approved(tmp_path, validation):
    bot = _ready(tmp_path)
    _settled(bot, "a", validation)
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT status FROM cashback_entries WHERE conversion_id = 'a'") == [("available",)]
    assert bot.wallet.balance(USER).withdrawable_vnd == 14_000


@pytest.mark.parametrize("validation", ["FRAUD", "REJECTED"])
def test_don_gian_lan_hoac_bi_tu_choi_khong_vao_vi_du_settled(tmp_path, validation):
    bot = _ready(tmp_path)
    _settled(bot, "a", validation)
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT status FROM cashback_entries WHERE conversion_id = 'a'") == [("cancelled",)]


def test_don_chua_vao_ky_khop_van_dang_giu(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), status="COMPLETED", commission=20_000, complete="2026-10-21T10:00:00Z", cid="a")
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT status FROM cashback_entries WHERE conversion_id = 'a'") == [("holding",)]


def test_quy_chi_lay_phan_don_bot_tru_phi_thue(tmp_path):
    """Kỳ #1 thật: đơn bot 20.861đ, đơn riêng chủ bot 4.510đ, phí 248đ, thuế 2.538đ → quỹ 18.075đ."""
    bot = _ready(tmp_path, fund=20_861)
    with bot.repo.connect() as conn:
        batch, evidence = conn.execute("SELECT id, statement_evidence_id FROM settlement_batches").fetchone()
        conn.execute("UPDATE settlement_batches SET fee_vnd = 248, tax_withheld_vnd = 2538 WHERE id = ?", (batch,))
        conn.execute(
            "INSERT INTO settlement_items (batch_id, evidence_id, order_ref, is_bot, settled_vnd, match_status, created_at) "
            "VALUES (?, ?, 'OWNER', 0, 4510, 'NOT_BOT', 'x')", (batch, evidence)
        )
        assert bot.wallet.gate.payout_headroom(conn) == 18_075
    _settled(bot, "a", "NEEDS_REVIEW", commission=40_000)  # khách có 28.000đ, quỹ chỉ 18.075đ
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.balance(USER).withdrawable_vnd == 28_000
    assert bot.wallet.request_payout(USER, T) == (None, "fund")
