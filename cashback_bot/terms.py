"""Điều khoản khách theo phiên bản (PLAN-077, ADR-054).

- Bản nháp (DRAFT) sửa được; công bố (PUBLISHED) thì đóng băng nội dung, ngày hiệu lực, người duyệt.
  Mỗi lúc chỉ một bản PUBLISHED; công bố bản mới thì bản cũ thành SUPERSEDED (trigger chặn đi lùi).
- Chấp thuận chỉ ghi khi khách bấm đồng ý đúng bản đang công bố, kèm hash nội dung đã thấy. Không chuyển
  chấp thuận từ bản cũ sang bản mới, không ghi thay khách.
- Mỗi link mới ghi bản điều khoản đang công bố (và lần chấp thuận của người tạo, nếu có). Link cũ để trống.
Module này không đụng tiền, sổ ví, trạng thái hoa hồng hay payout.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

DRAFT = "DRAFT"
PUBLISHED = "PUBLISHED"
SUPERSEDED = "SUPERSEDED"


class TermsError(ValueError):
    """Thao tác điều khoản không hợp lệ. Mã lỗi ở args[0]."""


@dataclass(frozen=True)
class TermsVersion:
    id: int
    version: str
    title: str
    sections: tuple[tuple[str, str, str], ...]
    content_hash: str
    status: str
    effective_from: str | None
    approved_by: str | None
    published_at: str | None
    created_at: str

    def section(self, key: str) -> tuple[str, str, str] | None:
        return next((item for item in self.sections if item[0] == key), None)


def _stamp(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def encode(title: str, sections) -> tuple[str, str]:
    """(nội dung JSON chuẩn, sha256). Hash phủ cả tiêu đề để khách đồng ý đúng văn bản đã thấy."""
    content = json.dumps([list(item) for item in sections], ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()
    return content, digest


def _from_row(row: sqlite3.Row) -> TermsVersion:
    sections = tuple(tuple(item) for item in json.loads(row["content"]))
    return TermsVersion(
        int(row["id"]), str(row["version"]), str(row["title"]), sections, str(row["content_hash"]),
        str(row["status"]), row["effective_from"], row["approved_by"], row["published_at"], str(row["created_at"]),
    )


def get(conn: sqlite3.Connection, version_id: int) -> TermsVersion | None:
    row = conn.execute("SELECT * FROM customer_terms_versions WHERE id = ?", (version_id,)).fetchone()
    return None if row is None else _from_row(row)


def current(conn: sqlite3.Connection, now: datetime) -> TermsVersion | None:
    """Bản đang công bố và đã tới ngày hiệu lực. None: chưa có điều khoản công bố."""
    row = conn.execute(
        "SELECT * FROM customer_terms_versions WHERE status = 'PUBLISHED' AND effective_from <= ?",
        (_stamp(now),),
    ).fetchone()
    return None if row is None else _from_row(row)


def versions(conn: sqlite3.Connection) -> list[TermsVersion]:
    rows = conn.execute("SELECT * FROM customer_terms_versions ORDER BY id DESC").fetchall()
    return [_from_row(row) for row in rows]


def create_draft(conn: sqlite3.Connection, version: str, title: str, sections, actor: str, now: datetime) -> int:
    if not version.strip() or not title.strip() or not sections:
        raise TermsError("empty")
    if conn.execute("SELECT 1 FROM customer_terms_versions WHERE version = ?", (version,)).fetchone():
        raise TermsError("version_exists")
    content, digest = encode(title, sections)
    cursor = conn.execute(
        """
        INSERT INTO customer_terms_versions (version, title, content, content_hash, status, created_by, created_at)
        VALUES (?, ?, ?, ?, 'DRAFT', ?, ?)
        """,
        (version, title, content, digest, actor, _stamp(now)),
    )
    return int(cursor.lastrowid)


def publish(conn: sqlite3.Connection, version_id: int, expected_hash: str, actor: str, now: datetime) -> TermsVersion:
    """Công bố bản nháp, hiệu lực ngay. expected_hash: hash admin đã xem lúc bấm, khác thì từ chối."""
    started = not conn.in_transaction
    if started:
        conn.execute("BEGIN IMMEDIATE")
    try:
        found = get(conn, version_id)
        if found is None:
            raise TermsError("not_found")
        if found.status != DRAFT:
            raise TermsError("not_draft")
        if found.content_hash != expected_hash:
            raise TermsError("hash_changed")
        stamp = _stamp(now)
        conn.execute("UPDATE customer_terms_versions SET status = 'SUPERSEDED' WHERE status = 'PUBLISHED'")
        conn.execute(
            """
            UPDATE customer_terms_versions
            SET status = 'PUBLISHED', effective_from = ?, approved_by = ?, published_at = ?
            WHERE id = ? AND status = 'DRAFT'
            """,
            (stamp, actor, stamp, version_id),
        )
        if started:
            conn.commit()
    except BaseException:
        if started:
            conn.rollback()
        raise
    return get(conn, version_id)  # type: ignore[return-value]


def acceptance(conn: sqlite3.Connection, user_id: int, version_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM customer_terms_acceptances WHERE telegram_user_id = ? AND terms_version_id = ?",
        (user_id, version_id),
    ).fetchone()


def accept(conn: sqlite3.Connection, user_id: int, version_id: int, source: str, now: datetime) -> tuple[int, bool]:
    """Ghi khách đồng ý bản đang công bố. Trả (acceptance_id, mới ghi?). Bấm lại không ghi thêm."""
    live = current(conn, now)
    if live is None or live.id != version_id:
        raise TermsError("not_current")
    found = acceptance(conn, user_id, version_id)
    if found is not None:
        return int(found["id"]), False
    stamp = _stamp(now)
    cursor = conn.execute(
        """
        INSERT INTO customer_terms_acceptances
            (telegram_user_id, terms_version_id, terms_hash, acceptance_source, accepted_at, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, version_id, live.content_hash, source, stamp, _stamp(datetime.now(timezone.utc))),
    )
    return int(cursor.lastrowid), True


def link_context(conn: sqlite3.Connection, user_id: int, now: datetime) -> dict:
    """Dòng link_terms_context cho link sắp tạo: bản đang công bố và lần chấp thuận của người tạo (nếu có)."""
    live = current(conn, now)
    accepted = None if live is None else acceptance(conn, user_id, live.id)
    return {
        "terms_version_id": None if live is None else live.id,
        "acceptance_id": None if accepted is None else int(accepted["id"]),
        "recorded_at": _stamp(now),
    }


def link_terms(conn: sqlite3.Connection, link_id: int) -> tuple[str, TermsVersion | None, bool]:
    """(trạng thái, bản điều khoản, đã chấp thuận?). LEGACY: link trước PLAN-077, không có bản ghi."""
    row = conn.execute("SELECT * FROM link_terms_context WHERE link_id = ?", (link_id,)).fetchone()
    if row is None:
        return "LEGACY_NOT_RECORDED", None, False
    if row["terms_version_id"] is None:
        return "NO_PUBLISHED_TERMS", None, False
    version = get(conn, int(row["terms_version_id"]))
    return ("ACCEPTED" if row["acceptance_id"] else "NOT_ACCEPTED"), version, row["acceptance_id"] is not None
