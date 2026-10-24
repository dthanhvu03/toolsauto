"""PLAN-075: chứng cứ thanh toán, đối soát kỳ, phân bổ quỹ, điều chỉnh, màn đối soát, khoá tài chính.

Không có mẫu báo cáo Shopee thật: mọi chứng từ là fixture định dạng chuẩn `cashback_settlement_v1`.
SQLite tạm, không gọi Shopee hay Telegram.
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from datetime import datetime, timezone

import pytest

from cashback_bot.commission_validation import PENDING
from cashback_bot.settlement import (
    DISPUTED,
    EVIDENCE_PENDING,
    MATCHED,
    PARTIALLY_MATCHED,
    REVERSED,
    EvidenceError,
    SettlementEngine,
    parse_statement,
)
from cashback_bot.settlement_import import read_evidence_file, run
from cashback_bot.wallet import BankAccount
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _link, _order

NOW = datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc)
# Kỳ chuẩn: đơn bot o1 10.000đ + đơn ngoài bot nb 5.000đ. Phí 147 + VAT 15 (chưa gồm), thuế 1.500.
FEE, VAT, TAX = 147, 15, 1_500
PAYOUT = 15_000 - FEE - VAT - TAX  # 13.338


def _doc(kind: str = "shopee_payment_report", ref: str = "PAY-2026-10", period: str = "2026-10", **extra) -> bytes:
    body = {"format": "cashback_settlement_v1", "kind": kind, "period": period, "document_ref": ref, **extra}
    return json.dumps(body).encode()


def _payment(items=None, payout=PAYOUT, reported=15_000, adjustments=0, fee=FEE, vat=VAT, includes=False, tax=TAX, **extra):
    totals = {
        "reported_commission_vnd": reported, "adjustments_vnd": adjustments, "fee_vnd": fee, "fee_vat_vnd": vat,
        "fee_includes_vat": includes, "tax_withheld_vnd": tax, "payout_vnd": payout,
    }
    items = items if items is not None else [
        {"order_ref": "SN-o1", "settled_vnd": 10_000}, {"order_ref": "SN-nb", "settled_vnd": 5_000}]
    return _doc(totals=totals, items=items, **extra)


def _bank(received=PAYOUT, ref="BANK-TX-1", period="2026-10"):
    return _doc("bank_statement", ref=ref, period=period, bank={"received_vnd": received})


@pytest.fixture
def world(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-05T00:00:00Z", cid="o1")
    _order(bot, None, status="COMPLETED", commission=5_000, complete="2026-10-05T00:00:00Z", cid="nb")
    engine = SettlementEngine(bot.repo, evidence_dir=tmp_path / "evidence")
    return bot, engine


def _matched(bot, engine):
    batch = engine.create_batch("2026-10", "test")
    engine.import_document(batch, _payment(), "test")
    engine.import_document(batch, _bank(), "test")
    return batch


def _conv(bot, cid):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT * FROM shopee_conversions WHERE conversion_id = ?", (cid,)).fetchone()


# --- Chứng cứ -----------------------------------------------------------------------------------


class TestEvidence:
    def test_valid_fixture_reconciles_to_matched(self, world):
        bot, engine = world
        batch = _matched(bot, engine)
        result = engine.evaluate(batch)
        assert result.status == MATCHED and result.discrepancies == ()
        assert (result.bot_vnd, result.non_bot_vnd, result.unknown_vnd, result.unallocated_vnd) == (10_000, 5_000, 0, 0)
        assert result.expected_payout_vnd == PAYOUT and result.eligible_fund_vnd == 10_000
        assert _conv(bot, "o1")["settlement_status"] == "SETTLED"
        with bot.repo.connect() as conn:
            assert {r[0] for r in conn.execute("SELECT verification FROM settlement_evidence")} == {"VERIFIED"}

    def test_missing_evidence_stays_pending(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        assert engine.evaluate(batch).status == EVIDENCE_PENDING
        engine.import_document(batch, _payment(), "test")
        result = engine.evaluate(batch)
        assert result.status == EVIDENCE_PENDING and "NO_BANK" in {d.code for d in result.discrepancies}
        assert _conv(bot, "o1")["settlement_status"] == "NOT_VERIFIED"

    def test_duplicate_evidence_rejected(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _bank(), "test")
        with pytest.raises(EvidenceError, match="slot_taken|duplicate_evidence"):
            engine.import_document(batch, _bank(), "test")
        other = engine.create_batch("2026-10", "test", payment_ref="P2")
        with pytest.raises(EvidenceError, match="duplicate_evidence"):
            engine.import_document(other, _bank(received=1), "test")  # cùng mã chứng từ ngân hàng

    def test_same_period_two_payment_refs_ok_same_ref_rejected(self, world):
        _bot_, engine = world
        engine.create_batch("2026-10", "test", payment_ref="P1")
        engine.create_batch("2026-10", "test", payment_ref="P2")
        with pytest.raises(EvidenceError, match="duplicate_batch"):
            engine.create_batch("2026-10", "test", payment_ref="P1")

    @pytest.mark.parametrize("bad", [-1, 1.5, "13338", True])
    def test_bad_amounts_rejected(self, bad):
        with pytest.raises(EvidenceError, match="amount"):
            parse_statement(_payment(payout=bad))

    @pytest.mark.parametrize("raw", [b"", b"\xff\xfe binary", b"order_sn,commission\nSN,1", b'{"format":"shopee_csv"}',
                                     _doc(ref="../../etc/passwd"), b"x" * 2_000_001])
    def test_forged_or_foreign_files_rejected(self, raw):
        with pytest.raises(EvidenceError):
            parse_statement(raw)

    def test_cli_refuses_symlink_and_non_file(self, tmp_path):
        target = tmp_path / "real.json"
        target.write_bytes(_bank())
        link = tmp_path / "link.json"
        link.symlink_to(target)
        with pytest.raises(EvidenceError, match="not_a_regular_file"):
            read_evidence_file(link)
        with pytest.raises(EvidenceError, match="not_a_regular_file"):
            read_evidence_file(tmp_path)

    def test_period_mismatch_and_duplicate_order_in_document(self, world):
        _b, engine = world
        batch = engine.create_batch("2026-10", "test")
        with pytest.raises(EvidenceError, match="period_mismatch"):
            engine.import_document(batch, _bank(period="2026-09"), "test")
        with pytest.raises(EvidenceError, match="duplicate_order_in_document"):
            parse_statement(_payment(items=[{"order_ref": "A", "settled_vnd": 1}, {"order_ref": "A", "settled_vnd": 1}]))

    def test_evidence_stored_protected_by_hash(self, world, tmp_path):
        _b, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _bank(), "test")
        folder = tmp_path / "evidence"
        (stored,) = list(folder.iterdir())
        assert len(stored.stem) == 64 and stored.read_bytes() == _bank()
        assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700 and stat.S_IMODE(os.stat(stored).st_mode) == 0o600

    def test_unknown_order_in_report(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        items = [{"order_ref": "SN-o1", "settled_vnd": 10_000}, {"order_ref": "SN-ghost", "settled_vnd": 5_000}]
        engine.import_document(batch, _payment(items=items), "test")
        engine.import_document(batch, _bank(), "test")
        result = engine.evaluate(batch)
        assert result.status == PARTIALLY_MATCHED and result.unknown_vnd == 5_000
        assert "ITEM_UNKNOWN_ORDER" in {d.code for d in result.discrepancies}

    def test_supersede_keeps_history(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        first = engine.import_document(batch, _payment(payout=1), "test")
        assert engine.evaluate(batch).status in (EVIDENCE_PENDING, DISPUTED)
        with pytest.raises(EvidenceError, match="slot_taken"):
            engine.import_document(batch, _payment(ref="PAY-2026-10-v2"), "test")
        second = engine.import_document(batch, _payment(ref="PAY-2026-10-v2"), "test", replaces=first)
        engine.import_document(batch, _bank(), "test")
        assert engine.evaluate(batch).status == MATCHED
        with bot.repo.connect() as conn:
            states = dict(conn.execute("SELECT id, verification FROM settlement_evidence").fetchall())
            imports = conn.execute("SELECT COUNT(*) FROM settlement_audit WHERE action = 'evidence_import'").fetchone()[0]
        assert states[first] == "SUPERSEDED" and states[second] == "VERIFIED" and imports == 3


# --- Đối soát và quỹ ---------------------------------------------------------------------------


class TestReconciliation:
    def test_bank_short_and_over_are_disputed(self, world):
        bot, engine = world
        for received, code in ((PAYOUT - 1_000, "BANK_SHORT"), (PAYOUT + 500, "BANK_OVER")):
            batch = engine.create_batch("2026-10", "test", payment_ref=f"P-{code}")
            engine.import_document(batch, _payment(ref=f"PAY-{code}"), "test")
            engine.import_document(batch, _bank(received=received, ref=f"BANK-{code}"), "test")
            result = engine.evaluate(batch)
            assert result.status == DISPUTED and code in {d.code for d in result.discrepancies}
            assert result.eligible_fund_vnd is None

    def test_non_bot_and_unknown_never_in_bot_fund(self, world):
        bot, engine = world
        batch = _matched(bot, engine)
        result = engine.evaluate(batch)
        assert result.non_bot_vnd == 5_000 and result.eligible_fund_vnd == result.bot_vnd == 10_000

    def test_tax_and_fee_vat_in_arithmetic(self, world):
        _b, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _payment(payout=15_000 - FEE - TAX), "test")  # quên trừ VAT
        assert "STATEMENT_ARITHMETIC" in {d.code for d in engine.evaluate(batch).discrepancies}

    def test_fee_including_vat_not_deducted_twice(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _payment(includes=True, payout=15_000 - FEE - TAX), "test")
        engine.import_document(batch, _bank(received=15_000 - FEE - TAX), "test")
        result = engine.evaluate(batch)
        assert result.status == MATCHED and result.expected_payout_vnd == 15_000 - FEE - TAX

    def test_unknown_vat_inclusion_is_incomplete(self, world):
        _b, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _payment(includes=None), "test")
        assert "TOTALS_INCOMPLETE" in {d.code for d in engine.evaluate(batch).discrepancies}

    def test_multiple_payments_in_one_period(self, world):
        bot, engine = world
        first = engine.create_batch("2026-10", "test", payment_ref="P1")
        engine.import_document(first, _payment(ref="PAY-A", items=[{"order_ref": "SN-o1", "settled_vnd": 10_000}],
                                               reported=10_000, fee=0, vat=0, tax=0, payout=10_000), "test")
        engine.import_document(first, _bank(received=10_000, ref="BANK-A"), "test")
        second = engine.create_batch("2026-10", "test", payment_ref="P2")
        engine.import_document(second, _payment(ref="PAY-B", items=[{"order_ref": "SN-nb", "settled_vnd": 5_000}],
                                                reported=5_000, fee=0, vat=0, tax=0, payout=5_000), "test")
        engine.import_document(second, _bank(received=5_000, ref="BANK-B"), "test")
        assert engine.evaluate(first).status == MATCHED and engine.evaluate(second).status == MATCHED

    def test_partial_payment_flagged(self, world):
        _b, engine = world
        batch = engine.create_batch("2026-10", "test")
        items = [{"order_ref": "SN-o1", "settled_vnd": 6_000}, {"order_ref": "SN-nb", "settled_vnd": 5_000}]
        engine.import_document(batch, _payment(items=items, reported=11_000, payout=11_000 - FEE - VAT - TAX), "test")
        engine.import_document(batch, _bank(received=11_000 - FEE - VAT - TAX), "test")
        result = engine.evaluate(batch)
        assert result.status == PARTIALLY_MATCHED and result.review_vnd == 6_000 and result.bot_vnd == 0

    def test_items_exceeding_total_disputed(self, world):
        _b, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _payment(reported=12_000, payout=12_000 - FEE - VAT - TAX), "test")
        result = engine.evaluate(batch)
        assert result.status == DISPUTED and result.unallocated_vnd == -3_000

    def test_total_without_order_breakdown_stays_unallocated(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _payment(items=[]), "test")
        engine.import_document(batch, _bank(), "test")
        result = engine.evaluate(batch)
        assert result.status == PARTIALLY_MATCHED and result.unallocated_vnd == 15_000 and result.bot_vnd == 0
        assert _conv(bot, "o1")["settlement_status"] == "NOT_VERIFIED"  # tổng kỳ không tự gán SETTLED cho đơn

    def test_exact_vnd_integers(self, world):
        bot, engine = world
        batch = _matched(bot, engine)
        result = engine.evaluate(batch)
        assert all(isinstance(v, int) for v in (result.bot_vnd, result.non_bot_vnd, result.expected_payout_vnd))

    def test_duplicate_payment_across_batches_and_adjustment_with_evidence(self, world):
        bot, engine = world
        _matched(bot, engine)
        dup = engine.create_batch("2026-11", "test")
        engine.import_document(dup, _payment(period="2026-11", ref="PAY-2026-11", items=[{"order_ref": "SN-o1", "settled_vnd": 10_000}],
                                             reported=10_000, fee=0, vat=0, tax=0, payout=10_000), "test")
        assert "ITEM_DUPLICATE" in {d.code for d in engine.evaluate(dup).discrepancies}
        adj = engine.create_batch("2026-12", "test")
        engine.import_document(adj, _payment(period="2026-12", ref="PAY-2026-12",
                                             items=[{"order_ref": "SN-o1", "settled_vnd": None, "adjustment_vnd": -2_000}],
                                             reported=0, adjustments=-2_000, fee=0, vat=0, tax=0, payout=0), "test")
        assert engine.scan_adjustments() >= 1
        with bot.repo.connect() as conn:
            row = conn.execute("SELECT old_vnd, new_vnd, delta_vnd, source FROM settlement_adjustments "
                               "WHERE source = 'settlement_item'").fetchone()
        assert tuple(row) == (10_000, 8_000, -2_000, "settlement_item")


# --- Duyệt hoa hồng và điều chỉnh ---------------------------------------------------------------


class TestValidationAndAdjustments:
    def test_validation_report_never_sets_approved(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _doc("shopee_validation_report", ref="VAL-2026-10",
                                           items=[{"order_ref": "SN-o1", "approved_vnd": 10_000}]), "test")
        assert _conv(bot, "o1")["validation_status"] == PENDING  # APPROVED vẫn BLOCKED (ADR-051)
        home = _callback(bot, ADMIN, "c:sm:home")
        assert "10.000đ (chưa đối chiếu)" in home.text

    def test_paid_or_completed_is_not_settled_without_batch(self, world):
        bot, _engine = world
        assert _conv(bot, "o1")["settlement_status"] == "NOT_VERIFIED"
        assert _conv(bot, "o1")["validation_status"] == PENDING

    def test_report_missing_an_order_does_not_delete_it(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _payment(items=[{"order_ref": "SN-nb", "settled_vnd": 5_000}]), "test")
        assert _conv(bot, "o1") is not None and _conv(bot, "o1")["settlement_status"] == "NOT_VERIFIED"

    def test_paid_for_fraud_order_needs_review(self, tmp_path):
        bot = _bot(tmp_path)
        sub = _link(bot)
        _order(bot, sub, status="COMPLETED", commission=0, cid="o1", fraud=True)
        engine = SettlementEngine(bot.repo, evidence_dir=tmp_path / "ev")
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _payment(items=[{"order_ref": "SN-o1", "settled_vnd": 10_000}], reported=10_000,
                                               fee=0, vat=0, tax=0, payout=10_000), "test")
        assert "ITEM_NEEDS_REVIEW" in {d.code for d in engine.evaluate(batch).discrepancies}

    def test_commission_drop_and_fraud_after_settlement_open_one_adjustment_each(self, world):
        bot, engine = world
        _matched(bot, engine)
        sub = _conv(bot, "o1")["sub_id"]
        _order(bot, sub, status="COMPLETED", commission=6_000, complete="2026-10-05T00:00:00Z", cid="o1")
        assert engine.scan_adjustments() == 1
        assert engine.scan_adjustments() == 0  # quét lại không tạo trùng
        _order(bot, sub, status="COMPLETED", commission=0, complete="2026-10-05T00:00:00Z", cid="o1", fraud=True)
        engine.scan_adjustments()
        with bot.repo.connect() as conn:
            rows = conn.execute("SELECT old_vnd, new_vnd, delta_vnd, status FROM settlement_adjustments ORDER BY id").fetchall()
        # Giảm còn 6.000đ: một điều chỉnh. Gian lận (hoa hồng về 0 + FRAUD cùng lần báo): đúng một điều chỉnh nữa.
        assert [tuple(r) for r in rows] == [(10_000, 6_000, -4_000, "OPEN"), (10_000, 0, -10_000, "OPEN")]
        bot.refresh_wallet(NOW)
        assert all(e["status"] != "available" for e in bot.wallet.entries(USER))

    def test_reverse_restores_not_verified(self, world):
        bot, engine = world
        batch = _matched(bot, engine)
        assert engine.reverse(batch, "test", "nhập nhầm").status == REVERSED
        assert _conv(bot, "o1")["settlement_status"] == "NOT_VERIFIED"


# --- An toàn tài chính ---------------------------------------------------------------------------


class TestFinancialSafety:
    def test_matched_batch_never_opens_wallet_or_payout(self, world):
        bot, engine = world
        _matched(bot, engine)
        bot.wallet.set_hold_days(0)
        bot.refresh_wallet(NOW)
        settings = bot.wallet.settings()
        assert settings.enabled is False and settings.locked_reasons
        bot.wallet.save_bank(USER, BankAccount("MB", "0123456789", "NGUYEN VAN A"), NOW)
        assert bot.wallet.request_payout(USER, NOW) == (None, "locked")
        assert "khoá tài chính" in _callback(bot, ADMIN, "c:wl:on:ok").text
        with bot.repo.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM cashback_entries WHERE status = 'available'").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM cashback_payouts").fetchone()[0] == 0
            with pytest.raises(sqlite3.IntegrityError, match="financial_lock"):
                conn.execute("UPDATE cashback_entries SET status = 'available'")
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "shopee_settlements" not in names and "payout_tax_policies" not in names

    def test_admin_only_and_forged_callbacks(self, world):
        bot, engine = world
        batch = _matched(bot, engine)
        assert "chỉ dành cho quản trị" in _callback(bot, USER, "c:sm:home").text
        assert "chỉ dành cho quản trị" in _callback(bot, USER, f"c:sm:rc:{batch}").text
        assert "Không tìm thấy kỳ" in _callback(bot, ADMIN, "c:sm:b:99999").text
        assert "không còn hiệu lực" in _callback(bot, ADMIN, "c:sm:b:1;DROP").text
        assert "không còn hiệu lực" in _callback(bot, ADMIN, "c:sm:paid:1").text  # không có nút đánh dấu đã trả

    def test_audit_is_append_only(self, world):
        bot, engine = world
        _matched(bot, engine)
        with bot.repo.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                conn.execute("UPDATE settlement_audit SET actor = 'x'")
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                conn.execute("DELETE FROM settlement_evidence")

    def test_migration_idempotent(self, world):
        bot, engine = world
        _matched(bot, engine)
        bot.repo.migrate()
        bot.repo.migrate()
        with bot.repo.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM settlement_batches").fetchone()[0] == 1
            triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        assert {"financial_lock_entry_insert", "financial_lock_payout_paid", "settlement_audit_no_update"} <= triggers


# --- Màn admin và công cụ nhập --------------------------------------------------------------------


class TestSettlementScreen:
    def test_home_without_evidence_says_not_verified(self, world):
        bot, _engine = world
        home = _callback(bot, ADMIN, "c:sm:home")
        assert "Chưa có kỳ thanh toán nào" in home.text and "Chưa xác minh" in home.text
        assert "settlement_import" in home.text and "Thuộc đơn Cashback Bot" in home.text
        payout_line = next(line for line in home.text.split("\n") if "Shopee báo thanh toán" in line)
        assert "0đ" not in payout_line
        bot.repo.update_shopee_cookie_status(status="connected")
        shopee = _callback(bot, ADMIN, "c:menu:shopee")
        assert ("🧾 Đối soát thanh toán", "c:sm:home") in [b for row in shopee.inline_keyboard for b in row]

    def test_batch_detail_items_evidence_viewed_and_history(self, world):
        bot, engine = world
        batch = _matched(bot, engine)
        detail = _callback(bot, ADMIN, f"c:sm:b:{batch}")
        assert "✅ Chứng từ khớp" in detail.text and "Đơn qua bot (khớp)" in detail.text and "10.000đ" in detail.text
        assert "chưa phải tiền khách được rút" in detail.text
        items = _callback(bot, ADMIN, f"c:sm:items:{batch}")
        assert "➖ ngoài bot" in items.text and "✅" in items.text
        with bot.repo.connect() as conn:
            evidence_id = conn.execute("SELECT id FROM settlement_evidence LIMIT 1").fetchone()[0]
        seen = _callback(bot, ADMIN, f"c:sm:seen:{evidence_id}")
        assert "chưa phải xác minh" in seen.text and "đã đối chiếu hai nguồn" in seen.text
        history = _callback(bot, ADMIN, "c:sm:h")
        assert "nhập chứng từ" in history.text and "admin đã xem chứng từ" in history.text
        rerun = _callback(bot, ADMIN, f"c:sm:rc:{batch}")
        assert "Đã đối soát lại" in rerun.text

    def test_differences_and_bank_screens(self, world):
        bot, engine = world
        batch = engine.create_batch("2026-10", "test")
        engine.import_document(batch, _payment(), "test")
        engine.import_document(batch, _bank(received=PAYOUT - 1_000), "test")
        assert "lệch -1.000đ" in _callback(bot, ADMIN, "c:sm:bank").text
        assert "🔴 Có chênh lệch" in _callback(bot, ADMIN, "c:sm:diff").text

    def test_cli_flow(self, world, tmp_path):
        bot, _engine = world
        statement = tmp_path / "pay.json"
        statement.write_bytes(_payment())
        bank = tmp_path / "bank.json"
        bank.write_bytes(_bank())
        batch = run(["new-batch", "--period", "2026-10"], bot.repo, actor="cli:test")["batch_id"]
        run(["import", "--batch", str(batch), "--file", str(statement)], bot.repo, actor="cli:test")
        out = run(["import", "--batch", str(batch), "--file", str(bank)], bot.repo, actor="cli:test")
        assert out["status"] == MATCHED
        assert run(["show", "--batch", str(batch)], bot.repo)["bot_vnd"] == 10_000
