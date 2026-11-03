"""Lịch mùa Tết Đinh Mùi 2027 (PLAN-134 C): ngày âm lịch + giai đoạn mùa, để lơ xe nói đúng mùa và HUD ghi «26 Chạp».

Dữ kiện (agent tra cứu 01/11, có nguồn trong PLAN-134): mùng 1 Tết = thứ Bảy 6/2/2027; tháng Chạp năm Bính Ngọ chỉ có 29 ngày
nên giao thừa là 29 Chạp (5/2/2027), không có «30 Tết»; công chức nghỉ 28 Chạp → mùng 5. Bến xe đông nhất chiều về 24–28
Chạp, chiều ra lại thành phố từ mùng 4, đông nhất mùng 6–7.
"""

from datetime import date, timedelta

TET_DAY = date(2027, 2, 6)
CHAP_DAYS = 29  # tháng Chạp thiếu: 29 Chạp là giao thừa

# Giai đoạn mùa theo số ngày tính từ mùng 1 (âm = trước Tết)
EARLY = "early"  # trước 23 Chạp: xe Tết bắt đầu chạy, chưa đông
PEAK = "peak"  # 23 → 28 Chạp: cao điểm chiều về, bến chật
EVE = "eve"  # 29 Chạp: giao thừa, chuyến cuối năm
TET = "tet"  # mùng 1 → 3: ăn Tết
RETURN = "return"  # mùng 4 → 10: chiều ra lại thành phố
AFTER = "after"  # sau mùng 10: hết mùa


def phase(today: date) -> str:
    d = (today - TET_DAY).days
    if d < -7:
        return EARLY
    if d < -1:
        return PEAK
    if d == -1:
        return EVE
    if d < 3:
        return TET
    if d < 10:
        return RETURN
    return AFTER


def lunar_label(today: date) -> str | None:
    """«26 Chạp», «Giao thừa», «Mùng 2 Tết», «Mùng 5»; trước tháng Chạp / sau mùng 10: None (HUD đếm ngày như cũ)."""
    d = (today - TET_DAY).days
    if -CHAP_DAYS <= d < -1:
        return f"{CHAP_DAYS + 1 + d} Chạp"
    if d == -1:
        return "Giao thừa"
    if 0 <= d < 3:
        return f"Mùng {d + 1} Tết"
    if 3 <= d < 10:
        return f"Mùng {d + 1}"
    return None


def view(today: date) -> dict:
    """Cho state: giai đoạn, nhãn âm lịch, số ngày tới Tết."""
    return {"phase": phase(today), "lunar": lunar_label(today), "days_to_tet": max(0, (TET_DAY - today).days)}


def chap(day: int) -> date:
    """Ngày dương của «`day` Chạp» (để test / lơ xe tính ngược)."""
    return TET_DAY - timedelta(days=CHAP_DAYS + 1 - day)
