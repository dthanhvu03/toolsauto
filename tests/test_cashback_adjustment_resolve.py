"""/admin → 💰 Tiền & ví → 💳 Kỳ thanh toán Shopee → 🔍 Khoản chênh lệch: admin đóng điều chỉnh OPEN (2026-11-03)."""

from __future__ import annotations

from tests.test_cashback_payout_lifecycle import T, _available, _ready, _rows
from tests.test_cashback_wallet import ADMIN, _callback


def _open_adjustment(bot, cid: str) -> int:
    """CHỈ DB TEST: đơn đã vào kỳ MATCHED có một điều chỉnh chưa xử lý."""
    with bot.repo.connect() as conn:
        return conn.execute(
            "INSERT INTO settlement_adjustments (conversion_id, old_vnd, new_vnd, delta_vnd, source, source_ref, status, "
            "detected_at) VALUES (?, 1372, 1373, 1, 'settlement_item', '13', 'OPEN', 'x')", (cid,)
        ).lastrowid


def test_dong_dieu_chinh_thi_don_vao_vi(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    adjustment = _open_adjustment(bot, "a")
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT status FROM cashback_entries WHERE conversion_id = 'a'") == [("holding",)]
    screen = _callback(bot, ADMIN, "c:sm:diff")
    assert f"c:sm:adj:{adjustment}" in str(screen.inline_keyboard)
    ask = _callback(bot, ADMIN, f"c:sm:adj:{adjustment}")
    assert "Đóng nghĩa là" in ask.text and f"c:sm:adj:{adjustment}:ok" in str(ask.inline_keyboard)
    assert _rows(bot, "SELECT status FROM settlement_adjustments") == [("OPEN",)], "chưa xác nhận thì chưa đóng"
    done = _callback(bot, ADMIN, f"c:sm:adj:{adjustment}:ok")
    assert "Đã đóng điều chỉnh" in done.text and "c:sm:adj:" not in str(done.inline_keyboard)
    assert _rows(bot, "SELECT status, resolved_by FROM settlement_adjustments") == [("RESOLVED", f"admin:{ADMIN}")]
    assert _rows(bot, "SELECT action FROM settlement_audit WHERE action = 'adjustment_resolve'") == [("adjustment_resolve",)]
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT status FROM cashback_entries WHERE conversion_id = 'a'") == [("available",)]


def test_bam_lai_nut_cu_khong_ghi_hai_lan(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    adjustment = _open_adjustment(bot, "a")
    _callback(bot, ADMIN, f"c:sm:adj:{adjustment}:ok")
    again = _callback(bot, ADMIN, f"c:sm:adj:{adjustment}:ok")
    assert "đã được xử lý trước đó" in again.text
    assert len(_rows(bot, "SELECT 1 FROM settlement_audit WHERE action = 'adjustment_resolve'")) == 1
