"""Giờ hẹn đăng theo giờ Việt Nam. Không gọi nơi đăng."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

ICT = timezone(timedelta(hours=7))
MIN_LEAD = 10 * 60
MAX_LEAD = 30 * 24 * 3600
SAMPLE = "ngày/tháng giờ:phút"

# code → (nhãn, số ngày cộng thêm, giờ, phút).
# Slot theo lượt hiện Buffer (Uyển Nhi / Sống Nhẹ / Mê Câu Cá).
# day_off=0: nếu giờ hôm nay đã qua (hoặc < 10 phút) thì lấy cùng giờ ngày mai.
PRESETS: dict[str, tuple[str, int, int, int]] = {
    "t08": ("08:00 · Uyển Nhi", 0, 8, 0),
    "t12": ("12:00 · Sống Nhẹ", 0, 12, 0),
    "t15": ("15:30 · Uyển Nhi", 0, 15, 30),
    "t20": ("20:00 · Mê Câu Cá", 0, 20, 0),
}


def now_ict(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(ICT)
    if now.tzinfo is None:
        return now.replace(tzinfo=ICT)
    return now.astimezone(ICT)


def format_ict(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), ICT).strftime("%H:%M %d/%m")


def due_iso(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _check(ts: int, now: datetime) -> tuple[int | None, str | None]:
    now_ts = int(now.timestamp())
    if ts <= now_ts:
        return None, "Giờ phải ở tương lai."
    if ts < now_ts + MIN_LEAD:
        return None, "Giờ phải cách hiện tại ít nhất 10 phút."
    if ts > now_ts + MAX_LEAD:
        return None, "Giờ không được xa hơn 30 ngày."
    return ts, None


def accept_ts(ts: int, now: datetime | None = None) -> tuple[int | None, str | None]:
    try:
        value = int(ts)
    except (TypeError, ValueError):
        return None, f"Giờ không đọc được. Mẫu {SAMPLE}."
    return _check(value, now_ict(now))


def preset_ts(code: str, now: datetime | None = None) -> tuple[int | None, str | None]:
    spec = PRESETS.get(code)
    if not spec:
        return None, f"Giờ không đọc được. Mẫu {SAMPLE}."
    moment = now_ict(now)
    _, day_off, hour, minute = spec
    last_err: str | None = None
    # Cùng giờ hôm nay; nếu đã qua cửa sổ thì thử ngày kế.
    for extra in (0, 1) if day_off == 0 else (0,):
        day = (moment + timedelta(days=day_off + extra)).date()
        try:
            target = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ICT)
        except ValueError:
            return None, f"Giờ không đọc được. Mẫu {SAMPLE}."
        ts, err = _check(int(target.timestamp()), moment)
        if ts is not None:
            return ts, None
        last_err = err
    return None, last_err or f"Giờ không đọc được. Mẫu {SAMPLE}."


def parse_when(text: str, now: datetime | None = None) -> tuple[int | None, str | None]:
    """`ngày/tháng giờ:phút` hoặc `ngày/tháng/năm giờ:phút`. Thiếu năm thì lấy năm nay."""
    import re

    raw = " ".join((text or "").split())
    moment = now_ict(now)
    matched = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\s+(\d{1,2}):(\d{2})", raw)
    if not matched:
        return None, f"Giờ không đọc được. Mẫu {SAMPLE}."
    day_s, month_s, year_s, hour_s, minute_s = matched.groups()
    year = int(year_s) if year_s else moment.year
    try:
        target = datetime(year, int(month_s), int(day_s), int(hour_s), int(minute_s), tzinfo=ICT)
    except ValueError:
        return None, f"Giờ không đọc được. Mẫu {SAMPLE}."
    # Giờ đã qua thì từ chối, không cộng thêm một năm.
    return _check(int(target.timestamp()), moment)


def quota_block_reason(
    *,
    when: datetime,
    now: datetime,
    week_left: int | None,
    day_limit,
    day_sent,
    day_scheduled,
) -> str | None:
    """Tạo lịch mới. Đổi giờ không gọi hàm này."""
    if week_left is not None and week_left < 1:
        return "Hết suất tuần."
    if when.date() == now.date() and day_limit is not None:
        left = int(day_limit) - int(day_sent or 0) - int(day_scheduled or 0)
        if left < 1:
            return "Hết suất hôm nay."
    return None
