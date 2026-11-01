"""Câu nói của Anh Tư lơ xe (PLAN-128): nói như lơ xe khách ngoài bến thật — chợ búa, cộc, lẹ, la ó, giọng miền Nam.

- Lơ xe không nói chuẩn mực: «lên lẹ lên cha nội», «hổng chờ à nghen», «nhích vô trong coi», «mấy ông mấy bà».
  Không chửi thề (TikTok khoá live), còn lại cứ đời như ngoài bến.
- Mỗi tình huống vài câu, bốc ngẫu nhiên: nghe lại không lặp y chang (lặp nguyên câu là thấy «máy» liền).
- Không đọc số km như báo cáo: lơ xe nói giờ đi («chừng 26 tiếng»), tên bến, tên tỉnh.
Sửa câu chỉ cần sửa bảng LINES; {tên} trong câu là chỗ điền.
"""

import random
import re

LINES: dict[str, tuple[str, ...]] = {
    # ---- ở bến -------------------------------------------------------------------------------
    "boarding": (
        "{dest} đây! {dest} đây! Đi hông đi? Gõ tên tỉnh lẹ lên, xe sắp chạy rồi!",
        "Ê ê, ai về {dest} hông? Đứng đó ngó hoài, gõ tên tỉnh rồi lên xe cái coi!",
        "Xe Tết đi {dest} nè mấy ông mấy bà ơi! Lên lên lên, giường còn trống trơn nè!",
        "Đi đâu đi đâu? {dest} hả? Gõ tên tỉnh đi cha nội, Anh Tư xếp giường cho!",
    ),
    "seats_left": (
        "Còn có {n} giường à nghen! Ai đi thì lẹ cái chân lên!",
        "{n} giường nữa thôi đó! Chậm là ở lại ăn Tết với nhà xe nha!",
        "Còn {n} chỗ! Gõ lẹ lên, Anh Tư hổng chờ đâu à!",
    ),
    "last_seat": (
        "Còn đúng một giường chót! Ai lẹ tay người đó được, hổng giành nha!",
        "Một chỗ cuối nè! Gõ lẹ đi, chậm là đứng ngoài ngó xe chạy đó!",
    ),
    "full": (
        "Kín giường rồi! Đóng cửa! Anh tài ơi chạy!",
        "Đủ rồi đủ rồi, hết chỗ rồi! Ai chưa lên thì ráng chờ chuyến sau nha!",
        "Chật ních rồi bà con ơi! Nằm sát vô, chạy nè!",
    ),
    "switch_lane": (
        "Thôi đổi tuyến, xe này chạy {dest}! Ai chờ {dest} lên lẹ, lẹ!",
        "Bên {dest} đông quá, quay đầu chạy {dest} luôn! Lên lên!",
    ),
    "departure": (
        "Nhà xe dọn qua {station} rồi nha! Ai về quê gõ tên tỉnh, lẹ lên kẻo hết giường!",
    ),
    # ---- trên đường ---------------------------------------------------------------------------
    "depart": (
        "Xe chạy nè! Ngồi yên đó, đừng có đi tới đi lui! {hours} là tới {dest}.",
        "Xuất bến! Giày dép bỏ bọc, đồ đạc nhét gầm giường, nằm im cho Anh Tư nhờ! {hours} tới {dest}.",
        "Anh tài ơi đạp ga! Đường {dest} {hours}, ai còn thức thả tim cho ổng chạy lẹ!",
    ),
    "rest": (
        "Ghé {place} nghỉ mười lăm phút! Ai đi vệ sinh thì đi lẹ, nhớ biển số xe, lạc là ráng chịu nha!",
        "Tới {place} rồi! Ở đây có {specialty}, ai mua quà thì mua lẹ, đừng có trả giá lâu!",
        "Dừng ăn cơm {place} nè! Ăn lẹ lẹ, mười lăm phút xe chạy, hổng chờ ai đâu à!",
    ),
    "honk": (
        "Bíp bíp! Lên xe! Lên xe! Còn ai ở dưới hông?",
        "Ê, lên lẹ cái coi! Đếm đủ đầu là chạy à nghen!",
        "Trời đất, còn ai trong nhà vệ sinh hông? Ra lẹ, xe chạy bỏ đó!",
    ),
    "dropoff_bubble": (
        "{prov}! {prov}! Ai xuống {prov} ôm đồ ra cửa lẹ nha!",
    ),
    "finish": (
        "Hết khách! Anh tài ơi quay đầu, về bến rước chuyến mới!",
        "Xong một chuyến! Ai chưa đi gõ tên tỉnh chờ đó, Anh Tư về liền!",
    ),
    "likes": (
        "{total} tim rồi! Anh tài phê quá đạp ga luôn nè!",
        "Trời ơi tim gì nhiều dữ! {total} tim rồi, thả nữa đi bà con!",
    ),
    # ---- xe tăng cường ---------------------------------------------------------------------------
    "relief_auto": (
        "Đông quá trời đông! Nhà xe kêu thêm xe đi {dest}, ai chờ hướng đó lên luôn!",
        "Thêm xe nè! Xe đi {dest} chạy liền, khỏi đứng chờ mỏi giò!",
    ),
    "relief_gift": (
        "Chịu chơi! {name} bao nguyên chiếc xe cho bà con đi {dest}! Lên lẹ đi!",
        "{name} bao xe rồi! Ai về {dest} lên ngồi miễn phí nè, cảm ơn {name} cái coi!",
    ),
    "relief_admin": (
        "Nhà xe cho thêm chuyến đi {dest}! Ai chờ hướng đó lên lẹ lên!",
    ),
    # ---- người xem ---------------------------------------------------------------------------------
    "home": (
        "Trời đất {name}, ở ngay {prov} mà đòi đi xe? Đi bộ về đi cha nội!",
        "{name} ở {prov} luôn hả? Khỏi lên, về nhà ăn bánh tét đi!",
    ),
    "treat": (
        "{name} bao trà đá cả xe! Chịu chơi dữ!",
        "Có {name} khao trà đá nè, uống lẹ đi bà con!",
    ),
    "board": (
        "{names} về {prov}! Lên lên, nhích vô trong!",
        "{names} đi {prov} hả? Lên lẹ, nằm giường trong cho Anh Tư!",
        "Rồi, {names} về {prov}, lên xe! Người sau lẹ lên!",
    ),
    "board_mixed": (
        "{names} lên rồi! Dồn vô trong cho người sau lên!",
        "Lên lẹ lên, {names}! Đừng đứng chắn cửa!",
    ),
    "dropoff": (
        "{prov}! {prov}! {names} xuống lẹ, coi lại đồ đạc, quên ráng chịu nha!",
        "Tới {prov} rồi! {names} ôm đồ xuống lẹ, xe còn chạy nữa!",
        "{names} ơi, {prov} tới rồi, còn ngủ hả? Dậy xuống xe lẹ!",
    ),
    "gift": (
        "Ui, {name} tặng quà! Chịu chơi quá, năm nay phát tài nha!",
        "{name} chơi lớn dữ! Cảm ơn nha, Tết này hốt bạc!",
        "Cảm ơn {name} nghen! Có quà là Anh Tư la to hơn nè!",
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
