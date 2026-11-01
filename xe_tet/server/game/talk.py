"""Câu nói của Anh Tư lơ xe (PLAN-128): nói như phụ xe khách thật — giọng miền Nam, chữ đời thường, không như máy đọc.

- Mỗi tình huống vài câu, bốc ngẫu nhiên: nghe lại không lặp y chang (lặp nguyên câu là thấy «máy» liền).
- Không đọc số km như báo cáo: phụ xe nói giờ đi («chừng 26 tiếng là tới»), tên bến, tên tỉnh.
- Chữ của nghề: lên xe lẹ, còn giường chót, kín giường, nhớ biển số xe, coi lại đồ đạc, anh tài ơi chạy.
Sửa câu chỉ cần sửa bảng LINES; {tên} trong câu là chỗ điền.
"""

import random

LINES: dict[str, tuple[str, ...]] = {
    # ---- ở bến -------------------------------------------------------------------------------
    "boarding": (
        "Xe đi {dest} vô bến rồi nè! Ai về quê gõ tên tỉnh, Anh Tư xếp giường liền.",
        "{dest}, {dest} đây bà con ơi! Về quê ăn Tết thì gõ tên tỉnh lên xe nha.",
        "Xe Tết đi {dest} đây! Nhà ở đâu gõ tên tỉnh, giường nằm có sẵn hết rồi.",
        "Ai về hướng {dest} hông? Gõ tên tỉnh đi, lên xe lẹ còn kịp chuyến nè.",
    ),
    "seats_left": (
        "Còn {n} giường thôi nha, ai đi thì lẹ lẹ lên!",
        "Còn {n} chỗ nữa thôi bà con ơi, chậm là đi chuyến sau á.",
        "{n} giường chót nè, gõ tên tỉnh lẹ lên!",
    ),
    "last_seat": (
        "Còn đúng một giường chót nè, ai nhanh tay thì được!",
        "Một chỗ cuối cùng! Ai về quê gõ lẹ đi!",
    ),
    "full": (
        "Kín giường rồi nha! Anh tài ơi, chạy!",
        "Đủ khách rồi, bà con nằm yên, xe chạy liền nè.",
        "Đủ rồi đủ rồi, đóng cửa, xe chạy nha!",
    ),
    "switch_lane": (
        "Xe này đổi qua đi {dest} nha, ai chờ hướng đó lên luôn!",
        "Hướng {dest} có người chờ nè, xe này chạy {dest} luôn nha!",
    ),
    "departure": (
        "Nhà xe dời qua {station} rồi nha! Ai về quê gõ tên tỉnh để xếp giường.",
    ),
    # ---- trên đường ---------------------------------------------------------------------------
    "depart": (
        "Xe chạy nha bà con! Đi {dest} {hours} là tới, ai mệt thì làm một giấc.",
        "Anh tài cho xe lăn bánh rồi! Đường {dest} {hours}, ai còn thức thì thả tim cho anh tài chạy lẹ.",
        "Xuất bến! Đồ đạc để gọn, giày dép bỏ bọc, nằm nghỉ cho khỏe nha. {hours} là về tới {dest}.",
    ),
    "rest": (
        "Xe ghé {place} nghỉ mười lăm phút nha! Ai ăn uống, đi vệ sinh thì xuống, nhớ biển số xe.",
        "Tới trạm {place} rồi, nghỉ chân chút! Ở đây có {specialty}, ai mua làm quà thì mua lẹ.",
        "Dừng ăn cơm ở {place} nha bà con! Ăn lẹ lẹ, mười lăm phút xe chạy à.",
    ),
    "honk": (
        "Bíp bíp! Lên xe đi bà con, xe chạy rồi nè!",
        "Ai còn ở dưới lên lẹ nha, đếm đủ người là chạy!",
        "Lên xe lên xe! Còn ai trong nhà vệ sinh hông?",
    ),
    "dropoff_bubble": (
        "Tới {prov} rồi bà con ơi! Ai xuống {prov} chuẩn bị đồ đạc nha!",
    ),
    "finish": (
        "Trả khách xong rồi, xe quay đầu về bến đón chuyến mới nha!",
        "Hết khách rồi! Ai chưa đi thì gõ tên tỉnh chờ xe sau, Anh Tư về liền.",
    ),
    "likes": (
        "{total} tim rồi! Anh tài đạp ga nè!",
        "Tim nhiều quá, anh tài chạy hăng luôn! {total} tim rồi đó.",
    ),
    # ---- xe tăng cường ---------------------------------------------------------------------------
    "relief_auto": (
        "Đông khách quá, nhà xe kêu thêm xe đi {dest}, bà con chờ hướng đó lên luôn nha!",
        "Kêu thêm xe rồi nè! Xe đi {dest} chạy liền, khỏi chờ.",
    ),
    "relief_gift": (
        "{name} bao nguyên chiếc xe cho bà con đi {dest}! Cảm ơn {name} nha, xe chạy liền!",
        "Có {name} bao xe nè, bà con hướng {dest} lên xe đi luôn!",
    ),
    "relief_admin": (
        "Nhà xe cho thêm xe đi {dest} nè, ai chờ hướng đó lên xe nha!",
    ),
    # ---- người xem ---------------------------------------------------------------------------------
    "home": (
        "{name} ở ngay {prov} rồi mà, đi bộ về nhà cho khỏe!",
        "Ủa {name} ở {prov} luôn hả, khỏi đi xe, về nhà ăn Tết thôi!",
    ),
    "treat": (
        "{name} bao cả xe trà đá nè! Cảm ơn nhiều nha!",
        "Có {name} khao trà đá cả xe, quý hóa quá!",
    ),
    "board": (
        "{names} lên xe về {prov} nè!",
        "Có {names} về {prov}, lên xe đi!",
        "{names} lên xe rồi, về {prov} ăn Tết!",
    ),
    "board_mixed": (
        "{names} lên xe rồi nha!",
        "Có thêm {names} lên xe nè!",
    ),
    "dropoff": (
        "Tới {prov} rồi! {names} xuống xe nha, nhớ coi lại đồ đạc.",
        "{prov} đây bà con ơi! {names} chuẩn bị xuống, ăn Tết vui vẻ nha!",
        "Ai xuống {prov} nè? {names}, tới nhà rồi đó!",
    ),
    "gift": (
        "Cảm ơn {name} nha, quý hóa quá!",
        "{name} tặng quà cho cả xe nè, cảm ơn nha!",
        "Cảm ơn {name} nhiều nha, Tết này phát tài!",
    ),
}


def line(kind: str, rng: random.Random | None = None, **fields) -> str:
    """Một câu cho tình huống `kind` (bốc ngẫu nhiên trong các câu cùng loại), điền {tên} từ `fields`."""
    return (rng or random).choice(LINES[kind]).format(**fields)


def hours_phrase(hours: float) -> str:
    """Giờ xe chạy nói kiểu phụ xe: «chừng 40 phút», «chừng 26 tiếng»."""
    if hours < 1:
        return f"chừng {max(10, round(hours * 6) * 10)} phút"
    return f"chừng {round(hours)} tiếng"


def spoken_list(text: str) -> str:
    """«cá ngừ · bánh hỏi» → «cá ngừ, bánh hỏi» (dấu chấm giữa đọc không tự nhiên)."""
    return text.replace(" · ", ", ")
