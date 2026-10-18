"""Ô giờ tiếp theo của một kênh. Không gọi nơi đăng.

Mỗi kênh đăng theo khung giờ đã định (mặc định 3 bài một ngày, có kênh 5 bài một ngày theo giờ Việt Nam).
Đủ bài trong ngày thì sang ngày sau.
Giờ neo giữ slot đã đo trên Buffer; hai giờ thêm là ước tính để trải trong ngày.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.features.buffer.when import ICT, accept_ts, now_ict

LOOKAHEAD_DAYS = 14
DAILY_LIMIT = 3

# Tên kênh (không dấu hoa) → (giờ, phút), sớm tới muộn.
CHANNEL_HOURS: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("uyển nhi", ((8, 0), (15, 30), (19, 30))),
    ("sống nhẹ", ((7, 30), (11, 30), (14, 30), (17, 30), (20, 30))),
    ("mê câu cá", ((11, 0), (16, 30), (20, 0))),
)
DEFAULT_HOURS: tuple[tuple[int, int], ...] = ((9, 0), (14, 0), (19, 0))


def channel_hours(name: str) -> list[tuple[int, int]]:
    """Giờ trong ngày. Kênh chưa có bảng riêng thì dùng giờ mặc định."""
    key = (name or "").casefold()
    for fragment, hours in CHANNEL_HOURS:
        if fragment in key:
            return list(hours)
    return list(DEFAULT_HOURS)


def daily_limit(name: str) -> int:
    """Số bài tối đa mỗi ngày của kênh (bằng đúng số ô giờ định sẵn)."""
    return len(channel_hours(name))


def slots_label(name: str) -> str:
    return ", ".join(f"{hour:02d}:{minute:02d}" for hour, minute in channel_hours(name))


def _on_day(ts: int, day: date) -> bool:
    return datetime.fromtimestamp(int(ts), ICT).date() == day


def next_free_slot(
    name: str,
    taken: list[int] | set[int],
    now: datetime | None = None,
    skip_days: set[date] | None = None,
) -> tuple[int | None, str | None]:
    """Ô kế còn trống, chưa đủ số bài trong ngày. Giờ đã qua thì bỏ."""
    hours = channel_hours(name)
    limit = daily_limit(name)
    stamps = [int(ts) for ts in taken if ts]
    occupied = set(stamps)
    blocked = skip_days or set()
    moment = now_ict(now)
    for offset in range(LOOKAHEAD_DAYS):
        day = (moment + timedelta(days=offset)).date()
        if day in blocked:
            continue
        if sum(1 for ts in stamps if _on_day(ts, day)) >= limit:
            continue
        for hour, minute in hours:
            try:
                target = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ICT)
            except ValueError:
                continue
            ts, _err = accept_ts(int(target.timestamp()), moment)
            if ts is None or ts in occupied:
                continue
            return ts, None
    return None, "Hết ô trống trong 14 ngày."
