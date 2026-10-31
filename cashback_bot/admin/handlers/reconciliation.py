"""Màn /admin → 🔗 Shopee Affiliate → 🧾 Đơn cần đối soát (PLAN-081). Chỉ đọc.

Liệt kê đơn qua bot đang chờ Shopee xác minh, tuổi theo giờ mua, lần cuối bot thấy đơn trong nguồn, nhãn theo dõi,
lý do và việc cần làm. Không có nút đổi trạng thái hoa hồng, thanh toán hay sổ ví: kết luận chỉ đến từ dữ liệu Shopee
thật hoặc chứng từ ở 🧾 Đối soát thanh toán (PLAN-075).
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply, buyer_name
from cashback_bot.reconciliation import REASON_LABELS, backlog

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
STATUS_LABELS = {
    "RECONCILIATION_REQUIRED": "🔴 Cần đối soát",
    "OUTSIDE_WINDOW_UNVERIFIED": "🟠 Ngoài khung, chưa xác minh",
    "APPROACHING_WINDOW": "🟡 Sắp ra khung",
    "OBSERVED_RECENTLY": "🟢 Đang theo dõi",
    "RECONCILED": "✅ Đã đối soát",
}
LIMIT = 12
ATTEMPT_LABELS = {"seen": "tra được", "not_returned": "Shopee không trả đơn này"}


def _vn(stamp: str | None) -> str:
    try:
        moment = datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return "chưa rõ"
    return moment.astimezone(ICT).strftime("%d/%m %H:%M")


def _age(stamp: str | None, now: datetime) -> str:
    try:
        moment = datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return "không rõ tuổi"
    return f"{(now - moment).days} ngày"


class ReconciliationAdmin:
    def __init__(self, repo: TrackingRepository, lookup: bool = False):
        self.repo = repo
        # PLAN-081 Phương án A (SHOPEE_RECONCILE_LOOKUP_ENABLED): bot tra lại đơn đã ra khung mỗi ngày.
        self.lookup = lookup

    def route(self, data: str, now: datetime | None = None) -> BotReply:
        if data == "c:rc:home":
            return self.home(now or datetime.now(timezone.utc))
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=((("◀️ Đơn cần đối soát", "c:rc:home"),),))

    def home(self, now: datetime) -> BotReply:
        rows = backlog(self.repo)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["tracking_status"]] = counts.get(row["tracking_status"], 0) + 1
        lines = ["⚙️ Quản trị › Shopee Affiliate › <b>Đơn cần đối soát</b>", ""]
        if not rows:
            lines.append("Chưa có đơn qua bot nào đang chờ Shopee xác minh.")
        else:
            lines.append(" · ".join(f"{STATUS_LABELS[s]}: <b>{counts[s]}</b>" for s in STATUS_LABELS if counts.get(s)))
            lines.append("")
            for row in rows[:LIMIT]:
                order = "••••" + str(row["order_sn"] or row["conversion_id"])[-4:]
                name = html.escape(buyer_name(row["product_name"] or "")[:40]) or "-"
                seen = _vn(row["last_seen_at"]) + (" (suy ra)" if row["last_seen_source"] == "backfill_updated_at" else "")
                lines.append(f"{STATUS_LABELS[row['tracking_status']]} · {order} · {name}")
                lines.append(f"  mua {_vn(row['purchase_time'])} ({_age(row['purchase_time'], now)}) · lần cuối bot thấy: {seen}")
                if row["last_attempt_at"]:
                    lines.append(f"  lần tra Shopee gần nhất: {_vn(row['last_attempt_at'])} · "
                                 f"{ATTEMPT_LABELS.get(row['last_attempt_result'], html.escape(str(row['last_attempt_result'])))}")
                lines.append(f"  {html.escape(REASON_LABELS.get(row['reason'], row['reason'] or '-'))}"
                             + (f" · 👉 {html.escape(row['next_action'])}" if row["next_action"] else ""))
            if len(rows) > LIMIT:
                lines.append(f"… và {len(rows) - LIMIT} đơn khác.")
        scope = (
            "ⓘ Bot quét đơn mua trong 30 ngày gần nhất; đơn qua bot đang chờ đã ra khung được tra lại trên Shopee tối đa "
            "1 lần / ngày. " if self.lookup else "ⓘ Bot chỉ đọc được đơn mua trong 30 ngày gần nhất. "
        )
        lines += [
            "",
            scope + "Đơn ngoài khung giữ nguyên số tiền và trạng thái; bot không tự kết luận Shopee đã duyệt, từ chối hay huỷ.",
        ]
        keyboard = (
            (("🧾 Đối soát thanh toán", "c:sm:home"),),
            (("◀️ Shopee Affiliate", "c:menu:shopee"),),
        )
        return BotReply("\n".join(lines), inline_keyboard=keyboard)
