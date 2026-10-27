"""Lịch sale cố định của Shopee VN và giờ gửi nhắc (reports/CASHBACK_SALE_REMINDERS.md). Hàm thuần, không đọc DB.

Bốn cấp (theo các trang lịch sale, Shopee không công bố bảng phân cấp chính thức):
- peak · đỉnh: 11.11, 12.12 (sinh nhật Shopee). Nhắc 20:30 tối hôm trước và 11:30 trong ngày (trước khung 12h).
- super · siêu sale: 9.9, 10.10, Black Friday (thứ Sáu cuối tháng 11). Nhắc 20:30 tối hôm trước.
- double · ngày đôi thường: 1.1 … 8.8. Nhắc 20:30 tối hôm trước.
- mini: giữa tháng (15), cuối tháng / lương về (25). Nhắc 20:30 tối hôm trước.
Sale mở lúc 0h; 20:30 là khung tối khách đang lướt điện thoại, còn hơn 3 giờ để mở link qua bot và gom giỏ.
Hai dịp cách nhau dưới 5 ngày thì chỉ giữ dịp cấp cao hơn (15 sau 11.11 / 12.12, 25/11 trước Black Friday bị bỏ):
mỗi khách tối đa khoảng 2 tin một tuần. Flash sale hằng ngày (0h, 12h…) không nhắc: thành tin rác.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
PEAK = {(11, 11), (12, 12)}
SUPER = {(9, 9), (10, 10)}
MIN_GAP_DAYS = 5
EVE_AT = time(20, 30)
DAY_AT = time(11, 30)
TIERS = {"peak": 4, "super": 3, "double": 2, "mini": 1}
TIER_LABELS = {"peak": "Đỉnh", "super": "Siêu sale", "double": "Ngày đôi", "mini": "Mini"}


@dataclass(frozen=True)
class SaleEvent:
    day: date
    kind: str  # double · mid · payday · blackfriday
    tier: str  # peak · super · double · mini

    @property
    def label(self) -> str:
        if self.kind == "double":
            return f"{self.day.day}.{self.day.month}"
        if self.kind == "blackfriday":
            return "Black Friday"
        return f"{self.day.day}/{self.day.month}"

    @property
    def priority(self) -> int:
        return TIERS[self.tier]


@dataclass(frozen=True)
class Slot:
    event: SaleEvent
    stage: str  # eve: tối hôm trước · day: trưa trong ngày
    at: datetime  # UTC

    @property
    def id(self) -> str:
        return f"{self.event.day.isoformat()}:{self.stage}"


def _black_friday(year: int) -> date:
    day = date(year, 11, 30)
    return day - timedelta(days=(day.weekday() - 4) % 7)


def _month_events(year: int, month: int) -> list[SaleEvent]:
    pair = (month, month)
    tier = "peak" if pair in PEAK else ("super" if pair in SUPER else "double")
    found = [
        SaleEvent(date(year, month, month), "double", tier),
        SaleEvent(date(year, month, 15), "mid", "mini"),
        SaleEvent(date(year, month, 25), "payday", "mini"),
    ]
    if month == 11:
        found.append(SaleEvent(_black_friday(year), "blackfriday", "super"))
    return found


def events(start: date, end: date) -> list[SaleEvent]:
    """Các dịp trong [start, end], đã bỏ dịp cấp thấp nằm quá gần dịp cấp cao hơn."""
    found: list[SaleEvent] = []
    # Lấy rộng một tháng hai đầu để luật cách ngày xét đúng cả dịp sát biên.
    cursor = date(start.year, start.month, 1) - timedelta(days=1)
    stop = end + timedelta(days=31)
    while cursor <= stop:
        found += _month_events(cursor.year, cursor.month)
        cursor = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
    found.sort(key=lambda e: e.day)
    kept = [e for e in found if not any(
        o is not e and abs((o.day - e.day).days) < MIN_GAP_DAYS
        and (o.priority > e.priority or (o.priority == e.priority and o.day < e.day))
        for o in found)]
    return [e for e in kept if start <= e.day <= end]


def _utc(day: date, at: time) -> datetime:
    return datetime.combine(day, at, ICT).astimezone(timezone.utc)


def slots(event: SaleEvent) -> list[Slot]:
    result = [Slot(event, "eve", _utc(event.day - timedelta(days=1), EVE_AT))]
    if event.tier == "peak":
        result.append(Slot(event, "day", _utc(event.day, DAY_AT)))
    return result


def upcoming(now: datetime, days: int = 45) -> list[Slot]:
    """Các lượt nhắc từ hôm nay tới `days` ngày tới, kể cả lượt đã qua trong ngày (để màn admin thấy đã gửi)."""
    today = now.astimezone(ICT).date()
    found = [s for e in events(today, today + timedelta(days=days + 1)) for s in slots(e)]
    return sorted((s for s in found if s.at.astimezone(ICT).date() >= today), key=lambda s: s.at)


def find(slot_id: str) -> Slot | None:
    try:
        day_text, stage = slot_id.split(":")
        day = date.fromisoformat(day_text)
    except ValueError:
        return None
    for event in events(day, day):
        for slot in slots(event):
            if slot.stage == stage:
                return slot
    return None
