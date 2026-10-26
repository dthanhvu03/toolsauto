"""Thời hạn lưu dữ liệu khách (C2, chủ bot duyệt 2026-10-26). Admin chỉnh ở /admin → 📋 Điều khoản → 🗄.

Chỉ là chính sách: điều khoản (bản nháp V3 trở đi) ghi đúng các mốc này lúc tạo bản nháp. Bot CHƯA tự xoá hay
ẩn danh dữ liệu khi đến hạn; việc đó xoá DB production nên cần chủ bot duyệt riêng.
"""

from __future__ import annotations

import json
import sqlite3

RETENTION_KEY = "retention_policy"
# mã: (nhãn, đơn vị, mặc định, nhỏ nhất, lớn nhất)
FIELDS: dict[str, tuple[str, str, int, int, int]] = {
    "finance_years": ("Sổ ví, yêu cầu rút, chứng từ chuyển khoản", "năm", 10, 5, 20),
    "bank_idle_months": ("Tài khoản ngân hàng chưa từng nhận tiền, kể từ lần cuối dùng bot", "tháng", 24, 1, 120),
    "activity_months": ("Link, click, đơn không phát sinh tiền", "tháng", 24, 3, 120),
    "ticket_months": ("Nội dung yêu cầu hỗ trợ, kể từ khi đóng", "tháng", 24, 3, 120),
}
DEFAULTS = {key: spec[2] for key, spec in FIELDS.items()}


def custom(conn: sqlite3.Connection) -> dict[str, int]:
    """Các mốc admin đã đổi khỏi mặc định. Giá trị hỏng hoặc ngoài khoảng thì bỏ qua."""
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (RETENTION_KEY,)).fetchone()
    try:
        raw = json.loads(row[0]) if row and row[0] else {}
    except ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in FIELDS and isinstance(v, int) and valid(k, v)}


def load(conn: sqlite3.Connection) -> dict[str, int]:
    return {**DEFAULTS, **custom(conn)}


def valid(key: str, value: int) -> bool:
    _label, _unit, _default, low, high = FIELDS[key]
    return low <= value <= high


def period(key: str, value: int) -> str:
    return f"{value} {FIELDS[key][1]}"
