"""Cấp bậc khách + chuỗi ngày ghé live (anh 04/11 «chơi quài không chán»).

Điểm hành trình = số chuyến đã về tới quê + số ngày khác nhau đã ghé live: ai chăm ghé, chăm đi đều lên cấp, không cần quà.
Chuỗi ngày: ghé (có tương tác thật) mỗi ngày liên tiếp; tới mốc STREAK_REWARD_DAYS được một suất lên đầu hàng chờ.
"""

LEVELS: tuple[tuple[int, str, str], ...] = (  # (điểm tối thiểu, biểu tượng, tên cấp)
    (0, "🎒", "Khách mới"),
    (3, "🎫", "Khách quen"),
    (10, "⭐", "Hành khách vàng"),
    (25, "🚌", "Phụ xe"),
    (50, "👑", "Lão làng"),
)
STREAK_REWARD_DAYS = (3, 7, 14, 30)


def points(trips: int, days: int) -> int:
    return trips + days


def level(pts: int) -> int:
    return max(i for i, (need, _, _) in enumerate(LEVELS) if pts >= need)


def badge(pts: int) -> str:
    """Biểu tượng cạnh tên; khách mới để trống cho màn đỡ rối."""
    i = level(pts)
    return LEVELS[i][1] if i else ""


def title(pts: int) -> str:
    _, icon, name = LEVELS[level(pts)]
    return f"{icon} {name}"


def to_next(pts: int) -> tuple[str, int] | None:
    """(tên cấp kế, còn bao nhiêu điểm); đã cấp cao nhất thì None."""
    i = level(pts)
    if i + 1 >= len(LEVELS):
        return None
    need, icon, name = LEVELS[i + 1]
    return f"{icon} {name}", need - pts
