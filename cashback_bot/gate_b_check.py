"""Kiểm tra chỉ đọc cho Gate B PLAN-079: chạy trước và sau buổi thử thông báo đơn với tài khoản test.

    .venv/bin/python -m cashback_bot.gate_b_check --test-ids 123,456 [--since 2026-10-25T02:00:00Z]

Mở DB ở chế độ mode=ro, không ghi gì. In trạng thái cờ / mốc, hàng đợi, kiểm tra nội dung tin khách, tiền và khoá
tài chính; dòng «FAIL» nghĩa là dừng thử và tắt cờ. Mã thoát 1 khi có FAIL. Không in token, nội dung tin hay Sub ID.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from cashback_bot.order_notify import BASELINE_KEY, HISTORY_KEY, STATE_KEY

DEFAULT_DB = Path("data/cashback.sqlite")
FINANCIAL_TRIGGERS = (
    "financial_lock_entry_insert", "financial_lock_entry_update", "financial_lock_payout_insert",
    "financial_lock_payout_paid", "financial_lock_payout_progress", "payout_paid_needs_evidence",
)
# Câu không được có trong tin đơn khi chưa có chứng từ (ví và chi trả đang khoá).
FORBIDDEN = ("đủ điều kiện rút", "có thể rút ngay", "đã chuyển tiền", "tiền sắp về ví", "chắc chắn nhận", "đặt hàng thành công")
APPROVED_TEXT = "đã được Shopee duyệt"


def _state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def run(db: Path, test_ids: frozenset[int], since: str | None) -> list[str]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out: list[str] = []
    fails: list[str] = []
    try:
        history = json.loads(_state(conn, HISTORY_KEY) or "[]")
        out.append(f"mode={_state(conn, STATE_KEY) or '-'} baseline={_state(conn, BASELINE_KEY) or '-'}")
        out += [f"  history {h.get('at')} {h.get('mode')} baseline={h.get('baseline')}" for h in history[-5:]]

        for row in conn.execute(
            "SELECT audience, status, COUNT(*) AS n FROM admin_notifications GROUP BY 1, 2 ORDER BY 1, 2"
        ):
            out.append(f"queue {row['audience']}/{row['status']}={row['n']}")
        for row in conn.execute(
            "SELECT status, COALESCE(last_error, '-') AS why, COUNT(*) AS n FROM admin_notifications "
            "WHERE audience = 'customer' AND category LIKE 'order_%' GROUP BY 1, 2 ORDER BY 1, 2"
        ):
            out.append(f"orders {row['status']} ({row['why']})={row['n']}")

        window = since or _state(conn, BASELINE_KEY) or "9999"
        if test_ids:
            marks = ", ".join("?" for _ in test_ids)
            leaked = int(conn.execute(
                f"SELECT COUNT(*) FROM admin_notifications WHERE audience = 'customer' AND category LIKE 'order_%' "
                f"AND status IN ('pending', 'retry', 'sending', 'sent', 'unknown') AND created_at >= ? "
                f"AND chat_id NOT IN ({marks})",
                (window, *sorted(test_ids)),
            ).fetchone()[0])
            out.append(f"order notices to non-test accounts since {window}: {leaked}")
            if leaked:
                fails.append("tin đơn tới khách ngoài danh sách test")

        dupes = int(conn.execute(
            "SELECT COUNT(*) FROM (SELECT source_ref FROM admin_notifications WHERE category = 'order_new' "
            "AND source_ref LIKE 'conversion:%' GROUP BY source_ref HAVING COUNT(*) > 1)"
        ).fetchone()[0])
        out.append(f"conversions with more than one «new order» event: {dupes}")
        if dupes:
            fails.append("một đơn có hơn một sự kiện «đơn mới»")

        bad_text = 0
        bad_approved = 0
        for row in conn.execute(
            "SELECT n.message_html, n.source_ref, c.validation_status FROM admin_notifications n "
            "LEFT JOIN shopee_conversions c ON 'conversion:' || c.conversion_id = n.source_ref "
            "WHERE n.audience = 'customer' AND n.category LIKE 'order_%'"
        ):
            text = str(row["message_html"] or "")
            bad_text += any(phrase in text for phrase in FORBIDDEN)
            bad_approved += APPROVED_TEXT in text and row["source_ref"] != "smoke" and row["validation_status"] != "APPROVED"
        out.append(f"order notices with withdraw/paid wording: {bad_text}; «approved» without APPROVED: {bad_approved}")
        if bad_text or bad_approved:
            fails.append("tin đơn có câu chữ tiền / duyệt khi chưa có chứng cứ")

        for row in conn.execute(
            "SELECT status, COUNT(*) AS n, COALESCE(SUM(cashback_vnd), 0) AS total FROM cashback_entries GROUP BY 1 ORDER BY 1"
        ):
            out.append(f"entries {row['status']}: {row['n']} · {row['total']}đ")
        amounts = [int(r[0]) for r in conn.execute("SELECT cashback_vnd FROM cashback_entries ORDER BY cashback_vnd DESC")]
        out.append("entry amounts: " + ", ".join(f"{a}đ" for a in amounts))
        available = int(conn.execute("SELECT COUNT(*) FROM cashback_entries WHERE status = 'available'").fetchone()[0])
        payouts = int(conn.execute("SELECT COUNT(*) FROM cashback_payouts").fetchone()[0])
        wallet = _state(conn, "wallet_enabled") or "0"
        out.append(f"wallet_enabled={wallet} available={available} payouts={payouts}")
        if wallet != "0" or available or payouts:
            fails.append("ví / khoản rút / lệnh chi khác 0")
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        missing = [name for name in FINANCIAL_TRIGGERS if name not in names]
        out.append(f"financial lock triggers {len(FINANCIAL_TRIGGERS) - len(missing)}/{len(FINANCIAL_TRIGGERS)}")
        if missing:
            fails.append("thiếu trigger khoá tài chính: " + ", ".join(missing))
        check = conn.execute("PRAGMA quick_check").fetchone()[0]
        out.append(f"quick_check={check}")
        if check != "ok":
            fails.append("quick_check lỗi")
    finally:
        conn.close()
    out += [f"FAIL {reason}" for reason in fails] or ["OK"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--test-ids", default="", help="ID Telegram tài khoản test, cách nhau dấu phẩy")
    parser.add_argument("--since", default=None, help="mốc ISO UTC để đếm tin đơn ngoài danh sách test")
    args = parser.parse_args(argv)
    ids = frozenset(int(part) for part in args.test_ids.replace(";", ",").split(",") if part.strip().isdigit())
    lines = run(args.db, ids, args.since)
    print("\n".join(lines))
    return 1 if any(line.startswith("FAIL") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
