"""Nhớ khách qua các buổi live (PLAN-134 D): SQLite riêng của Xe Tết trong `storage/db/` — không đụng DB khác của toolsauto.

Engine không đọc ghi gì: tạo người xem mới thì hỏi `load` (một dòng theo khoá chính, nhanh), đổi gì thì đánh dấu; Hub gom
người đã đổi và gọi `save_many` theo lô mỗi FLUSH_SECONDS giây ở luồng riêng (`asyncio.to_thread`) — vòng game không chờ ổ đĩa.
`storage/` nằm ngoài git nên deploy (`git reset --hard`) không mất dữ liệu.
"""

import os
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = Path(os.getenv("XE_TET_DB") or ROOT / "storage" / "db" / "xe_tet.db")
FLUSH_SECONDS = 30.0

FIELDS = ("name", "home", "trips", "likes", "gifts", "comments", "first_day", "last_day", "days")
SCHEMA = """
CREATE TABLE IF NOT EXISTS viewers (
    uid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    home TEXT,                -- tỉnh đã về lần gần nhất (khoá tỉnh)
    trips INTEGER NOT NULL DEFAULT 0,   -- số chuyến đã về tới quê
    likes INTEGER NOT NULL DEFAULT 0,
    gifts INTEGER NOT NULL DEFAULT 0,   -- tổng xu đã tặng
    comments INTEGER NOT NULL DEFAULT 0,
    first_day TEXT NOT NULL,  -- ngày đầu gặp (YYYY-MM-DD, giờ VN)
    last_day TEXT NOT NULL,
    days INTEGER NOT NULL DEFAULT 1     -- số ngày khác nhau đã ghé live
)
"""


class ViewerStore:
    def __init__(self, path: Path = DB) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)  # đọc ở vòng game, ghi ở luồng to_thread
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(SCHEMA)
            self._db.commit()

    def load(self, uid: str) -> dict | None:
        with self._lock:
            row = self._db.execute(f"SELECT {', '.join(FIELDS)} FROM viewers WHERE uid = ?", (uid,)).fetchone()
        return dict(row) if row else None

    def save_many(self, rows: list[dict]) -> None:
        """Ghi đè hồ sơ (engine giữ bản đầy đủ đã cộng dồn từ `load`)."""
        if not rows:
            return
        cols = ("uid", *FIELDS)
        sql = (f"INSERT INTO viewers ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
               f"ON CONFLICT(uid) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in FIELDS)}")
        with self._lock:
            self._db.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()
