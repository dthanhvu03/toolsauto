"""Giờ nghỉ của shop: admin đặt khung nghỉ hằng ngày (giờ Việt Nam) hoặc đóng tay ngay.

Lúc nghỉ khách vẫn xem món, nạp ví được, nhưng KHÔNG đặt mua / tạo QR mua (đêm admin ngủ không nạp được ví
FatCat thì đơn treo — mất uy tín). Mã QR tạo trước giờ nghỉ mà tiền về trong giờ nghỉ vẫn tự mua như thường.
State: `closed_hours` = "23:30-07:30" · `closed_manual` = "1".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

ICT = timezone(timedelta(hours=7))
_TIME = r"(\d{1,2})\s*(?:[:hg.]\s*(\d{2})?)?"
_WINDOW_RE = re.compile(rf"^\s*{_TIME}\s*(?:-|–|—|>|đến|den|to)\s*{_TIME}\s*$", re.I)


@dataclass(frozen=True)
class Window:
    start: int  # phút trong ngày (0–1439), giờ VN
    end: int

    @property
    def code(self) -> str:
        return f"{_hhmm(self.start)}-{_hhmm(self.end)}"

    @property
    def label(self) -> str:
        return f"{_hhmm(self.start)}–{_hhmm(self.end)}"

    def contains(self, minute: int) -> bool:
        if self.start <= self.end:
            return self.start <= minute < self.end
        return minute >= self.start or minute < self.end  # qua nửa đêm, vd 23:30–07:30


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_window(text: str | None) -> Window | None:
    """"23:30-07:30" · "23h-7h" · "23h30 - 7h30" · "1:00–6:00". Sai / hai đầu bằng nhau → None."""
    match = _WINDOW_RE.match(text or "")
    if not match:
        return None
    h1, m1, h2, m2 = (int(g) if g else 0 for g in match.groups())
    if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
        return None
    window = Window(h1 * 60 + m1, h2 * 60 + m2)
    return None if window.start == window.end else window


@dataclass(frozen=True)
class Status:
    closed: bool
    manual: bool = False
    reopen: str | None = None  # "07:30" khi nghỉ theo giờ; None khi đóng tay


def status(window: Window | None, manual: bool, now: datetime | None = None) -> Status:
    if manual:
        return Status(True, manual=True)
    if window is None:
        return Status(False)
    local = (now or datetime.now(timezone.utc)).astimezone(ICT)
    if window.contains(local.hour * 60 + local.minute):
        return Status(True, reopen=_hhmm(window.end))
    return Status(False)
