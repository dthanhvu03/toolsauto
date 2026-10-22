"""Reconciliation engine — đối chiếu conversion với cashback DB.

Nguyên tắc:
1. Match chính xác 100% giá trị Sub ID.
2. Không tự đổi chữ hoa/thường.
3. Không cắt hoặc tự nối chuỗi.
4. Không tự gán đơn bằng sản phẩm hoặc thời gian gần nhau.
5. Một Sub ID có thể phát sinh nhiều conversion.
6. Một conversion chỉ được nhận diện một lần theo khóa (source, conversion_id).
7. Không có Sub ID → unmatched.
8. Sub ID không có trong cashback DB → unmatched.
9. Nhiều link_requests cùng sub_id → ambiguous.
10. Không đồng nhất người tạo link với người mua khi chưa có bằng chứng người mua.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from experiments.shopee_conversion_v2.database import ConversionDatabase


@dataclass
class ReconciliationResult:
    """Kết quả đối chiếu tổng hợp."""

    total: int = 0
    matched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    missing_sub_id: int = 0
    errors: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            "total": self.total,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "missing_sub_id": self.missing_sub_id,
            "errors": self.errors,
        }


class CashbackDBReader:
    """Read-only reader cho production cashback.sqlite.

    KHÔNG GHI vào database này.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Cashback DB not found: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def lookup_sub_id(self, sub_id: str) -> list[dict[str, Any]]:
        """Tìm link_requests theo sub_id chính xác."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT sub_id, telegram_user_id, item_id, shop_id,
                       product_name, price_vnd, estimated_commission,
                       estimated_cashback, cashback_rate_percent,
                       link_status, created_at
                FROM link_requests
                WHERE sub_id = ?
                """,
                (sub_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_all_sub_ids(self) -> list[str]:
        """Lấy tất cả sub_id đã tạo."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT sub_id FROM link_requests WHERE sub_id IS NOT NULL").fetchall()
            return [row["sub_id"] for row in rows]
        finally:
            conn.close()

    def verify_readonly(self) -> bool:
        """Xác minh connection là read-only."""
        conn = self._connect()
        try:
            conn.execute("INSERT INTO bot_state (key, value) VALUES ('_test_ro', 'x')")
            conn.execute("DELETE FROM bot_state WHERE key = '_test_ro'")
            conn.commit()
            return False
        except sqlite3.OperationalError:
            return True
        finally:
            conn.close()


class ReconciliationEngine:
    """Đối chiếu conversion records với cashback DB."""

    def __init__(self, conversion_db: ConversionDatabase, cashback_reader: CashbackDBReader | None):
        self.conversion_db = conversion_db
        self.cashback_reader = cashback_reader

    def reconcile_all(self, sync_run_id: int | None = None) -> ReconciliationResult:
        """Đối chiếu tất cả conversion trong prototype DB."""
        result = ReconciliationResult()
        for conv in self.conversion_db.get_all_conversions():
            result.total += 1
            try:
                match = self._match_single(conv)
            except Exception as exc:
                result.errors += 1
                match = {
                    "status": "unmatched",
                    "method": "error",
                    "sub_id": conv.get("sub_id"),
                    "telegram_user_id": None,
                    "notes": f"Reconciliation error for {conv.get('conversion_id')}: {exc}",
                }
            status = match["status"]
            if status == "matched":
                result.matched += 1
            elif status == "ambiguous":
                result.ambiguous += 1
            elif status == "missing_sub_id":
                result.missing_sub_id += 1
            else:
                result.unmatched += 1
            self.conversion_db.save_attribution(
                conversion_db_id=int(conv["id"]),
                source_conversion_id=conv["conversion_id"],
                sub_id=match.get("sub_id"),
                telegram_user_id=match.get("telegram_user_id"),
                match_status=status,
                match_method=match["method"],
                match_notes=match.get("notes"),
                sync_run_id=sync_run_id,
            )
            result.details.append(
                {
                    "conversion_id": conv["conversion_id"],
                    "sub_id": match.get("sub_id"),
                    "telegram_user_id": match.get("telegram_user_id"),
                    "status": status,
                    "method": match["method"],
                    "notes": match.get("notes"),
                }
            )
        return result

    def _match_single(self, conv: dict[str, Any]) -> dict[str, Any]:
        """Đối chiếu một conversion."""
        sub_id = conv.get("sub_id") or ""
        if sub_id == "":
            return {
                "status": "missing_sub_id",
                "method": "no_sub_id",
                "sub_id": None,
                "telegram_user_id": None,
                "notes": "Conversion has no sub_id",
            }
        if sub_id == "----":
            return {
                "status": "missing_sub_id",
                "method": "dash_sub_id",
                "sub_id": sub_id,
                "telegram_user_id": None,
                "notes": "Sub ID is '----' (Shopee placeholder)",
            }
        if self.cashback_reader is None:
            return {
                "status": "unmatched",
                "method": "no_cashback_db",
                "sub_id": sub_id,
                "telegram_user_id": None,
                "notes": "Cashback DB reader not configured",
            }
        matches = self.cashback_reader.lookup_sub_id(sub_id)
        if not matches:
            return {
                "status": "unmatched",
                "method": "sub_id_not_found",
                "sub_id": sub_id,
                "telegram_user_id": None,
                "notes": f"Sub ID '{sub_id}' not found in cashback DB",
            }
        if len(matches) > 1:
            return {
                "status": "ambiguous",
                "method": "multiple_link_requests",
                "sub_id": sub_id,
                "telegram_user_id": None,
                "notes": f"Sub ID '{sub_id}' maps to {len(matches)} link_requests",
            }
        link_req = matches[0]
        return {
            "status": "matched",
            "method": "exact_sub_id",
            "sub_id": sub_id,
            "telegram_user_id": link_req.get("telegram_user_id"),
            "notes": None,
        }
