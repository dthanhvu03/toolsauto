"""Câu nói của Anh Tư lơ xe (PLAN-128): lơ xe khách bến bãi — cộc, ngắn, gọn, bỗ bã, thực tế.

- Không văn mẫu, không sến súa, không cảm thán rườm rà.
- Câu ngắn (3-7 chữ), nhịp giật dứt khoát, đọc qua TTS (VieNeu/Edge) trong 1-2 giây, không nghẽn hàng đợi.
- Giữ đúng các placeholder {dest}, {n}, {hours}, {place}, {specialty}, {total}, {name}, {names}, {prov}, {station}.
"""

import random
import re

LINES: dict[str, tuple[str, ...]] = {
    # ---- ở bến -------------------------------------------------------------------------------
    "boarding": (
        "{dest} đây! Gõ tên tỉnh lên xe, đứng ngó gì?",
        "Xe đi {dest}, ai đi gõ tỉnh lẹ lên xe chạy!",
        "{dest} nè, bấm tên tỉnh đi, sắp chạy rồi!",
        "Ai về {dest} bấm tên tỉnh nhảy lên xe mau!",
    ),
    "seats_left": (
        "Còn {n} vé, lẹ chân lên!",
        "Còn đúng {n} chỗ, chậm chân hết vé ráng chịu!",
        "Còn {n} giường, bấm tên tỉnh lẹ lên!",
    ),
    "last_seat": (
        "Một vé chót, ai lên bấm lẹ!",
        "Còn đúng một chỗ cuối, lẹ tay thì còn!",
    ),
    "full": (
        "Hết vé, tài ơi chạy!",
        "Kín xe rồi, đóng cửa xuất bến!",
        "Hết chỗ rồi, chờ chuyến sau đi!",
    ),
    "switch_lane": (
        "Đổi tuyến sang {dest}, ai đi {dest} lên lẹ!",
        "Quay đầu chạy {dest}, ai về {dest} lên ngay!",
    ),
    "departure": (
        "Xe dọn qua {station} rồi, gõ tên tỉnh lên xe mau!",
    ),
    # ---- trên đường ---------------------------------------------------------------------------
    "depart": (
        "Xuất bến! Nằm yên đừng đi lại, {hours} tới {dest}!",
        "Bác tài dập ga, {hours} tới {dest}, nằm im cho tui nhờ!",
        "Xe chạy nè, dép bỏ bọc, {hours} là tới {dest}!",
    ),
    "rest": (
        "Trạm {place} mười lăm phút, đi vệ sinh lẹ lên!",
        "Ghé {place} ăn uống nghỉ ngơi, có {specialty} kìa!",
        "Nghỉ trạm {place}, mười lăm phút xe chạy bỏ ráng chịu!",
    ),
    "honk": (
        "Bíp bíp, lên xe lẹ, tài đạp ga giờ!",
        "Còn ai dưới xe không, lên lẹ xe chạy!",
        "Ra xe lẹ, đếm đủ đầu người là phóng!",
    ),
    "dropoff_bubble": (
        "{prov} đây, ai xuống ôm đồ ra cửa lẹ!",
    ),
    "finish": (
        "Hết khách rồi, quay đầu về bến đón chuyến mới!",
        "Xong chuyến, ai chưa đi gõ tên tỉnh chờ tí!",
    ),
    "likes": (
        "Thả tim cho xe chạy lẹ coi!",
        "{total} tim rồi, bấm màn hình mạnh tay lên!",
    ),
    # ---- xe tăng cường ---------------------------------------------------------------------------
    "relief_auto": (
        "Đông quá, thêm một xe đi {dest}, ai đi lên luôn!",
        "Có xe tăng cường đi {dest}, lên lẹ khỏi chờ!",
    ),
    "relief_gift": (
        "{name} bao nguyên con xe đi {dest}, ai về hướng đó lên mau!",
        "{name} thầu chuyến {dest} rồi, cả xe lên đi ké lẹ lên!",
    ),
    "relief_admin": (
        "Nhà xe tăng cường thêm chuyến đi {dest}, lên xe mau!",
    ),
    # ---- người xem ---------------------------------------------------------------------------------
    "home": (
        "{name} ở ngay {prov} đi bộ về đi cha nội!",
        "{name} ở {prov} lên xe làm gì? Xuống nhường vé cho người ta!",
    ),
    "treat": (
        "{name} khao trà đá cả xe, ai khát húp đi!",
        "{name} bao nước cả xe, uống lẹ đi bà con!",
    ),
    "board": (
        "{names} về {prov}, nhích mông vô trong nằm!",
        "{names} lên xe, bỏ dép vô bọc, đừng chắn cửa!",
        "{names} về {prov}, chui tọt vô trong coi!",
    ),
    "board_mixed": (
        "{names} lên xe, nhích vô trong đừng chắn cửa!",
        "{names} có vé rồi, dồn vô trong cho người sau lên!",
    ),
    "dropoff": (
        "{prov} tới rồi! {names} gom đồ xuống lẹ!",
        "{names} xuống {prov}, coi chừng quên đồ đấy nha!",
        "{prov} đây, {names} vác balo bước xuống mau!",
    ),
    "gift": (
        "{name} bắn quà, uy tín nha!",
        "{name} chơi đẹp đấy, cảm ơn nha!",
        "{name} tặng quà kìa, anh em vỗ tay cái coi!",
        "Cảm ơn {name} nha, uy tín luôn!",
    ),
}


def line(kind: str, rng: random.Random | None = None, **fields) -> str:
    """Một câu cho tình huống `kind` (bốc ngẫu nhiên trong các câu cùng loại), điền {tên} từ `fields`."""
    text = (rng or random).choice(LINES[kind]).format(**fields)
    # chỗ điền đứng đầu câu («… nhờ! {hours} tới …» → «chừng 6 tiếng») thì viết hoa lại
    return re.sub(r"(^|[.!?]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), text)


def hours_phrase(hours: float) -> str:
    """Giờ xe chạy nói kiểu phụ xe: «chừng 40 phút», «chừng 26 tiếng»."""
    if hours < 1:
        return f"chừng {max(10, round(hours * 6) * 10)} phút"
    return f"chừng {round(hours)} tiếng"


def spoken_list(text: str) -> str:
    """«cá ngừ · bánh hỏi» → «cá ngừ, bánh hỏi» (dấu chấm giữa đọc không tự nhiên)."""
    return text.replace(" · ", ", ")
