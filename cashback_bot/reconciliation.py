"""Theo dõi đơn qua bot đang chờ Shopee xác minh khi ra khỏi khung đồng bộ 30 ngày (PLAN-081, ADR-058).

Chỉ đọc dữ liệu bot đã có; không gọi Shopee, không đổi tiền, không gửi tin cho khách.
Nhãn theo dõi tách khỏi validation_status / settlement_status / sổ ví:
- OBSERVED_RECENTLY        thấy trong nguồn, tuổi < 20 ngày
- APPROACHING_WINDOW       20 ≤ tuổi < 30 ngày (sắp ra khung quét)
- OUTSIDE_WINDOW_UNVERIFIED tuổi ≥ 30 ngày: bot không còn đọc được đơn, chưa biết Shopee đã đổi gì
- RECONCILIATION_REQUIRED  tuổi ≥ 45 ngày, hoặc đơn trong khung mà vắng ≥ 2 lượt thành công liên tiếp,
                           hoặc thiếu giờ mua
- RECONCILED               đơn từng được theo dõi nay có kết luận từ dữ liệu Shopee thật / chứng từ PLAN-075

Không bao giờ suy ra «Shopee đã từ chối / huỷ / gian lận» chỉ vì đơn đã lâu hoặc vắng mặt.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cashback_bot.db import TrackingRepository, enqueue_event

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
APPROACHING_AGE = timedelta(days=20)
WINDOW_AGE = timedelta(days=30)
REQUIRED_AGE = timedelta(days=45)
MISSED_RUNS_REQUIRED = 2
# Phương án A: tra được trong 48 giờ qua bằng khung hẹp thì coi là còn quan sát được, dù đã ngoài khung 30 ngày.
NARROW_FRESH = timedelta(hours=48)
# Không tra quá 180 ngày tuổi (nguồn chưa chứng minh trả đơn quá cũ; đơn vẫn ở danh sách cần đối soát).
LOOKUP_MAX_AGE = timedelta(days=180)
WAITING = ("PENDING", "UNKNOWN", "NEEDS_REVIEW")
CONCLUDED = ("APPROVED", "REJECTED", "FRAUD")
BACKLOG = ("APPROACHING_WINDOW", "OUTSIDE_WINDOW_UNVERIFIED", "RECONCILIATION_REQUIRED")
DIGEST_KEY = "recon_digest_last"
NEXT_ACTIONS = {
    "OBSERVED_RECENTLY": None,
    "APPROACHING_WINDOW": "Theo dõi; sau mốc 30 ngày bot không còn đọc được đơn này",
    "OUTSIDE_WINDOW_UNVERIFIED": "Kiểm tra trạng thái đơn trên Shopee Affiliate",
    "RECONCILIATION_REQUIRED": "Đối soát đơn với Shopee; có chứng từ thì nhập ở 🧾 Đối soát thanh toán",
    "RECONCILED": None,
}


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str | None) -> datetime | None:
    try:
        return datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass
class Summary:
    counts: dict = field(default_factory=dict)
    changed: list = field(default_factory=list)  # (conversion_id, from, to, reason)


def classify(row, now: datetime, missed: int) -> tuple[str, str]:
    """(nhãn, lý do) của một đơn đang chờ. Chỉ dựa vào tuổi theo giờ mua và số lượt vắng trong khung."""
    purchase = _parse(row["purchase_time"])
    if purchase is None:
        return "RECONCILIATION_REQUIRED", "no_purchase_time"
    age = now - purchase
    seen = _parse(row["last_seen_at"]) if "last_seen_at" in row.keys() else None
    if age >= WINDOW_AGE and seen is not None and row["last_seen_source"] == "report_list_narrow" and now - seen <= NARROW_FRESH:
        return "OBSERVED_RECENTLY", "seen_outside_window"
    if age >= REQUIRED_AGE:
        return "RECONCILIATION_REQUIRED", "age_45d"
    if age >= WINDOW_AGE:
        return "OUTSIDE_WINDOW_UNVERIFIED", "outside_30d_window"
    if missed >= MISSED_RUNS_REQUIRED:
        return "RECONCILIATION_REQUIRED", "missing_in_window"
    if age >= APPROACHING_AGE:
        return "APPROACHING_WINDOW", "age_20d"
    return "OBSERVED_RECENTLY", "seen"


def evaluate(repo: TrackingRepository, now: datetime, run_id: int | None = None, window_start: str | None = None,
             run_success: bool = False, admin_notifier=None) -> Summary:
    """Cập nhật nhãn theo dõi. run_id / window_start / run_success: của lượt đồng bộ vừa xong (để đếm lượt vắng).

    Lượt không thành công (PARTIAL / lỗi) không được tính là «vắng» vì dữ liệu chưa đủ. Gọi không có lượt (định kỳ)
    chỉ cập nhật nhãn theo tuổi. Chạy lại cùng một lượt không đếm vắng hai lần.
    """
    summary = Summary()
    stamp = _stamp(now)
    with repo.connect() as conn:
        rows = conn.execute(
            """
            SELECT c.conversion_id, c.order_sn, c.purchase_time, c.validation_status, c.settlement_status,
                   c.last_seen_run_id, c.last_seen_at, c.last_seen_source, r.tracking_status, r.missed_runs, r.last_run_id
            FROM shopee_conversions c LEFT JOIN conversion_reconciliation r ON r.conversion_id = c.conversion_id
            WHERE c.matched_link_id IS NOT NULL AND c.platform = 'shopee'
              AND (c.validation_status IN ('PENDING', 'UNKNOWN', 'NEEDS_REVIEW') OR r.conversion_id IS NOT NULL)
            """
        ).fetchall()
        for row in rows:
            current, missed = row["tracking_status"], int(row["missed_runs"] or 0)
            if row["validation_status"] in CONCLUDED or row["settlement_status"] == "SETTLED":
                if current is None or current == "RECONCILED":
                    continue
                status, reason = "RECONCILED", "shopee_data"
            else:
                if run_id is not None and run_success and row["last_run_id"] != run_id:
                    in_window = window_start is None or (row["purchase_time"] or "") >= window_start
                    if row["last_seen_run_id"] == run_id:
                        missed = 0
                    elif in_window:
                        missed += 1
                status, reason = classify(row, now, missed)
            last_run = run_id if run_id is not None and run_success else row["last_run_id"]
            if current is None:
                conn.execute(
                    "INSERT INTO conversion_reconciliation (conversion_id, tracking_status, reason, next_action, missed_runs, "
                    "last_run_id, status_since, evaluated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (row["conversion_id"], status, reason, NEXT_ACTIONS[status], missed, last_run, stamp, stamp),
                )
            else:
                conn.execute(
                    "UPDATE conversion_reconciliation SET tracking_status = ?, reason = ?, next_action = ?, missed_runs = ?, "
                    "last_run_id = ?, evaluated_at = ?, status_since = CASE WHEN tracking_status = ? THEN status_since ELSE ? END "
                    "WHERE conversion_id = ?",
                    (status, reason, NEXT_ACTIONS[status], missed, last_run, stamp, status, stamp, row["conversion_id"]),
                )
            if status != current:
                conn.execute(
                    "INSERT INTO conversion_reconciliation_events (conversion_id, from_status, to_status, reason, run_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (row["conversion_id"], current, status, reason, run_id, stamp),
                )
                summary.changed.append((row["conversion_id"], current, status, reason))
        for status, count in conn.execute(
            "SELECT tracking_status, COUNT(*) FROM conversion_reconciliation GROUP BY tracking_status"
        ):
            summary.counts[status] = int(count)
        _alerts(conn, repo, summary, now, admin_notifier)
    return summary


def _admin_target(admin_notifier) -> int | None:
    if admin_notifier is None or not getattr(admin_notifier, "enabled", False):
        return None
    chat = getattr(admin_notifier, "chat_id", None)
    return None if chat is None else int(chat)


def _alerts(conn: sqlite3.Connection, repo: TrackingRepository, summary: Summary, now: datetime, admin_notifier) -> None:
    """Báo admin. Một tin riêng khi đơn chuyển «cần đối soát» hoặc đơn từng ngoài khung đã đối soát được; một tin tổng hợp
    tối đa mỗi ngày (giờ VN), chỉ khi danh sách đơn cần chú ý đổi. Không bao giờ gửi khách."""
    chat = _admin_target(admin_notifier)
    if chat is None:
        return
    stamp = _stamp(now)
    for conversion_id, before, after, reason in summary.changed:
        if after == "RECONCILIATION_REQUIRED" or (after == "RECONCILED" and before in BACKLOG[1:]):
            order = _order_ref(conn, conversion_id)
            text = (
                f"🧾 <b>Đơn cần đối soát</b>\n\nĐơn {order}: {REASON_LABELS.get(reason, reason)}.\n"
                "Bot không tự kết luận đơn bị từ chối hay huỷ. Xem /admin → 🔗 Shopee Affiliate → 🧾 Đơn cần đối soát."
                if after == "RECONCILIATION_REQUIRED" else
                f"✅ <b>Đã có kết quả cho đơn {order}</b>\n\nĐơn từng ngoài khung đồng bộ nay đã có dữ liệu Shopee / chứng từ."
            )
            enqueue_event(conn, event_key=f"recon:{conversion_id}:{after}", event_type="RECON_ALERT", chat_id=chat,
                          message_html=text, now=stamp)
    attention = conn.execute(
        "SELECT conversion_id, tracking_status FROM conversion_reconciliation WHERE tracking_status IN (?, ?, ?) "
        "ORDER BY conversion_id",
        BACKLOG,
    ).fetchall()
    fingerprint = hashlib.sha256("|".join(f"{r[0]}={r[1]}" for r in attention).encode()).hexdigest()[:12]
    last = conn.execute("SELECT value FROM bot_state WHERE key = ?", (DIGEST_KEY,)).fetchone()
    last_day, _, last_print = (last[0] if last else "").partition(":")
    today = now.astimezone(ICT).strftime("%Y-%m-%d")
    if not attention or last_print == fingerprint or last_day == today:
        return
    counts = {status: sum(1 for r in attention if r[1] == status) for status in BACKLOG}
    lines = [f"⚠️ <b>ĐƠN CẦN ĐỐI SOÁT</b>\n\nCó {len(attention)} đơn cashback đang chờ Shopee xác minh:"]
    if counts["APPROACHING_WINDOW"]:
        lines.append(f"• {counts['APPROACHING_WINDOW']} đơn sắp ra khỏi khung đồng bộ 30 ngày.")
    if counts["OUTSIDE_WINDOW_UNVERIFIED"]:
        lines.append(f"• {counts['OUTSIDE_WINDOW_UNVERIFIED']} đơn đã ngoài khung, chưa có nguồn cập nhật mới.")
    if counts["RECONCILIATION_REQUIRED"]:
        lines.append(f"• {counts['RECONCILIATION_REQUIRED']} đơn cần đối soát.")
    lines.append("\nXem /admin → 🔗 Shopee Affiliate → 🧾 Đơn cần đối soát.")
    enqueue_event(conn, event_key=f"recon_digest:{today}:{fingerprint}", event_type="RECON_DIGEST", chat_id=chat,
                  message_html="\n".join(lines), now=stamp)
    conn.execute(
        "INSERT INTO bot_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (DIGEST_KEY, f"{today}:{fingerprint}"),
    )


REASON_LABELS = {
    "seen": "bot vẫn thấy đơn trong nguồn",
    "seen_outside_window": "ngoài khung 30 ngày nhưng bot vẫn tra được trên Shopee",
    "age_20d": "sắp ra khỏi khung đồng bộ 30 ngày",
    "outside_30d_window": "đã ngoài khung đồng bộ 30 ngày, bot không còn đọc được",
    "age_45d": "quá 45 ngày chưa có kết luận",
    "missing_in_window": "vắng trong 2 lượt đồng bộ liên tiếp dù còn trong khung",
    "no_purchase_time": "Shopee không trả giờ mua",
    "shopee_data": "đã có kết luận từ dữ liệu Shopee / chứng từ",
}


def _order_ref(conn: sqlite3.Connection, conversion_id: str) -> str:
    row = conn.execute("SELECT order_sn FROM shopee_conversions WHERE conversion_id = ?", (conversion_id,)).fetchone()
    return "••••" + str((row["order_sn"] if row and row["order_sn"] else conversion_id))[-4:]


def lookup_targets(repo: TrackingRepository, now: datetime, limit: int) -> list[tuple[str, int]]:
    """Phương án A: đơn qua bot đang chờ, đã ra khung 30 ngày, chưa tra hôm nay (giờ VN), tuổi ≤ 180 ngày.
    Trả (conversion_id, giờ mua unix). Đơn chưa tra bao giờ hoặc tra lâu nhất đi trước."""
    today = now.astimezone(ICT).strftime("%Y-%m-%d")
    picked: list[tuple[str, int]] = []
    with repo.connect() as conn:
        rows = conn.execute(
            """
            SELECT c.conversion_id, c.purchase_time, r.last_attempt_at
            FROM conversion_reconciliation r JOIN shopee_conversions c ON c.conversion_id = r.conversion_id
            WHERE r.tracking_status IN ('OUTSIDE_WINDOW_UNVERIFIED', 'RECONCILIATION_REQUIRED', 'OBSERVED_RECENTLY')
              AND c.matched_link_id IS NOT NULL AND c.validation_status IN ('PENDING', 'UNKNOWN', 'NEEDS_REVIEW')
              AND c.purchase_time IS NOT NULL
            ORDER BY r.last_attempt_at IS NOT NULL, r.last_attempt_at, c.purchase_time
            """
        ).fetchall()
    for row in rows:
        purchase = _parse(row["purchase_time"])
        if purchase is None or now - purchase < WINDOW_AGE or now - purchase > LOOKUP_MAX_AGE:
            continue
        attempted = _parse(row["last_attempt_at"])
        if attempted is not None and attempted.astimezone(ICT).strftime("%Y-%m-%d") == today:
            continue
        picked.append((str(row["conversion_id"]), int(purchase.timestamp())))
        if len(picked) >= limit:
            break
    return picked


def record_attempt(repo: TrackingRepository, conversion_id: str, result: str, now: datetime) -> None:
    """Ghi lần tra khung hẹp: seen / not_returned / error:<loại>. Không đổi nhãn hay tiền (evaluate() làm sau)."""
    stamp = _stamp(now)
    with repo.connect() as conn:
        conn.execute(
            "UPDATE conversion_reconciliation SET last_attempt_at = ?, last_attempt_result = ? WHERE conversion_id = ?",
            (stamp, result[:60], conversion_id),
        )
        conn.execute(
            "INSERT INTO conversion_reconciliation_events (conversion_id, from_status, to_status, reason, run_id, created_at) "
            "SELECT conversion_id, tracking_status, tracking_status, ?, NULL, ? FROM conversion_reconciliation WHERE conversion_id = ?",
            (f"lookup:{result[:50]}", stamp, conversion_id),
        )


def backlog(repo: TrackingRepository) -> list[sqlite3.Row]:
    """Danh sách cho màn admin: đơn cần chú ý trước, rồi đơn đang theo dõi, rồi đơn đã đối soát (chỉ đọc)."""
    with repo.connect() as conn:
        return conn.execute(
            """
            SELECT r.*, c.order_sn, c.purchase_time, c.last_seen_at, c.last_seen_source, c.order_status,
                   c.validation_status, c.settlement_status, l.product_name
            FROM conversion_reconciliation r
            JOIN shopee_conversions c ON c.conversion_id = r.conversion_id
            LEFT JOIN link_requests l ON l.id = c.matched_link_id
            ORDER BY CASE r.tracking_status WHEN 'RECONCILIATION_REQUIRED' THEN 0 WHEN 'OUTSIDE_WINDOW_UNVERIFIED' THEN 1
                     WHEN 'APPROACHING_WINDOW' THEN 2 WHEN 'OBSERVED_RECENTLY' THEN 3 ELSE 4 END, c.purchase_time
            """
        ).fetchall()
