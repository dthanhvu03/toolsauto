"""Câu nói của Anh Tư lơ xe (PLAN-128, sửa PLAN-131): chợ búa như lơ xe ngoài bến thật, ba kiểu nói anh chọn trên /control.

- «ben»: lơ xe bến xe miền Nam — cha nội, hổng chờ, nhích vô, đứng đó ngó hoài.
- «genz»: gét gô, khum, toang, quay xe, ét ô ét, đỉnh nóc kịch trần, uy tín.
- «geny»: chuẩn không cần chỉnh, bó tay chấm com, chất như nước cất, quẩy lên.
- «mix» (mặc định): mỗi lần nói bốc ngẫu nhiên trong cả ba kiểu.

Giọng đọc đều, không nhấn nhá: câu chỉ có dấu phẩy, dấu chấm (không «!»), không đuôi «nha». Chữ lóng tiếng Anh viết theo
cách đọc tiếng Việt (gét gô, ét ô ét) vì máy đọc tiếng Việt đọc sai chữ Anh. Không chửi thề (TikTok khoá live).
Mỗi tình huống vài câu, bốc ngẫu nhiên: nghe lại không lặp y chang. Sửa câu chỉ cần sửa bảng LINES; {tên} là chỗ điền.
"""

import random
import re

STYLES = ("ben", "genz", "geny")
TALK_STYLES = ("mix", *STYLES)

LINES: dict[str, dict[str, tuple[str, ...]]] = {
    # ---- lơ xe bến xe ------------------------------------------------------------------------------
    "ben": {
        "boarding": (
            "{dest} đây, {dest} đây, đi hông đi, gõ tên tỉnh lẹ lên.",
            "Ai về {dest} hông, đứng đó ngó hoài, gõ tên tỉnh rồi lên xe cái coi.",
            "Xe Tết đi {dest} nè mấy ông mấy bà, giường còn trống trơn, lên lẹ.",
            "Đi đâu đi đâu, {dest} hả, gõ tên tỉnh đi cha nội, Anh Tư xếp giường cho.",
        ),
        "seats_left": (
            "Còn có {n} giường à, ai đi thì lẹ cái chân lên.",
            "{n} giường nữa thôi đó, chậm là ở lại ăn Tết với nhà xe.",
            "Còn {n} chỗ, gõ lẹ lên, Anh Tư hổng chờ đâu.",
        ),
        "last_seat": (
            "Còn đúng một giường chót, ai lẹ tay người đó được, hổng giành.",
            "Một chỗ cuối, gõ lẹ đi, chậm là đứng ngoài ngó xe chạy.",
        ),
        "full": (
            "Kín giường rồi, đóng cửa, anh tài ơi chạy.",
            "Đủ rồi đủ rồi, hết chỗ, ai chưa lên ráng chờ chuyến sau.",
            "Chật ních rồi bà con, nằm sát vô, chạy nè.",
        ),
        "switch_lane": (
            "Thôi đổi tuyến, xe này chạy {dest}, ai chờ {dest} lên lẹ.",
            "Bên {dest} đông quá, quay đầu chạy {dest} luôn, lên lên.",
        ),
        "departure": (
            "Nhà xe dọn qua {station} rồi, ai về quê gõ tên tỉnh, lẹ lên kẻo hết giường.",
        ),
        "depart": (
            "Xe chạy, ngồi yên đó, đừng có đi tới đi lui, {hours} là tới {dest}.",
            "Xuất bến, giày dép bỏ bọc, đồ đạc nhét gầm giường, nằm im cho Anh Tư nhờ, {hours} tới {dest}.",
            "Anh tài đạp ga, đường {dest} {hours}, ai còn thức thả tim cho ổng chạy lẹ.",
        ),
        "rest": (
            "Ghé {place} nghỉ mười lăm phút, ai đi vệ sinh thì đi lẹ, nhớ biển số xe, lạc ráng chịu.",
            "Tới {place} rồi, ở đây có {specialty}, ai mua quà thì mua lẹ, đừng trả giá lâu.",
            "Dừng ăn cơm ở {place}, ăn lẹ lẹ, mười lăm phút xe chạy, hổng chờ ai đâu.",
        ),
        "honk": (
            "Bíp bíp, lên xe lên xe, còn ai ở dưới hông.",
            "Lên lẹ cái coi, đếm đủ đầu là chạy.",
            "Trời đất, còn ai trong nhà vệ sinh hông, ra lẹ, xe chạy bỏ đó.",
        ),
        "dropoff_bubble": (
            "{prov}, {prov}, ai xuống {prov} ôm đồ ra cửa lẹ.",
        ),
        "finish": (
            "Hết khách, anh tài quay đầu về bến rước chuyến mới.",
            "Xong một chuyến, ai chưa đi gõ tên tỉnh chờ đó, Anh Tư về liền.",
        ),
        "likes": (
            "{total} tim rồi, anh tài phê quá đạp ga luôn.",
            "Trời ơi tim gì nhiều dữ, {total} tim rồi, thả nữa đi bà con.",
        ),
        "relief_auto": (
            "Đông quá trời đông, nhà xe kêu thêm xe đi {dest}, ai chờ hướng đó lên luôn.",
            "Thêm xe nè, xe đi {dest} chạy liền, khỏi đứng chờ mỏi giò.",
        ),
        "relief_gift": (
            "Chịu chơi, {name} bao nguyên chiếc xe cho bà con đi {dest}, lên lẹ đi.",
            "{name} bao xe rồi, ai về {dest} lên ngồi miễn phí, cảm ơn {name} cái coi.",
        ),
        "relief_admin": (
            "Nhà xe cho thêm chuyến đi {dest}, ai chờ hướng đó lên lẹ lên.",
        ),
        "home": (
            "Trời đất {name}, ở ngay {prov} mà đòi đi xe, đi bộ về đi cha nội.",
            "{name} ở {prov} luôn hả, khỏi lên, về nhà ăn bánh tét đi.",
        ),
        "treat": (
            "{name} bao trà đá cả xe, chịu chơi dữ.",
            "Có {name} khao trà đá nè, uống lẹ đi bà con.",
        ),
        "board": (
            "{names} về {prov}, lên lên, nhích vô trong.",
            "{names} đi {prov} hả, lên lẹ, nằm giường trong cho Anh Tư.",
            "Rồi, {names} về {prov}, lên xe, người sau lẹ lên.",
        ),
        "board_mixed": (
            "{names} lên rồi, dồn vô trong cho người sau lên.",
            "Lên lẹ lên {names}, đừng đứng chắn cửa.",
        ),
        "dropoff": (
            "{prov}, {prov}, {names} xuống lẹ, coi lại đồ đạc, quên ráng chịu.",
            "Tới {prov} rồi, {names} ôm đồ xuống lẹ, xe còn chạy nữa.",
            "{names} ơi, {prov} tới rồi, còn ngủ hả, dậy xuống xe lẹ.",
        ),
        "gift": (
            "Ui, {name} tặng quà, chịu chơi quá, năm nay phát tài.",
            "{name} chơi lớn dữ, cảm ơn, Tết này hốt bạc.",
            "Cảm ơn {name}, có quà là Anh Tư la to hơn nè.",
        ),
    },
    # ---- gen Z -----------------------------------------------------------------------------------------
    "genz": {
        "boarding": (
            "Ai về {dest} điểm danh, gõ tên tỉnh vô, lên xe gét gô.",
            "Xe đi {dest} tới công chuyện rồi, gõ tên tỉnh là có giường, khum lằng nhằng.",
            "{dest} đây mọi người ơi, ai về quê ăn Tết thì gõ tên tỉnh, chốt đơn liền.",
            "Ủa alo, ai về {dest} mà còn đứng đó, gõ tên tỉnh lẹ đi.",
        ),
        "seats_left": (
            "Còn {n} giường thôi, chậm là ét ô ét đó.",
            "{n} chỗ cuối, ai nhanh tay thì chốt, chậm là toang.",
            "Còn {n} giường, gõ tên tỉnh liền, khum là lỡ chuyến.",
        ),
        "last_seat": (
            "Giường cuối cùng, ai lụm được là đỉnh nóc kịch trần.",
            "Một chỗ cuối, ai chậm là trầm cảm luôn đó.",
        ),
        "full": (
            "Kín giường rồi, đóng cửa, anh tài gét gô.",
            "Hết chỗ rồi, ai chưa lên thì chờ chuyến sau, đừng dỗi.",
            "Đủ người rồi, xe chạy liền, nằm thả lỏng đi mọi người.",
        ),
        "switch_lane": (
            "Bất ngờ chưa, xe này đổi qua đi {dest}, ai chờ hướng đó lên liền.",
            "Bên {dest} đông quá trời, xe quay xe chạy {dest} luôn.",
        ),
        "departure": (
            "Nhà xe dời qua {station} rồi, ai về quê gõ tên tỉnh, điểm danh liền.",
        ),
        "depart": (
            "Gét gô, xe lăn bánh rồi, {hours} là tới {dest}, ngủ một giấc là tới nơi.",
            "Xe chạy rồi mọi người, đường về {dest} {hours}, ai còn thức thì thả tim cho anh tài có động lực.",
            "Xuất phát, cất điện thoại đi, mà thôi cứ cầm xem live cũng được, {hours} là tới {dest}.",
        ),
        "rest": (
            "Tới {place} rồi, nghỉ mười lăm phút, đi vệ sinh, chụp hình sống ảo lẹ lẹ.",
            "Trạm {place} có {specialty}, ai mua làm quà thì mua, đừng để mẹ chê keo.",
            "Ghé {place} ăn lẹ mười lăm phút, ăn xong lên xe liền, đừng bắt cả xe chờ, kỳ lắm.",
        ),
        "honk": (
            "Ê mọi người, lên xe, anh tài sắp chạy rồi đó.",
            "Còn ai ở dưới hông, lên lẹ, khum là ở lại trạm luôn.",
            "Đếm người nè, thiếu ai là toang, lên xe lẹ.",
        ),
        "dropoff_bubble": (
            "Tới {prov} rồi, ai về {prov} xách đồ xuống, về nhà khoe với họ hàng.",
        ),
        "finish": (
            "Xong chuyến, mãi đỉnh, xe quay về bến đón đợt mới.",
            "Hết khách rồi, ai chưa đi thì gõ tên tỉnh chờ, Anh Tư quay lại liền.",
        ),
        "likes": (
            "{total} tim rồi, cháy quá, anh tài đạp ga.",
            "Tim nhiều dữ vậy trời, {total} tim, xe chạy như bay luôn.",
        ),
        "relief_auto": (
            "Đông quá xỉu ngang, nhà xe kêu thêm xe đi {dest}, ai chờ hướng đó lên luôn.",
            "Thêm xe rồi, xe đi {dest} chạy liền, khỏi chờ mòn mỏi.",
        ),
        "relief_gift": (
            "{name} bao nguyên chiếc xe đi {dest}, đỉnh nóc kịch trần bay phấp phới.",
            "{name} chơi lớn bao xe, ai về {dest} lên liền, cảm ơn {name} nhiều.",
        ),
        "relief_admin": (
            "Nhà xe thêm chuyến đi {dest}, ai chờ hướng đó lên liền.",
        ),
        "home": (
            "Ủa {name} ở ngay {prov} mà, đi bộ về nhà đi, khum cần xe đâu.",
            "{name} ở {prov} luôn hả, vậy về nhà ăn Tết luôn, khỏi lên xe.",
        ),
        "treat": (
            "{name} bao trà đá cả xe, mãi đỉnh.",
            "{name} khao trà đá, uy tín luôn.",
        ),
        "board": (
            "{names} về {prov}, lên xe, gét gô.",
            "{names} đã lên xe về {prov}, uy tín.",
            "Điểm danh {names}, về {prov}, lên xe liền.",
        ),
        "board_mixed": (
            "{names} lên xe rồi, xích vô cho người sau.",
            "Chào {names}, lên xe, nằm giường nào cũng được, khum kén.",
        ),
        "dropoff": (
            "Tới {prov} rồi, {names} xuống xe, về nhà khoe họ hàng đi.",
            "{names} ơi, {prov} tới rồi, xách đồ xuống, đừng bỏ quên sạc dự phòng.",
            "{prov} tới công chuyện, {names} xuống xe lẹ.",
        ),
        "gift": (
            "{name} tặng quà, uy tín, năm nay giàu.",
            "Cảm ơn {name}, đỉnh nóc kịch trần.",
            "{name} chơi lớn quá, Tết này nhận lì xì mỏi tay.",
        ),
    },
    # ---- gen Y -----------------------------------------------------------------------------------------
    "geny": {
        "boarding": (
            "Ai về {dest} thì gõ tên tỉnh, lên xe, chuẩn không cần chỉnh.",
            "Xe đi {dest} đây, ngon lành cành đào, gõ tên tỉnh là có giường.",
            "{dest} đây bà con, về quê ăn Tết thì gõ tên tỉnh, đừng ngồi chém gió nữa.",
            "Về {dest} hông, gõ tên tỉnh đi, kẻo hết giường lại ngồi khóc ròng.",
        ),
        "seats_left": (
            "Còn {n} giường thôi, chậm là bó tay chấm com.",
            "{n} chỗ nữa thôi, ai về quê thì nhanh tay kẻo lỡ.",
            "Còn {n} giường, gõ tên tỉnh liền, kẻo hết vé lại than trời.",
        ),
        "last_seat": (
            "Giường cuối cùng, ai nhanh thì được, chậm thì thôi xong.",
            "Còn đúng một chỗ, ai lẹ tay người đó hưởng.",
        ),
        "full": (
            "Kín chỗ rồi, xe chạy, quẩy lên anh tài.",
            "Hết giường rồi, ai chưa lên thì chuyến sau, kệ đi gì căng.",
            "Đủ khách, đóng cửa, lên đường thôi.",
        ),
        "switch_lane": (
            "Đổi tuyến, xe này đi {dest}, ai chờ hướng đó lên liền.",
            "Bên {dest} đông quá, xe này chạy {dest} luôn, chuẩn bài.",
        ),
        "departure": (
            "Nhà xe dời qua {station} rồi, ai về quê gõ tên tỉnh để xếp giường.",
        ),
        "depart": (
            "Lên đường thôi, {hours} là về tới {dest}, ai mệt thì làm một giấc cho khỏe.",
            "Xe chạy rồi, đường về {dest} {hours}, ngồi yên mà hưởng.",
            "Xuất bến, nhạc lên, quẩy lên, {hours} là tới {dest}.",
        ),
        "rest": (
            "Ghé {place} nghỉ mười lăm phút, ăn uống vệ sinh cho xong, nhớ biển số xe.",
            "Trạm {place} có {specialty}, mua về biếu ông bà là chuẩn cơm mẹ nấu.",
            "Dừng ăn cơm ở {place}, ăn nhanh còn đi, đừng ngồi tám chuyện.",
        ),
        "honk": (
            "Lên xe lên xe, ai còn ở dưới thì nhanh, xe chạy rồi.",
            "Đếm người nè, thiếu ai thì gọi, xe sắp đi.",
            "Ai còn ăn dở thì gói mang theo, xe chạy liền.",
        ),
        "dropoff_bubble": (
            "Tới {prov} rồi, ai xuống {prov} chuẩn bị đồ đạc.",
        ),
        "finish": (
            "Xong chuyến, hết sẩy, xe về bến đón khách mới.",
            "Hết khách rồi, ai chưa đi thì gõ tên tỉnh chờ chuyến sau.",
        ),
        "likes": (
            "{total} tim rồi, bá đạo thật, anh tài chạy hết tốc lực.",
            "Tim nhiều quá, {total} tim rồi, cảm ơn bà con.",
        ),
        "relief_auto": (
            "Đông quá, nhà xe tăng cường thêm xe đi {dest}, ai chờ hướng đó lên luôn.",
            "Có xe tăng cường đi {dest} rồi, khỏi chờ.",
        ),
        "relief_gift": (
            "{name} bao nguyên chiếc xe đi {dest}, bá đạo thật sự.",
            "Có {name} bao xe cho bà con về {dest}, chất như nước cất.",
        ),
        "relief_admin": (
            "Nhà xe thêm chuyến đi {dest}, ai chờ hướng đó lên xe.",
        ),
        "home": (
            "{name} ở ngay {prov} mà, đi bộ về cho khỏe, đi xe chi cho tốn.",
            "{name} ở {prov} luôn hả, thôi về nhà ăn Tết, khỏi lên xe.",
        ),
        "treat": (
            "{name} bao trà đá cả xe, chất như nước cất.",
            "Có {name} khao trà đá, quý hóa quá.",
        ),
        "board": (
            "{names} về {prov}, lên xe đi.",
            "{names} lên xe về {prov} rồi, chuẩn không cần chỉnh.",
            "Có {names} về {prov}, mời lên xe.",
        ),
        "board_mixed": (
            "{names} lên xe rồi, vô trong ngồi cho người sau lên.",
            "Mời {names} lên xe, nằm đâu cũng được.",
        ),
        "dropoff": (
            "Tới {prov} rồi, {names} xuống xe, nhớ coi lại đồ đạc.",
            "{prov} đây, {names} chuẩn bị xuống, về nhà ăn Tết vui vẻ.",
            "{names} ơi, tới {prov} rồi, xuống xe về với gia đình thôi.",
        ),
        "gift": (
            "Cảm ơn {name}, quý hóa quá, năm mới phát tài.",
            "{name} tặng quà, chất như nước cất, cảm ơn nhiều.",
            "Cảm ơn {name}, chúc năm mới an khang, tiền vô như nước.",
        ),
    },
}


def options(kind: str, style: str = "mix") -> tuple[str, ...]:
    """Các câu cho tình huống `kind` theo kiểu nói; «mix» (hoặc kiểu lạ) = gộp cả ba kiểu."""
    if style in STYLES:
        return LINES[style][kind]
    return tuple(text for s in STYLES for text in LINES[s][kind])


def line(kind: str, rng: random.Random | None = None, style: str = "mix", **fields) -> str:
    """Một câu cho tình huống `kind` (bốc ngẫu nhiên theo kiểu nói), điền {tên} từ `fields`."""
    text = (rng or random).choice(options(kind, style)).format(**fields)
    # chỗ điền đứng đầu câu («… nhờ. {hours} tới …» → «Chừng 6 tiếng») thì viết hoa lại
    return re.sub(r"(^|[.!?]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), text)


def hours_phrase(hours: float) -> str:
    """Giờ xe chạy nói kiểu phụ xe: «chừng 40 phút», «chừng 26 tiếng»."""
    if hours < 1:
        return f"chừng {max(10, round(hours * 6) * 10)} phút"
    return f"chừng {round(hours)} tiếng"


def spoken_list(text: str) -> str:
    """«cá ngừ · bánh hỏi» → «cá ngừ, bánh hỏi» (dấu chấm giữa đọc không tự nhiên)."""
    return text.replace(" · ", ", ")
