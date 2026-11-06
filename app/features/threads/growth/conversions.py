"""Báo cáo nguồn khách từ Threads (PLAN-158): khách mới vào 2 bot với mã ``?start=threads_…``.

CHỈ ĐỌC DB của bot (mở SQLite ``mode=ro``) — không ghi, không gọi bot. Mã nguồn do bot tự ghi khi khách /start lần đầu
(PLAN-153): Cashbot ``bot_state['src:<telegram_user_id>']``, AI Pass Store ``state['src:<user_id>']``.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.features.threads.growth.config import _ROOT, ABVariant, TargetBot, code_map

logger = logging.getLogger(__name__)

PREFIX = "threads_"


def _db_path(env_key: str, default: str) -> Path:
    raw = (os.getenv(env_key) or default).strip()
    p = Path(raw)
    return p if p.is_absolute() else _ROOT / p


def cashback_db() -> Path:
    return _db_path("CASHBACK_DB_PATH", "./data/cashback.sqlite")


def store_db() -> Path:
    return _db_path("STORE_DB_PATH", "./data/store.sqlite")


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _cashback_rows(path: Path) -> List[Dict[str, Any]]:
    with closing(_ro(path)) as c:
        rows = c.execute(
            """
            SELECT s.value AS code, u.telegram_user_id AS user_id, u.username, u.created_at AS joined_at,
                   u.last_seen_at,
                   (SELECT COUNT(*) FROM link_requests l WHERE l.telegram_user_id = u.telegram_user_id) AS links
            FROM bot_state s
            JOIN telegram_users u ON u.telegram_user_id = CAST(substr(s.key, 5) AS INTEGER)
            WHERE s.key LIKE 'src:%' AND s.value LIKE ?
            """,
            (PREFIX + "%",),
        ).fetchall()
    out = []
    for r in rows:
        links = int(r["links"] or 0)
        out.append({**dict(r), "activity": f"đã gửi {links} link" if links else "mới /start, chưa gửi link",
                    "active": links > 0})
    return out


def _store_rows(path: Path) -> List[Dict[str, Any]]:
    with closing(_ro(path)) as c:
        rows = c.execute(
            """
            SELECT s.value AS code, u.user_id, u.username, u.created_at AS joined_at, u.last_seen_at,
                   (SELECT COALESCE(SUM(t.credited), 0) FROM topups t
                     WHERE t.user_id = u.user_id AND t.status = 'paid') AS topup,
                   (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.user_id) AS orders,
                   (SELECT COALESCE(SUM(o.total), 0) FROM orders o
                     WHERE o.user_id = u.user_id AND COALESCE(o.refunded, 0) = 0) AS spent
            FROM state s
            JOIN users u ON u.user_id = CAST(substr(s.key, 5) AS INTEGER)
            WHERE s.key LIKE 'src:%' AND s.value LIKE ?
            """,
            (PREFIX + "%",),
        ).fetchall()
    out = []
    for r in rows:
        topup, orders, spent = int(r["topup"] or 0), int(r["orders"] or 0), int(r["spent"] or 0)
        parts = []
        if topup:
            parts.append(f"nạp {topup:,}đ".replace(",", "."))
        if orders:
            parts.append(f"{orders} đơn · {spent:,}đ".replace(",", "."))
        out.append({**dict(r), "activity": " · ".join(parts) or "mới /start, chưa nạp", "active": bool(orders or topup)})
    return out


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def report(now: Optional[datetime] = None, cashback_path: Optional[Path] = None,
           store_path: Optional[Path] = None) -> Dict[str, Any]:
    """Khách mới từ Threads theo bot / biến thể + danh sách khách. Lỗi đọc DB một bot không làm hỏng bot kia."""
    now = now or datetime.now(timezone.utc)
    codes = code_map()
    by_variant: Dict[str, Dict[str, Dict[str, int]]] = {
        b.value: {v.value: {"customers": 0, "active": 0} for v in ABVariant} for b in TargetBot
    }
    customers: List[Dict[str, Any]] = []
    errors: List[str] = []
    sources = (
        (TargetBot.CASHBOT, cashback_path or cashback_db(), _cashback_rows),
        (TargetBot.AI_STORE, store_path or store_db(), _store_rows),
    )
    for bot, path, reader in sources:
        if not path.exists():
            errors.append(f"không thấy DB {bot.value}: {path}")
            continue
        try:
            rows = reader(path)
        except sqlite3.Error as exc:
            errors.append(f"đọc DB {bot.value} lỗi: {exc}")
            logger.warning("growth.conversions: %s %s", path, exc)
            continue
        for r in rows:
            code_bot, variant = codes.get(r["code"], (bot, None))
            cust = {
                "bot": code_bot.value, "variant": variant.value if variant else None, "code": r["code"],
                "user_id": r["user_id"], "username": r["username"], "joined_at": r["joined_at"],
                "last_seen_at": r["last_seen_at"], "activity": r["activity"], "active": r["active"],
            }
            customers.append(cust)
            if variant:
                slot = by_variant[code_bot.value][variant.value]
                slot["customers"] += 1
                slot["active"] += 1 if r["active"] else 0
    customers.sort(key=lambda c: c["joined_at"] or "", reverse=True)
    day_ago = now - timedelta(days=1)
    return {
        "total": len(customers),
        "active": sum(1 for c in customers if c["active"]),
        "last_24h": sum(1 for c in customers if (_parse(c["joined_at"]) or now - timedelta(days=99)) >= day_ago),
        "by_variant": by_variant,
        "customers": customers[:100],
        "errors": errors,
    }
