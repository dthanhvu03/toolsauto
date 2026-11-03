"""Báo cáo sau mỗi buổi live (PLAN-143): ghi số liệu thật theo từng phút để anh học người xem từ chính kênh mình — phút nào,
cảnh nào người ta tặng quà / bình luận / lên xe nhiều.

- Một buổi = cầu nối TikTok «connected»; rớt mạng nối lại trong SESSION_GAP giây vẫn là một buổi.
- Chỉ đếm sự kiện từ TikTok (Hub gọi `raw` ở đường TikTok) — giả lập / bấm thử trên /control không lẫn vào số liệu.
- Ghi SQLite cùng file với hồ sơ khách (`store.DB`), bảng riêng, theo lô ở luồng riêng (Hub.flush) — vòng game không chờ ổ đĩa.
"""

import sqlite3
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import store
from .game.answers import faq, is_question
from .game.parser import normalize, parse

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SESSION_GAP = 120.0  # rớt kết nối quá lâu mới tính là hết buổi
COUNTS = ("comments", "likes", "gifts", "xu", "joins", "follows", "shares", "seats", "queued", "pickups", "delivered",
          "regulars", "newcomers")
PHASE_LABEL = {"BOARDING": "Đón khách ở bến", "DRIVING": "Xe chạy", "REST": "Trạm dừng", "DROPOFF": "Thả khách",
               "FINISH": "Về bến", "SPECIAL": "Chúc Tết"}

SCHEMA = """
-- Bình luận thật (anh 03/11 «tải dữ liệu bình luận về để xem mình nên xử lý những trường hợp nào»): nội dung + game hiểu là
-- gì lúc đó (kind: province / stay / food / where / question / chat…). Chỉ lưu buổi live thật, ở máy anh, không gửi đi đâu.
CREATE TABLE IF NOT EXISTS live_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    ts REAL NOT NULL,
    minute INTEGER NOT NULL,
    phase TEXT NOT NULL,
    uid TEXT NOT NULL,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS live_comments_session ON live_comments (session_id, kind);
CREATE TABLE IF NOT EXISTS live_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started REAL NOT NULL,          -- giờ máy (epoch giây)
    ended REAL NOT NULL,
    username TEXT NOT NULL,
    peak_viewers INTEGER NOT NULL DEFAULT 0,
    uniq_commenters INTEGER NOT NULL DEFAULT 0,
    uniq_gifters INTEGER NOT NULL DEFAULT 0,
    uniq_boarded INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS live_minutes (
    session_id INTEGER NOT NULL,
    minute INTEGER NOT NULL,        -- phút thứ mấy từ lúc bắt đầu buổi
    phase TEXT NOT NULL,            -- cảnh chiếm nhiều nhất trong phút
    viewers INTEGER NOT NULL DEFAULT 0,
    uniq INTEGER NOT NULL DEFAULT 0,  -- người bình luận khác nhau trong phút
    comments INTEGER NOT NULL DEFAULT 0, likes INTEGER NOT NULL DEFAULT 0, gifts INTEGER NOT NULL DEFAULT 0,
    xu INTEGER NOT NULL DEFAULT 0, joins INTEGER NOT NULL DEFAULT 0, follows INTEGER NOT NULL DEFAULT 0,
    shares INTEGER NOT NULL DEFAULT 0, seats INTEGER NOT NULL DEFAULT 0, queued INTEGER NOT NULL DEFAULT 0,
    pickups INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0, regulars INTEGER NOT NULL DEFAULT 0,  -- khách quen (đã gặp buổi trước)
    newcomers INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, minute)
);
-- theo cảnh: sự kiện tính vào ĐÚNG cảnh lúc nó xảy ra (thả khách chỉ vài giây — gán theo phút sẽ mất hẳn cảnh này)
CREATE TABLE IF NOT EXISTS live_phases (
    session_id INTEGER NOT NULL,
    phase TEXT NOT NULL,
    seconds REAL NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0, likes INTEGER NOT NULL DEFAULT 0, gifts INTEGER NOT NULL DEFAULT 0,
    xu INTEGER NOT NULL DEFAULT 0, joins INTEGER NOT NULL DEFAULT 0, seats INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, phase)
);
"""
PHASE_COUNTS = ("comments", "likes", "gifts", "xu", "joins", "seats")


def _int(value, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class LiveLog:
    """Đếm trong bộ nhớ; Hub lấy phần đã đổi bằng `take` để ghi."""

    def __init__(self) -> None:
        self.session: dict | None = None
        self.minutes: dict[int, dict] = {}
        self.dirty: set[int] = set()
        self.phases: dict[int, Counter] = {}
        self.uniq_minute: dict[int, set[str]] = {}
        self.commenters: set[str] = set()
        self.gifters: set[str] = set()
        self.boarded: set[str] = set()
        self.seen: set[str] = set()  # người đã phân loại mới / quen trong buổi
        self.last_connected = 0.0
        self.phase_now = "BOARDING"
        self.phase_stats: dict[str, dict] = {}
        self.last_update: float | None = None
        self.comments: list[dict] = []  # bình luận chờ ghi

    @property
    def active(self) -> bool:
        return self.session is not None

    def _minute(self, now: float) -> dict:
        m = int((now - self.session["started"]) // 60)
        if m not in self.minutes:
            self.minutes[m] = {"minute": m, "viewers": 0, **{k: 0 for k in COUNTS}}
            self.phases[m] = Counter()
            self.uniq_minute[m] = set()
        self.dirty.add(m)
        return self.minutes[m]

    def update(self, connected: bool, username: str, now: float, phase: str, viewers: int) -> None:
        """Mỗi nhịp game: mở / đóng buổi, ghi cảnh đang chiếu và số người xem của phút hiện tại."""
        if connected:
            self.last_connected = now
            if self.session is None:
                self._open(username, now)
            else:
                self.session.pop("closing", None)  # nối lại trước khi kịp ghi lần cuối: vẫn là buổi cũ
        elif self.session is not None and now - self.last_connected > SESSION_GAP:
            self.session["ended"] = self.last_connected
            self.session["closing"] = True
            return
        if self.session is None or not connected:
            self.last_update = None
            return
        if self.last_update is not None:
            self._phase(self.phase_now)["seconds"] += now - self.last_update
        self.last_update = now
        self.phase_now = phase
        self.session["ended"] = now
        row = self._minute(now)
        self.phases[row["minute"]][phase] += 1
        row["viewers"] = max(row["viewers"], viewers)
        self.session["peak_viewers"] = max(self.session["peak_viewers"], viewers)

    def _open(self, username: str, now: float) -> None:
        self.session = {"id": None, "started": now, "ended": now, "username": username, "peak_viewers": 0}
        self.minutes, self.dirty, self.phases, self.uniq_minute = {}, set(), {}, {}
        self.commenters, self.gifters, self.boarded, self.seen = set(), set(), set(), set()
        self.phase_stats, self.last_update = {}, None

    def _phase(self, phase: str) -> dict:
        return self.phase_stats.setdefault(phase, {"seconds": 0.0, **{k: 0 for k in PHASE_COUNTS}})

    def _bump(self, row: dict, key: str, n: int = 1) -> None:
        row[key] += n
        if key in PHASE_COUNTS:
            self._phase(self.phase_now)[key] += n

    def raw(self, event: dict, now: float, returning: bool | None = None) -> None:
        """Sự kiện TikTok (bình luận / tim / quà / vào phòng / follow / share). `returning`: người này đã ghé buổi trước."""
        if self.session is None or self.session.get("closing"):
            return
        uid = str(event.get("uid") or str(event.get("name") or "").strip().lower())
        row = self._minute(now)
        kind = event.get("type")
        if kind == "comment":
            self._bump(row, "comments")
            text = str(event.get("text") or "").strip()[:300]
            if text:
                self.comments.append({"ts": now, "minute": row["minute"], "phase": self.phase_now, "uid": uid,
                                      "name": str(event.get("name") or "")[:60], "text": text, **classify(text)})
            self.uniq_minute[row["minute"]].add(uid)
            self.commenters.add(uid)
        elif kind == "like":
            self._bump(row, "likes", max(1, min(10_000, _int(event.get("count")))))
        elif kind == "gift":
            self._bump(row, "gifts")
            self._bump(row, "xu", max(1, _int(event.get("diamonds"))))
            self.gifters.add(uid)
        elif kind == "join":
            self._bump(row, "joins")
        elif kind == "follow":
            row["follows"] += 1
        elif kind == "share":
            row["shares"] += 1
        if kind != "join" and returning is not None and uid and uid not in self.seen:
            self.seen.add(uid)
            row["regulars" if returning else "newcomers"] += 1

    def game(self, event: dict, now: float) -> None:
        """Sự kiện của game: lên xe / giữ chỗ / bắt dọc đường / về tới quê."""
        if self.session is None or self.session.get("closing"):
            return
        kind = event.get("type")
        if kind == "ticket" and not event.get("changed"):
            row = self._minute(now)
            self._bump(row, "queued" if event.get("next") else "pickups" if event.get("pickup") else "seats")
            self.boarded.add(event.get("name", ""))  # thẻ vé chỉ mang tên hiển thị
        elif kind in ("dropoff", "relief_dropoff"):
            self._minute(now)["delivered"] += len(event.get("people") or [])

    def take(self) -> tuple[dict, list[dict]] | None:
        """(buổi, các phút đã đổi) cần ghi; buổi đã kết thúc thì trả lần cuối rồi quên."""
        if self.session is None:
            return None
        rows = []
        for m in sorted(self.dirty):
            row = dict(self.minutes[m])
            row["phase"] = self.phases[m].most_common(1)[0][0] if self.phases[m] else "BOARDING"
            row["uniq"] = len(self.uniq_minute[m])
            rows.append(row)
        self.dirty = set()
        session = {**self.session, "uniq_commenters": len(self.commenters), "uniq_gifters": len(self.gifters),
                   "uniq_boarded": len(self.boarded), "phases": {k: dict(v) for k, v in self.phase_stats.items()}}
        if self.session.get("closing"):
            self.session = None
        return session, rows

    def take_comments(self) -> list[dict]:
        out, self.comments = self.comments, []
        return out

    def saved(self, session_id: int) -> None:
        if self.session is not None and self.session["id"] is None:
            self.session["id"] = session_id


def classify(text: str) -> dict:
    """Game hiểu bình luận này là gì (cùng bộ đọc với engine): lệnh / tỉnh / câu hỏi có trả lời sẵn / hỏi AI / trò chuyện."""
    cmd = parse(text)
    if cmd.kind != "chat":
        return {"kind": cmd.kind, "detail": cmd.province.name if cmd.province else cmd.item or cmd.station}
    if is_question(text):
        key = faq(text)
        return {"kind": "question", "detail": f"faq:{key}" if key else "ai"}
    return {"kind": "chat", "detail": ""}


class LiveStore:
    def __init__(self, path: Path = store.DB) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)
            self._db.commit()

    def save(self, session: dict, rows: list[dict]) -> int:
        """Ghi / cập nhật một buổi và các phút; trả id buổi."""
        with self._lock:
            fields = (session["ended"], session["peak_viewers"], session["uniq_commenters"], session["uniq_gifters"],
                      session["uniq_boarded"])
            if session["id"] is None:
                cur = self._db.execute(
                    "INSERT INTO live_sessions (started, ended, username, peak_viewers, uniq_commenters, uniq_gifters, "
                    "uniq_boarded) VALUES (?, ?, ?, ?, ?, ?, ?)", (session["started"], fields[0], session["username"],
                                                                    *fields[1:]))
                sid = cur.lastrowid
            else:
                sid = session["id"]
                self._db.execute("UPDATE live_sessions SET ended = ?, peak_viewers = ?, uniq_commenters = ?, uniq_gifters = ?, "
                                 "uniq_boarded = ? WHERE id = ?", (*fields, sid))
            cols = ("minute", "phase", "viewers", "uniq", *COUNTS)
            self._db.executemany(
                f"INSERT INTO live_minutes (session_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))}) "
                f"ON CONFLICT(session_id, minute) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in cols[1:])}",
                [(sid, *(r[c] for c in cols)) for r in rows])
            pcols = ("seconds", *PHASE_COUNTS)
            self._db.executemany(
                f"INSERT INTO live_phases (session_id, phase, {', '.join(pcols)}) VALUES (?, ?, {', '.join('?' * len(pcols))}) "
                f"ON CONFLICT(session_id, phase) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in pcols)}",
                [(sid, phase, *(v[c] for c in pcols)) for phase, v in session.get("phases", {}).items()])
            self._db.commit()
        return sid

    def save_comments(self, session_id: int, comments: list[dict]) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT INTO live_comments (session_id, ts, minute, phase, uid, name, text, kind, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(session_id, c["ts"], c["minute"], c["phase"], c["uid"], c["name"], c["text"], c["kind"], c["detail"])
                 for c in comments])
            self._db.commit()

    def comments(self, session_id: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM live_comments WHERE session_id = ? ORDER BY ts", (session_id,)).fetchall()
        return [dict(r) for r in rows]

    def sessions(self, limit: int = 30) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT s.*, COALESCE(SUM(m.comments), 0) comments, COALESCE(SUM(m.xu), 0) xu, COALESCE(SUM(m.gifts), 0) gifts, "
                "COALESCE(SUM(m.seats + m.pickups), 0) seats, COALESCE(SUM(m.delivered), 0) delivered, "
                "COALESCE(SUM(m.regulars), 0) regulars, COALESCE(SUM(m.newcomers), 0) newcomers, "
                "COALESCE(SUM(m.likes), 0) likes "
                "FROM live_sessions s LEFT JOIN live_minutes m ON m.session_id = s.id GROUP BY s.id "
                "ORDER BY s.started DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def minutes(self, session_id: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM live_minutes WHERE session_id = ? ORDER BY minute", (session_id,)).fetchall()
        return [dict(r) for r in rows]

    def phases(self, session_id: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM live_phases WHERE session_id = ?", (session_id,)).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()


def clock(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, VN).strftime("%d/%m %H:%M")
