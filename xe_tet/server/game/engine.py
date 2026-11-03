"""Luật chơi Xe Tết: máy trạng thái thuần, thời gian truyền vào từ ngoài để test được.

Vòng một chuyến: BOARDING → (DRIVING → REST | DROPOFF)* → FINISH → BOARDING.
Tuyến thật (BRD-tuyen-xe.md): bến có nhiều làn theo hướng; mỗi lần một xe một làn xuất bến; điểm dừng theo km thật
(`Network.plan`: thứ tự ghé + km xe chạy kể cả rẽ nhánh); cảnh, đèo / hầm, trạm nghỉ lấy theo chỗ xe đang chạy.
SPECIAL chen vào BOARDING / DRIVING / REST khi có quà lớn, xong quay lại đúng pha và thời gian còn lại.
Xe tăng cường (PLAN-125) chạy ngầm song song: làn đủ một xe người chờ, hoặc người đang chờ tặng quà bậc băng rôn → một
xe chở 24 người chạy theo tuyến thật, tới nơi đọc tên như xe chính; không vẽ 3D.
Mọi thứ overlay cần vẽ đi qua `snapshot()` và `outbox` (sự kiện rời rạc).
"""

import hashlib
import math
from collections.abc import Callable
import random
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .moderation import allow_chat, clean_name
from . import season
from .answers import faq, is_question
from .network import PASS_SPAN_KM, TUNNEL_SPAN_KM, Network, Trip
from .parser import FOOD_EMOJI, normalize, parse
from .provinces import BY_KEY, specialty_of
from .talk import hours_phrase, line, spoken_list
from .trivia import LETTERS, answer_of, fact, make_quiz

SEATS = 24
BOARD_SECONDS = 180.0
FULL_BUS_SECONDS = 10.0
# Đủ giường mà vừa có nhiều người lên dồn (cả hàng chờ được xếp lên lúc vào bến): giữ xe thêm cho lơ xe kịp đọc tên từng
# người (PLAN-147 đọc ~5 tên / câu, câu cách nhau 5 giây ≈ 1 giây / người) — trước: 24 người lên cùng lúc, 10 giây xe chạy,
# hầu hết không được đọc tên, hàng người ở cửa xe biến mất
NAME_READ_S = 1.0
NAME_LEAD_S = 5.0
NAME_WINDOW_S = 40.0
FULL_HOLD_MAX = 35.0
REST_SECONDS = 90.0
HONK_BEFORE_END = 15.0
FINISH_SECONDS = 12.0
SPECIAL_SECONDS = 20.0
DROPOFF_BASE = 3.0  # giây mở màn thả khách, cộng thêm mỗi trang tên
EMPTY_BOARD_RETRY = 30.0  # hết giờ đón mà xe trống: đổi sang làn có người chờ / chờ thêm
# Thời gian chạy (BR-7, sửa PLAN-130): km thật, giờ nén — xa thì lâu hơn rõ rệt nhưng không tỉ lệ thẳng (người chờ xe
# sau không phải đợi gấp 6 lần): giây chạy đường = dài nhất × (km / LONGEST_KM)^DRIVE_CURVE, tối thiểu DRIVE_MIN.
# «Dài nhất» admin chỉnh (`trip_minutes`, mặc định 8 phút): 300 km ≈ 2:10, 900 km ≈ 4:50, 1.700 km ≈ 7:55.
LONGEST_KM = 1750.0
DRIVE_CURVE = 0.75
DRIVE_MIN_SECONDS = 45.0
TRIP_MINUTES = 8.0
RUSH_DRIVE_FACTOR = 0.6  # cao điểm: phần chạy đường còn 60 %
LEG_SECONDS_MIN = 6.0
# Đồng hồ trên xe (PLAN-130): giờ VN lúc xuất bến + km / BUS_KMH, mỗi trạm dừng thêm 30 phút — lơ xe nói «chừng 26
# tiếng» thì đồng hồ trên xe chạy đủ 26 tiếng, trời sáng / tối theo đồng hồ đó.
REST_HOURS = 0.5
REST_MIN_KM = 150  # chuyến ngắn hơn không ghé trạm (xe khách thật nghỉ sau ~4 giờ lái — Luật TTATGT 2024)
TWO_RESTS_KM = 900  # chuyến dài hơn → nghỉ 2 trạm, nhưng chỉ khi không ai chờ xe sau (trạm là cảnh vui, không bắt chờ)
# Qua đèo / hầm chạy chậm lại để người xem kịp thấy (nén 3–7 km / giây thì đèo 16 km lướt qua trong 2–5 giây);
# xe khách thật cũng bò qua đèo. Chỉ kéo dài thêm ~10–15 giây mỗi đèo.
PASS_SECONDS = 16.0
TUNNEL_SECONDS = 8.0
# Giờ cao điểm (BR-9: theo từng hướng): làn của xe đang chạy còn một xe khách chờ → chạy nhanh hơn, 1 trạm ngắn.
RUSH_QUEUE = 24
RUSH_REST_SECONDS = 45.0
# Chọn làn xuất bến (BR-4, sửa 01/11): người chờ lâu nhất đi trước — xe chạy làn của vé chờ cũ nhất. Mô phỏng 4 giờ
# (bến TP.HCM, 1 comment / 20 s): 82 % người được lên xe trong 30 phút, làn thiệt nhất 78 % — hơn hẳn chọn theo số
# người chờ (làn nhỏ bị bỏ đói còn 24–46 %). Dễ giải thích với người xem: «ai chờ trước đi trước».
BOARD_AVG_START = 120.0  # ước lượng giờ đón / giờ chạy một chuyến trước khi đo được chuyến thật (ước giờ chờ trên vé)
RUN_AVG_START = 600.0
AVG_WEIGHT = 0.4  # trung bình trượt: chuyến mới đo chiếm 40 %
TICKET_IDLE = 0.0  # >0: người chờ im lặng quá chừng này giây thì bỏ vé. Anh 03/11: im lặng vẫn là đang xem live → mặc định không bỏ
QUEUE_SHOW = 6  # số người chờ hiện tên trên màn hình
STAYING_SHOW = 8
REST_ORDERS_SHOW = 4
SHARE_COOLDOWN = 60.0
NOTICE_COOLDOWN = 20.0  # «không về» / tỉnh bến đi lặp lại: chỉ báo lần đầu trong 20 giây (chống spam thẻ + lơ xe)
LIKE_MAX = 10_000  # một sự kiện tim tối đa (chặn số ảo)
# Xe tăng cường (PLAN-125): một xe chở ~110–220 khách / giờ, phòng rất đông chỉ ~40 % lên được xe trong 30 phút.
RELIEF_MAX = 4  # xe tăng cường tự động chạy cùng lúc (giữ dải trên màn hình đọc được)
RELIEF_MAX_GIFT = 6  # xe do quà được vượt mốc tự động
RELIEF_GIFT_TIER = 3  # bậc băng rôn (100 xu): người đang giữ chỗ đạt bậc này → xe tăng cường chạy ngay làn của họ
STAYING_KEEP = 30  # nhớ 30 người «ở lại» gần nhất
SPECIALS_PER_GIFT = 3  # một lần tặng vượt nhiều mốc 1000 xu: tối đa 3 lần cả xe chúc Tết
VENDOR_XU = 10  # anh 03/11: cả phòng góp đủ chừng này xu → cô bán hàng lên xe bán nem, bì, bánh mì (một lần mỗi chuyến)
VENDOR_STOP_S = 5.0  # xe tấp vào lề cho cô lên
# anh 03/11: gọi một lần là cô ở trên xe bán suốt chuyến (tới điểm thả khách cuối), xe vẫn chạy bình thường
HUNGER_PER_MIN = 12.0  # % no bụng tụt mỗi phút xe chạy (chuyến ~8 phút: giữa chuyến bắt đầu có người «sắp đói»)
HUNGRY = 30.0  # dưới chừng này % là «sắp đói»: hiện 😋 cạnh tên, lơ xe gọi tên nhắc mua đồ ăn
HUNGER_TALK_GAP = 60.0  # lơ xe nhắc người sắp đói tối đa một lần / chừng này giây (gom tên)
VENDOR_NAME = "Cô Ba"
SNACKS = {"nem": ("Nem chua", "🍢"), "bi": ("Bì cuốn", "🌯"), "banh_mi": ("Bánh mì", "🥖")}
VENDOR_REMIND_GAP = 90.0  # lơ xe nhắc góp gọi cô bán hàng tối đa một lần / chừng này giây


def avatar_url(raw: object) -> str:
    """Chỉ nhận link ảnh https gọn (đưa thẳng vào thẻ <img> trên overlay)."""
    url = str(raw or "")
    return url if url.startswith("https://") and len(url) <= 800 and not any(c in url for c in "\"'<> \\") else ""


def who_of(names: list[str]) -> str:
    """«An», «An và Bình», «An, Bình và Chi», «An, Bình, Chi và 2 người nữa» — lơ xe gọi gộp tên."""
    if len(names) > 3:
        return ", ".join(names[:3]) + f" và {len(names) - 3} người nữa"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" và {names[-1]}"


def snack_of(text: str) -> str | None:
    """«nem», «2 bánh mì», «bì cuốn» → món; câu dài / «xe bị gì» thì không («bị» bỏ dấu cũng là «bi»)."""
    words = normalize(text).split()
    if not words or len(words) > 5:
        return None
    norm = " ".join(words)
    if "banh mi" in norm or "banhmi" in words:
        return "banh_mi"
    if "nem" in words:
        return "nem"
    # «bì» và «bị» bỏ dấu đều là «bi»: có dấu huyền mới tính; gõ không dấu thì phải đúng «bi» / «bi cuon» / «mua bi»
    if "bi" in words and ("bì" in text.lower() or "bi cuon" in norm or norm in ("bi", "mua bi", "cho bi", "lay bi")):
        return "bi"
    return None


# ---- đổi gió cho live đỡ lặp (anh 03/11: «game lặp đi lặp lại chán», TikTok hạn chế vì tưởng phát video quay sẵn) ----
QUIZ_GAP = 180.0  # giây giữa hai câu đố (admin đặt trên /control)
QUIZ_SECONDS = 40.0  # giây người xem gõ A / B / C (lơ xe đọc câu hỏi đã mất ~10 giây — anh 03/11 «chưa đọc kịp»)
QUIZ_RESULT_S = 12.0  # thẻ đáp án còn trên màn hình chừng này giây
QUIZ_LEAD_S = 10.0  # câu đố tự bật chỉ khi còn ≥ giờ trả lời + đáp án + chừng này giây mới tới điểm dừng kế (anh 03/11:
# «vừa bật câu đố lên thì nhảy» — băng «Về tới …» che mất)
QUIZ_WINNERS = 3  # ba người trả lời đúng sớm nhất được đọc tên + điểm đua tỉnh
QUIZ_RACE = 3
QUIZ_RECENT = 12  # không đố lại tỉnh vừa đố
FACT_GAP = 75.0
ARRIVE_SHOW_KM = 10.0  # còn chừng này km tới điểm thả khách thì màn ghi tên tỉnh đó
PLACE_HOLD_KM = 15.0  # tên tỉnh mới phải giữ chừng này km mới đổi trên màn (ranh tỉnh / nối hai tuyến: hết nhảy qua lại)  # lơ xe kể chuyện tỉnh đang đi qua tối đa một lần / chừng này giây
INCIDENTS = {  # sự cố dọc đường: tự xong sau INCIDENT_SECONDS giây; tim làm nhanh hơn, tặng quà góp đủ thì xong ngay
    "tire": ("🛞", "Xe xẹp lốp", "thay lốp"),
    "jam": ("🚗", "Kẹt xe", "mở đường"),
    "cattle": ("🐃", "Đàn trâu qua đường", "lùa trâu"),
}
INCIDENT_CHANCE = 0.6  # mỗi chuyến từ INCIDENT_MIN_KM: khả năng gặp một sự cố
INCIDENT_MIN_KM = 80.0
INCIDENT_SECONDS = 30.0
INCIDENT_XU = 5
INCIDENT_LIKE_S = 0.25  # mỗi tim bớt chừng này giây chờ
INCIDENT_LIKE_MAX = 0.6  # tim bớt tối đa 60 % thời gian chờ
WHAT = {"toll": "qua trạm", "police": "nộp phạt", **{k: v[2] for k, v in INCIDENTS.items()}}
WEATHER_ODDS = {  # (kiểu, khả năng) khi xe vào vùng mới / xuất bến; còn lại trời quang
    "bac": (("drizzle", 0.45), ("fog", 0.2)),
    "trung": (("rain", 0.3), ("fog", 0.1)),
    "taynguyen": (("fog", 0.35), ("rain", 0.2)),
    "nam": (("rain", 0.3),),
}
WEATHER_TALK_GAP = 60.0
CHATTER_GAP = 45.0  # AI đáp chuyện phiếm (không phải câu hỏi) tối đa một câu / chừng này giây
CHATTER_PER_VIEWER = 180.0  # mỗi người được AI đáp chuyện phiếm tối đa một lần / 3 phút
CHATTER_KEEP = 5
NAME_HOLD_MAX = 25.0  # hết giờ đón mà lơ xe còn đọc tên người lên xe: xe chờ đọc xong, tối đa chừng này giây (anh 03/11)
ROLL_IDLE = 15 * 60.0  # điểm danh (anh 03/11): tới lượt lên xe mà im lặng quá chừng này → lơ xe gọi tên trước khi xếp giường
ROLL_WAIT = 45.0  # giây chờ người được gọi tên thả tim / bình luận; giường giữ cho họ trong lúc chờ
ROLL_MISS_MAX = 2  # lỡ điểm danh chừng này lần thì bỏ vé (lần đầu chỉ lùi xuống chuyến sau)
SPECIALS_QUEUE_MAX = 3  # cảnh chúc Tết chờ chiếu tối đa (quà to dồn dập không làm xe đứng hàng chục phút)
BOOST_MAX = 2.0
BOOST_PER_LIKE = 0.01
BOOST_HALF_LIFE = 6.0
CHAT_COOLDOWN = 5.0
VIA_TALK_GAP = 40.0  # giây: chuyến nén ~4 phút qua cả chục tỉnh — gọi tỉnh nào cũng gọi thì lơ xe nói liên tục
WHERE_COOLDOWN = 15.0
# Bắt xe dọc đường (PLAN-136): xe tuyến cố định đón khách ở điểm dừng đón trả dọc đường (Thông tư 36/2024), người đi hẹn
# trước rồi ra điểm đón chờ. Chuyến chạy đường bị nén (nghìn km vài phút) nên điểm đón đặt theo GIÂY THẬT phía trước xe.
PICKUP_LEAD = 20.0  # giây: điểm đón cách xe chừng này — người xem kịp thấy «ra điểm đón chờ» rồi thấy xe tới
PICKUP_MARGIN = 10.0  # giây: quê phải còn xa hơn điểm đón ít nhất chừng này (sắp qua thì hẹn xe sau)
PICKUP_TALK_GAP = 8.0  # giây giữa hai câu lơ xe về đón dọc đường (phòng đông nhiều người cùng bắt xe)
# Xăng / độ bẩn của xe (PLAN-137): chạy thì hết xăng + bẩn dần; ở bến / trạm người xem gõ «đổ xăng», «rửa xe».
FUEL_RANGE_KM = 2500.0  # một bình chạy ~2.500 km
DIRT_KM = 3000.0  # bẩn hẳn sau ~3.000 km (mưa phùn miền Bắc ×1,8)
FUEL_PER = 0.2  # mỗi lần «đổ xăng»
WASH_PER = 0.25  # mỗi lần «rửa xe»
CARE_COOLDOWN = 10.0  # mỗi người 10 giây một lần
CARE_TALK_GAP = 8.0
FUEL_BONUS = 0.10  # xuất bến bình ≥ 80 %: chạy nhanh hơn 10 %
CLEAN_BONUS = 0.05  # xe sạch (bẩn ≤ 20 %): thêm 5 % — thiếu thì vẫn chạy bình thường, không chặn ai
BOARD_LOCK = 10.0  # giây cuối giờ đón: người đã ngồi không đổi tỉnh / bỏ vé được nữa (anh dặn 02/11 «10s lên xe thì ko cho
# ai xuống hết»)
OTHER_DIR_GAP = 20.0  # giây giữa hai lần lơ xe nhắc «đây là chuyến đi …, ai đi hướng khác đợi chuyến sau»
STATION_VOTES = 3  # số người gọi một bến để xe ra bến đó (PLAN-136, live 02/11 «cho xe ra bến khác»)
STATION_VOTE_TTL = 900.0  # phiếu gọi bến giữ 15 phút
STATION_TALK_GAP = 10.0
BACK_TALK_GAP = 10.0  # lơ xe trêu người vừa về quê đã quay ra bến
ASK_GAP = 12.0  # giây giữa hai câu lơ xe trả lời câu hỏi có sẵn (PLAN-135)
ASK_PER_VIEWER = 30.0  # mỗi người hỏi tối đa 30 giây một lần (hỏi dồn không chiếm hết lời lơ xe)
QUESTIONS_KEEP = 10  # hàng câu hỏi chờ AI: giữ 10 câu mới nhất
SAME_HOME_GAP = 30.0  # giây giữa hai lần lơ xe ghép đôi người cùng quê
WELCOME_GAP = 20.0  # giây giữa hai lần lơ xe chào khách quay lại (đầu buổi nhiều người cũ vào cùng lúc)
INVITE_LIKES = 15  # tim trong chuyến của một người chưa có vé → lơ xe gọi tên mời lên xe (người xem lặng lẽ, chưa comment)
INVITE_GAP = 45.0  # giây giữa hai lần mời; mỗi người được mời một lần mỗi buổi
PARCELS_MAX = 3  # thùng quà Tết mỗi người mỗi chuyến (quà combo dồn dập không chất kín gầm xe một người)  # tra vé: mỗi người 15 giây một lần (spam «xe nào» không chiếm hết thẻ trên màn hình)
REST_ACTION_COOLDOWN = 3.0
NAMES_PER_PAGE = 4  # thả khách: đọc tên tất cả, mỗi trang 4 người (chữ to đọc được trên điện thoại)
PAGE_SECONDS = 3.5
LIKE_MILESTONES = (1000, 5000, 10000)
VN = ZoneInfo("Asia/Ho_Chi_Minh")  # máy chủ chạy UTC; đếm ngược Tết phải theo ngày Việt Nam
SPECIAL_FROM = ("BOARDING", "DRIVING", "REST")  # quà lớn chen ngay ở các pha này, xong quay lại đúng chỗ
FLAT = {"wind": 0.0, "pass": None, "tunnel": False, "climb": 0}  # đứng ở bến / trạm: đường thẳng, phẳng
# Tự chiếu xe (PLAN-130): «events» theo chuyện hay, «rotate» xoay vòng đều
FEATURE_MODES = ("off", "events", "rotate")
FEATURE_MIN_SECONDS = 20.0  # xe chính lên màn hình ít nhất chừng này mới nhảy sang xe tăng cường
FEATURE_LEAD = 25.0  # chuyển sang xe tăng cường khi còn ~25 giây là tới điểm thả khách (kịp thấy xe chạy tới)
FEATURE_AFTER_DROP = 8.0  # thả khách xong ở lại xem thêm chút rồi về xe chính
# Lên sóng theo điểm (PLAN-141, anh chọn 02/11): khách trên xe tăng cường tặng quà / bình luận / thả tim nhiều → xe được chiếu
# lâu hơn lúc xe chính chỉ đang chạy đường trơn. Điểm trong buổi: 1 xu = 3, 1 bình luận = 1 (tối đa 30 / người), 50 tim = 1.
STAGE_PER_XU = 3.0
STAGE_COMMENTS_MAX = 30
STAGE_LIKES_PER_POINT = 50.0
SHOW_BASE = 15.0  # giây chiếu tối thiểu một lượt
SHOW_PER_POINT = 0.2  # +1 giây mỗi 5 điểm
SHOW_MAX = 60.0  # tối đa một lượt (anh chọn 60)
SHOW_AGAIN = 90.0  # xe vừa lên sóng thì 90 giây sau mới tới lượt lại — xe khác (ít điểm) cũng có lượt
ON_AIR_NAMES = 3
OFFSCREEN_SKIP = {"via", "honk"}
RELIEF_AUTO = False
# Dừng đón dọc đường (PLAN-145, anh 03/11): xe tới điểm hẹn thì dừng hẳn bên lề, người chờ lên từng người (đọc tên), xong chạy
PICKUP_STOP_BASE = 3.5  # giây tấp vào / mở cửa (người chờ đứng 2 giây rồi mới bước lên)
PICKUP_STOP_STEP = 1.3  # giây mỗi người bước lên
PICKUP_JOIN = 0.4  # điểm đón sắp tới còn ≥ 40 % PICKUP_LEAD giây → người hẹn sau đứng chung điểm đó (xe dừng một lần)
# Chọn tuyến cho chuyến mới (PLAN-145): tuyến chở được nhiều người đang chờ nhất (cả người làn khác mà xe đi ngang quê); ai chờ
# quá LANE_MAX_WAIT giây thì tuyến của người đó được đi trước — đông mà không ai bị bỏ quên
LANE_MAX_WAIT = 600.0  # PLAN-144 (anh 03/11 «không cần xe tăng cường nữa, nhiều xe quá anh không cover được»)
PRIORITY_TALK_GAP = 8.0  # lơ xe báo «X tặng quà, lên đầu hàng» tối đa 8 giây / câu
# Quà = xe chạy nhanh (anh chọn 03/11 «tặng quà để xe trước đi nhanh hơn», mỗi xu cộng giây): mỗi xu thêm TURBO_PER_XU giây
# chạy gấp TURBO_MULT, cộng dồn tối đa TURBO_MAX giây; chỉ trừ lúc xe đang chạy — xe tới quê / về bến sớm, chuyến sau tới sớm
TURBO_PER_XU = 3.0
TURBO_MAX = 180.0
TURBO_MULT = 2.0
TURBO_SPEED_CAP = 4.0  # tim + xăng đầy + quà cùng lúc: không vượt x4 (cảnh trôi còn nhìn được)
TURBO_TALK_GAP = 10.0
# Trạm thu phí / công an (anh 03/11): xe bị chặn lại, người xem TẶNG QUÀ góp đủ xu thì xe đi tiếp — chỉ quà mới tính; chờ tới
# khi đủ. Phòng ít quà thì admin bấm «Anh Tư bù lỗ» trên /control (hoặc đặt tự bù lỗ sau N giây) cho xe qua.
# Tần suất (rà soát 03/11, giả lập theo số liệu buổi live thật): chuyến xa nhất ~8 phút; trước 350 km / trạm + 60 % công an
# = ~2,6 lần chặn / chuyến dài → phòng ít quà đứng chờ 34 phút / giờ. Giờ: chuyến 600–1199 km một trạm, từ 1200 km hai trạm,
# công an 40 % — chuyến dài trung bình ~2 lần, chuyến ngắn 0–1 lần.
TOLL_EVERY_KM = 600.0
TOLL_MAX = 2
TOLL_MIN_KM = 300.0  # chuyến ngắn hơn: không qua trạm
POLICE_CHANCE = 0.4  # chuyến từ POLICE_MIN_KM: khả năng bị công an kiểm tra một lần
POLICE_MIN_KM = 150.0
SPEEDING_FACTOR = 3  # công an gặp lúc xe đang chạy x2 nhờ quà → «quá tốc độ», phạt gấp 3 (tim không tính: CTA bảo thả tim)
# Phí tự theo phòng (số liệu thật 02/11: 20 phút, 46 người xem, 6 quà = 6 xu ≈ 0,3 xu / phút → phí 20 xu chờ ~1 giờ):
# phí = lượng xu phòng hay tặng trong BLOCK_TARGET_MIN phút (đo 10 phút gần nhất, mỗi quà tính tối đa GIFT_RATE_CAP xu cho
# một đại gia không đẩy phí cả phòng), ít nhất 1 xu, nhiều nhất bằng mức admin đặt
BLOCK_TARGET_MIN = 1.5
GIFT_RATE_WINDOW = 600.0
GIFT_RATE_CAP = 50
# Phòng ít quà thì ít bị chặn: giữ mỗi điểm chặn đã định với xác suất theo lượng quà (≥ BLOCK_FULL_RATE xu / phút: giữ hết),
# không dưới BLOCK_KEEP_MIN — phí đã xuống 1 xu mà phòng 0,3 quà / phút vẫn chờ ~3 phút mỗi lần
BLOCK_FULL_RATE = 1.0
# Mục tiêu buổi live (anh 03/11 «1 giờ phải kiếm được 100k»: ~1.000 xu ≈ 100.000 đ người live nhận): một thanh chung cả phòng,
# mỗi mốc mở một cảnh vui cho TẤT CẢ người xem (mục tiêu tập thể + tiến độ thấy được — kiểu «LIVE goal» quen thuộc trên
# TikTok); đủ thì cả xe chúc Tết rồi sang vòng mới. Không hứa gì riêng cho người tặng ngoài cảm ơn tên.
GOAL_STEPS = ((0.1, "lixi", "🧧 mưa lì xì cả màn hình"), (0.3, "lantern", "🏮 thả đèn lồng"),
              (0.6, "firework", "🎆 pháo hoa lớn"), (1.0, "party", "🎉 cả xe dừng lại chúc Tết"))
MONEY_WINDOW = 3600.0  # bảng doanh thu /control: quà trong 1 giờ gần nhất
# Đua tỉnh (anh 03/11 duyệt): bình luận + tim + quà cộng điểm cho tỉnh quê; mỗi chuyến một vòng — tỉnh nhiều điểm nhất mà có
# người đang chờ thì chuyến mới đi hướng tỉnh đó (sau luật «chờ quá 10 phút đi trước»). Trộn hành động miễn phí: không thành
# game «chấm điểm chỉ bằng quà» (TikTok hạn chế), người không tặng vẫn kéo được tỉnh mình lên.
RACE_PER_COMMENT = 1
RACE_COMMENT_GAP = 15.0  # mỗi người một điểm bình luận / 15 giây (không spam lấy điểm)
RACE_LIKES_PER_POINT = 20
RACE_PER_XU = 5
RACE_TALK_GAP = 30.0
# Bảng quảng cáo bên đường (anh 03/11): video anh tải lên; xe đang chạy dừng lại xem hết rồi chạy tiếp
SHOW_LEG_WINDOW = (0.15, 0.8)
FOCUS_SECONDS = 12.0  # /control bấm vào một khách: máy quay zoom vào cửa sổ giường người đó chừng này giây (anh 03/11)  # chỉ dừng giữa chặng (không sát điểm thả khách / trạm)
BLOCK_KEEP_MIN = 0.3
BLOCK_CLEAR_KM = 12.0  # điểm chặn không đặt sát điểm thả khách / trạm nghỉ
BLOCK_GAP_KM = 40.0
BLOCK_REMIND_GAP = 25.0  # đang bị chặn: lơ xe nhắc góp quà mỗi 25 giây
POLICE_REASONS = ("kiểm tra giấy tờ, sổ đăng kiểm để quên ở bến", "tài xế quên mang bằng lái", "đèn hậu bị cháy",
                  "chở hành lý cồng kềnh trên nóc xe", "chưa thắt dây an toàn cho khách")
RULES_GAP = 180.0  # lơ xe đọc luật chơi mỗi 3 phút (anh báo 02/11: người xem chưa hiểu luật)
RULES_MIN_GAP = 60.0  # có RULES_JOINS người mới vào phòng thì đọc sớm hơn, nhưng không dưới 1 phút
RULES_JOINS = 3  # câu nhỏ của xe chính: xe chính không lên màn hình thì lơ xe khỏi nói
MANUAL_HOLD = 120.0  # admin bấm «Chiếu» tay → tạm ngưng tự chuyển 2 phút

WISHES = (
    "Năm mới an khang, cả nhà sum vầy!",
    "Về tới nhà rồi, ôm mẹ một cái thật lâu nhé!",
    "Chúc Tết đủ đầy, tiền vào như nước!",
    "Năm Đinh Mùi vạn sự như ý!",
    "Bố mẹ khỏe mạnh, mình bình an là vui rồi.",
    "Chúc một cái Tết ấm áp, không ai hỏi lương!",
    "Mâm cơm ngày Tết đang chờ đó!",
    "Năm mới mọi điều hanh thông!",
    "Một năm vất vả rồi, Tết này nghỉ ngơi thật đã nhé.",
    "Chúc sức khỏe, bình an và nhiều niềm vui!",
)

STAY_MESSAGES = (
    "Năm nay chưa về được thì gọi về nhà một cuộc nhé, {name}.",
    "Ở lại phòng trọ cũng có tụi mình ở đây với {name}.",
    "Tết này {name} chưa về, nhưng nhà vẫn luôn chờ.",
    "Cố lên {name}, năm sau mình về sớm hơn nha.",
)

GIFT_TIERS = ((1000, 4), (100, 3), (10, 2), (1, 1))
# (có vé, chưa có vé) — chỉ hứa đúng cái sẽ thấy trên màn hình
GIFT_LABELS = {
    1: ("⭐ giường vàng + tên viền vàng trên xe", "⭐ giường vàng khi lên xe — gõ tên tỉnh quê"),
    2: ("pháo hoa ngay + khi về tới quê", "pháo hoa mừng"),
    3: ("băng rôn «Xe Tết của bạn»", "băng rôn «Xe Tết của bạn»"),
    4: ("cả xe dừng lại chúc Tết", "cả xe dừng lại chúc Tết"),
}


# Mỗi món quà một hiệu ứng (PLAN-142, anh chọn 02/11). TikTok gửi tên món (thường tiếng Anh, có khi tiếng Việt) kèm giá xu: khớp
# tên trước, không khớp thì theo giá một món. Hiệu ứng chỉ là hình / tiếng trên màn hình — mốc xu cũ (VIP, pháo hoa, băng rôn,
# xe tăng cường, chúc Tết) giữ nguyên.
GIFT_FX_NAMES = (
    (("rose", "hoa hong", "flower", "bong hoa"), "petals"),
    (("tiktok",), "honk"),
    (("heart", "hearts", "tim", "love"), "hearts"),
    (("lantern", "den long"), "lantern"),
    (("li xi", "red envelope", "envelope", "money", "lucky"), "lixi"),
    (("firework", "fireworks", "phao hoa", "confetti"), "firework"),
)
GIFT_FX_RANK = ("petals", "honk", "hearts", "firework", "lixi", "lantern")  # nhỏ → lớn
GIFT_FX_PRICE = ((1, "petals"), (9, "hearts"), (29, "firework"), (99, "lixi"))  # (giá một món ≤, hiệu ứng); trên nữa: lantern
GIFT_FX_LABELS = {  # bảng quà trên màn hình (hud.ts dùng cùng thứ tự)
    "petals": "🌹 Hoa hồng → hoa mai / đào rơi", "honk": "🎵 TikTok → xe bóp còi", "hearts": "💗 Tim → tim bay",
    "firework": "🎆 10–29 xu → pháo hoa", "lixi": "🧧 30–99 xu → lì xì bay", "lantern": "🏮 Từ 100 xu → đèn lồng thả trời",
}


def gift_fx(gift: str, diamonds: int) -> tuple[str, int]:
    """(hiệu ứng, số món) của một lượt tặng: «Rose ×5», 5 xu → ("petals", 5)."""
    name, _, times = gift.partition(" ×")
    count = max(1, as_int(times)) if times else 1
    unit = diamonds / count
    by_price = next((fx for top, fx in GIFT_FX_PRICE if unit <= top), "lantern")
    words = f" {normalize(name)} "
    by_name = next((fx for keys, fx in GIFT_FX_NAMES if any(f" {k} " in words for k in keys)), by_price)
    return max(by_name, by_price, key=GIFT_FX_RANK.index), count  # món đắt mà tên «nhỏ» (Hand Hearts 100 xu) vẫn hiệu ứng lớn


def as_int(value, default: int = 1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def hue_of(uid: str) -> int:
    return int(hashlib.md5(uid.encode()).hexdigest()[:4], 16) % 360


def pick(options: tuple[str, ...], seed: str) -> str:
    return options[int(hashlib.md5(seed.encode()).hexdigest()[:6], 16) % len(options)]


class Refused(ValueError):
    """Admin yêu cầu việc luật chơi không cho lúc này — lời báo viết sẵn để hiện nguyên văn cho admin."""


@dataclass
class Viewer:
    uid: str
    name: str
    hue: int
    province: str | None = None
    stay: bool = False
    vip: bool = False
    fireworks: bool = False
    likes_trip: int = 0
    race_at: float = -1e9  # lần cuối bình luận được điểm đua tỉnh
    race_likes: int = 0  # tim lẻ chưa đủ một điểm đua tỉnh
    trips: int = 0
    followed: bool = False
    switched: bool = False
    last_chat: float = -1e9
    last_rest: float = -1e9
    last_where: float = -1e9
    last_ask: float = -1e9
    last_care: float = -1e9
    home_now: bool = False  # buổi này vừa được thả về quê (đặt vé tiếp → lơ xe trêu «mới về đã quay ra bến»)
    parcels: int = 0  # thùng quà Tết đi theo vé (PLAN-134 C): tặng quà lúc có vé → lên gầm xe, tới quê ôm vào cổng
    # hồ sơ nhớ qua các buổi live (PLAN-134 D, store.py): quê đã về, tổng tim / xu / comment, ngày đầu / cuối gặp, số ngày ghé
    home: str | None = None
    likes: int = 0
    gifts: int = 0
    comments: int = 0
    first_day: str = ""
    last_day: str = ""
    days: int = 0
    returning: bool = False  # đã gặp ở buổi live trước → lơ xe chào lại (một lần mỗi buổi)
    gift_trip: int = 0  # xu cộng dồn trong chuyến này → tính bậc quà
    last_seen: float = 0.0  # lần cuối có bất kỳ tương tác nào (TikTok không báo ai rời phòng)
    last_share: float = -1e9
    last_notice: float = -1e9
    invited: bool = False  # buổi này lơ xe đã mời lên xe (thả tim nhiều mà chưa có vé)
    stage: float = 0.0  # điểm lên sóng trong buổi (quà / bình luận / tim) — xe tăng cường của người này được chiếu lâu hơn
    stage_comments: int = 0
    gift_session: int = 0  # xu tặng trong buổi (bảng «Chủ nhà xe»)
    prio_credit: bool = False  # tặng quà lúc chưa có vé → lần giữ chỗ kế tiếp được lên đầu hàng (một lần)
    avatar: str = ""  # ảnh đại diện TikTok (https)
    full: float = 100.0  # % no bụng lúc đang trên xe (anh 03/11: «% cơ thể … sắp đói»)
    hungry_told: bool = False
    snack: str | None = None  # món mua của cô bán hàng chuyến này (nem / bì / bánh mì) — hiện cạnh tên trên xe
    roll_missed: int = 0  # số lần lỡ điểm danh liên tiếp (có tương tác lại thì về 0)
    roll_skip: int = -1  # lỡ điểm danh ở chuyến số này → chuyến đó không xếp giường nữa (lùi xuống chuyến sau)
    last_chatter: float = -1e9  # lần cuối được AI đáp chuyện phiếm
    quiz_score: int = 0  # số câu đố trả lời đúng trong buổi
    priority: bool = False  # đang chờ chuyến sau đã tặng quà → đã được lên đầu hàng (một lần tới khi lên xe — PLAN-144)


@dataclass
class Bus:
    no: int
    lane: str = ""
    seats: list[str | None] = field(default_factory=lambda: [None] * SEATS)
    banner: str | None = None

    def riders(self) -> list[str]:
        return [uid for uid in self.seats if uid]

    def free_seat(self) -> int | None:
        return next((i for i, uid in enumerate(self.seats) if uid is None), None)

    def seat_of(self, uid: str) -> int | None:
        return next((i for i, s in enumerate(self.seats) if s == uid), None)


@dataclass
class Relief:
    """Xe tăng cường chạy ngầm: không trạm nghỉ, không cảnh chúc Tết, km xe chạy = thời gian × tốc độ nén."""
    no: int
    lane: str
    riders: list[str]
    sponsor: str | None  # người tặng quà gọi xe (None: xe tự động)
    trip: Trip
    kmps: float
    clock0: datetime  # giờ VN lúc xuất bến (đồng hồ trên xe)
    odo: float = 0.0  # km xe đã chạy
    done: int = 0  # số điểm đã thả khách
    dropped_at: float | None = None  # lúc vừa thả khách (tự chiếu: ở lại xem thêm chút)
    shown_at: float = -1e9  # lần cuối lên sóng theo điểm
    place_now: str | None = None  # tỉnh xe đang qua (đang chiếu thì lơ xe gọi bà con tỉnh đó)


@dataclass
class Leg:
    kind: str  # rest | stop
    target: str  # tỉnh: điểm thả khách (stop) hoặc tỉnh có trạm dừng chân (rest)
    km: float  # km xe chạy (odometer) từ bến đi tới cuối chặng


class Engine:
    def __init__(self, now: float = 0.0, today: date | None = None,
                 board_seconds: float = BOARD_SECONDS, rest_seconds: float = REST_SECONDS,
                 network: Network | None = None):
        self.today = today
        self.network = network or Network.load()
        self.board_seconds = board_seconds
        self.rest_seconds = rest_seconds
        self.paused = False
        self.rng = random.Random()  # bốc câu lơ xe (test truyền hạt giống cố định nếu cần)
        self.viewers: dict[str, Viewer] = {}
        self.avatars: dict[str, str] = {}  # tên hiện → ảnh đại diện TikTok
        self.outbox: list[dict] = []
        self.queues: dict[str, list[str]] = {ln.key: [] for ln in self.network.lanes}  # vé chờ theo làn
        self.queued_at: dict[str, float] = {}  # giờ bắt đầu chờ của từng vé (giữ nguyên khi đổi tỉnh cùng làn)
        self.staying: list[str] = []
        self.board: Counter[str] = Counter()  # vé theo tỉnh trong phiên
        self.trip_likes = 0
        self.trip_gifted = False  # chuyến này đã có người mở hàng tặng quà chưa
        self.boost = 0.0
        self.turbo = 0.0  # giây xe còn chạy gấp đôi nhờ quà
        self.turbo_by = ""  # người tặng gần nhất
        self.last_turbo_talk = -1e9
        self.block: dict | None = None  # xe đang bị chặn: trạm thu phí / công an (chờ góp quà)
        self.block_plan: list[tuple[float, str]] = []  # (km, "toll" | "police") của chuyến này
        self.blocks_on = False  # server bật theo cài đặt (mặc định bật); engine trần (test) không chặn xe
        self.toll_xu = 20
        self.fine_xu = 10
        self.cover_seconds = 0.0  # 0: chờ tới khi góp đủ (admin bấm bù lỗ); > 0: tự bù lỗ sau chừng này giây
        self.block_rng = random.Random()
        self.incidents_on = False  # server bật theo cài đặt; engine trần (test) không gặp sự cố
        self.incident_xu = INCIDENT_XU
        self.quiz_on = False  # server bật theo cài đặt
        self.quiz_gap = QUIZ_GAP
        self.quiz: dict | None = None  # câu đố đang hỏi / vừa có đáp án
        self.next_quiz = now + QUIZ_GAP
        self.quiz_recent: list[str] = []
        self.last_fact = -1e9
        self.weather = "clear"  # clear | drizzle | rain | fog — overlay vẽ mưa / sương, lơ xe báo khi đổi
        self.weather_region: str | None = None
        self.last_weather_talk = -1e9
        self.ads: list[dict] = []  # quảng cáo bot của anh: lơ xe đọc câu «say» lần lượt (server đặt theo cài đặt)
        self.ad_gap = 8 * 60.0
        self.next_ad = now + 120.0  # mở game: đọc quảng cáo đầu tiên sau 2 phút
        self.ad_index = 0
        self.chatter: list[dict] = []  # chuyện phiếm chờ AI đáp (khi bật AI)
        self.last_chatter = -1e9
        self.last_block_remind = -1e9
        self.goal_xu = 1000  # mục tiêu buổi (xu), admin đặt
        self.goal_have = 0  # xu đã góp vào vòng mục tiêu hiện tại
        self.goal_round = 0
        self.money_log: list[tuple[float, int, str]] = []  # (giờ, xu, tên) quà trong MONEY_WINDOW giây
        self.started_at = now
        self.focus: dict | None = None  # {uid, until}: máy quay đang zoom vào khách này
        self.race_on = False  # anh 03/11: tắt đua tỉnh — ai đặt trước lên trước, chỉ quà được ưu tiên
        self.next_lane: str | None = None  # anh chọn hướng cho chuyến kế tiếp trên /control
        self.ticket_idle = TICKET_IDLE
        self.roll_on = True  # anh bật / tắt điểm danh trên /control
        self.roll_idle = ROLL_IDLE
        self.roll_wait = ROLL_WAIT
        self.rollcalls: dict[str, float] = {}
        self.vendor_on = False  # server bật theo cài đặt (vendor_on); test cũ về tốc độ không bị cô bán hàng chen vào
        self.vendor_xu = VENDOR_XU
        self.vendor: dict | None = None  # cô bán hàng đang lên xe ({stage: stop|sell, until, sold, treats})
        self.vendor_pool: dict = {"paid": 0, "givers": {}}  # quà góp gọi cô bán hàng (chuyến này)
        self.vendor_done = False  # chuyến này cô đã lên rồi
        self.last_vendor_remind = -1e9
        self.hungry_new: list[str] = []  # người vừa «sắp đói», chờ lơ xe gom tên nhắc
        self.last_hunger_talk = -1e9
        self.names_pending = False  # app báo: giọng đọc còn tên người lên xe chưa đọc xong
        self.name_hold_from: float | None = None  # uid đang được gọi tên → hết giờ chờ lúc này
        self.race: Counter = Counter()  # điểm đua tỉnh vòng này (theo mã tỉnh)
        self.race_leader: str | None = None
        self.race_winner: str | None = None
        self.last_race_talk = -1e9
        self.videos: list[dict] = []  # video bảng quảng cáo (server cập nhật từ thư mục)
        self.show: dict | None = None  # đang dừng xem video
        self.shows_on = False  # server bật theo cài đặt; engine trần (test) không tự chiếu
        self.show_every = 600.0
        self.show_max = 120.0
        self.show_index = 0
        self.show_pending: str | None = None  # anh bấm «Chiếu» lúc xe trong hầm: chiếu khi ra chỗ thoáng ("" = video kế tiếp)
        self.next_show = now + self.show_every
        self.fee_auto = True  # phí trạm / phạt tự theo lượng quà của phòng (tối đa toll_xu / fine_xu)
        self.gift_log: list[tuple[float, int]] = []  # (giờ, xu) quà trong GIFT_RATE_WINDOW giây gần nhất
        self.seated_at: list[float] = []  # giờ từng người có giường ở bến (giữ xe đủ lâu để đọc tên)
        self.bus_counter = 0
        self.trip: Trip | None = None
        self.reliefs: list[Relief] = []
        self.relief_auto = True  # admin tắt được: chỉ gọi xe tăng cường bằng tay / bằng quà
        self.featured: int | None = None  # xe tăng cường đang lên màn hình (None: xe chính)
        self.show_until: float | None = None  # xe tăng cường đang lên sóng theo điểm tới lúc này thì về xe chính
        self.trip_minutes = TRIP_MINUTES  # chuyến dài nhất chạy đường bao nhiêu phút (admin chỉnh)
        self.talk_style = "mix"  # kiểu nói của lơ xe (talk.TALK_STYLES, admin chọn)
        self.clock0: datetime | None = None  # giờ VN lúc xe chính xuất bến
        self.featured_since = now
        self.manual_until = -1e9
        # nhạc trong xe (PLAN-127): mỗi xe một đài — "main" cho xe chính, số xe cho xe tăng cường; index → music_tracks
        self.music: dict[str, dict] = {}
        self.legs: list[Leg] = []
        self.leg_index = 0
        self.progress = 0.0
        self.leg_seconds = LEG_SECONDS_MIN
        self.rest_orders: Counter[str] = Counter()
        self.wc_line: list[str] = []
        self.honked = False
        self.recall: Callable[[str], dict | None] | None = None  # hồ sơ khách buổi trước (Hub gắn store.load)
        self.dirty: set[str] = set()  # người xem có hồ sơ đổi, chờ ghi
        self.last_welcome = -1e9
        self.last_same_home = -1e9
        self.last_invite = -1e9
        self.fuel = 1.0  # bình xăng 0 → 1 (PLAN-137)
        self.dirt = 0.0  # độ bẩn 0 (sạch) → 1
        self.trip_bonus = 1.0  # thưởng tốc độ chuyến này theo xăng / độ sạch lúc xuất bến
        self.last_care_talk = -1e9
        self._snap_no = 0  # đếm snapshot: bảng chặng xe chính dựng một lần mỗi snapshot
        self._route_memo: tuple[int, dict] | None = None
        self.last_answer = -1e9
        self.other_dirs: list[str] = []  # tỉnh khác hướng vừa đặt vé (giữ chỗ xe sau) — lơ xe nhắc gộp
        self.last_other_talk = -1e9
        self.last_lock_talk = -1e9
        self.station_votes: dict[str, tuple[str, float]] = {}  # uid → (bến được gọi, lúc gọi)
        self.last_station_talk = -1e9
        self.last_back_talk = -1e9
        self.pickups: dict[str, tuple[str, float]] = {}  # uid → (tỉnh có điểm đón, odometer điểm đón) chờ xe tới
        self.halt: dict | None = None  # xe đang dừng bên đường đón khách: nơi, người lên, lúc chạy lại (PLAN-145)
        self.last_pickup_talk = -1e9
        self.ai_reply = False  # admin bật «lơ xe trả lời bằng AI» (Hub đặt theo thiết lập)
        self.questions: list[dict] = []  # câu hỏi chờ AI trả lời (Hub lấy qua next_question)
        self.place_now: str | None = None  # tỉnh xe chính đang đi qua (đổi tỉnh mới gọi bà con tỉnh đó)
        self.place_shown: str | None = None  # tên tỉnh đang ghi trên màn (đã giữ PLACE_HOLD_KM)
        self.place_cand: tuple[str, float] | None = None  # tỉnh mới đang chờ đủ km
        self.last_via_talk = -1e9
        self.last_priority_talk = -1e9
        self.patrons: list[str] = []  # uid «Chủ nhà xe», «Phó nhà xe» (xu tặng trong buổi)
        self.last_rules = now  # mới mở game: để cảnh đầu tiên chạy, đọc luật sau RULES_MIN_GAP nếu có người vào
        self.joins_since_rules = 0
        self.specials: list[str] = []
        self.resume: tuple[str, float] = ("DRIVING", 0.0)  # pha + giây còn lại để quay về sau SPECIAL
        self.next_banner: str | None = None  # quà băng rôn lúc hết chuyến → dán cho xe sau
        self.boarding_started: float | None = None
        self.trip_started: float | None = None
        self.board_avg = min(board_seconds, BOARD_AVG_START)
        self.run_avg = RUN_AVG_START
        self.treated: set[str] = set()
        self.delivered = 0
        self.delivered_km = 0
        self.home_counted: set[str] = set()
        self.phase = ""
        self.phase_started = now
        self.phase_until = now
        self.last_now = now
        self.bus = Bus(0)
        self._enter_boarding(now)

    # ---- tiện ích -------------------------------------------------------

    def emit(self, type_: str, **data) -> None:
        if "avatar" not in data and (url := self.avatars.get(data.get("name") or "")):
            data["avatar"] = url  # ảnh đại diện TikTok cạnh tên trên thẻ / thông báo (anh 03/11)
        self.outbox.append({"type": type_, **data})

    def talk(self, kind: str, speak: bool = True, main: bool = False, **fields) -> None:
        """Anh Tư lơ xe nói một câu loại `kind` (bảng câu đời thường trong talk.py). `main`: câu về chỗ / cảnh của xe chính —
        màn hình đang chiếu xe tăng cường thì câu nhỏ (qua tỉnh, bóp còi) bỏ, câu khác ghi rõ «Xe số N.» (anh báo 02/11: chiếu
        xe khác mà lơ xe vẫn đọc chỗ khác)."""
        text = line(kind, self.rng, self.talk_style, **fields)
        if main and self.featured is not None:
            if kind in OFFSCREEN_SKIP:
                return
            text = f"Chuyến {self.bus.no}. {text}"
        self.loxe(text, speak)

    def _dest(self, lane: str) -> str:
        return BY_KEY[self.network.lane_by_key[lane].to].name

    def loxe(self, text: str, speak: bool = True) -> None:
        """Bong bóng lơ xe; speak=False khi giọng đọc đã có câu riêng đầy đủ hơn (thả khách đọc cả tên)."""
        self.emit("loxe", text=text, speak=speak)

    def drain(self) -> list[dict]:
        out, self.outbox = self.outbox, []
        return out

    def viewer(self, uid: str, name: str) -> Viewer:
        name = clean_name(name) if name else name
        v = self.viewers.get(uid)
        if v is None:
            v = self.viewers[uid] = Viewer(uid, name or uid, hue_of(uid))
            row = self.recall(uid) if self.recall else None
            if row:  # khách đã gặp ở buổi trước (PLAN-134 D)
                v.home, v.trips, v.likes, v.gifts, v.comments = row["home"], row["trips"], row["likes"], row["gifts"], row["comments"]
                v.first_day, v.last_day, v.days = row["first_day"], row["last_day"], row["days"]
                v.returning = v.last_day < self._today().isoformat()
        elif name:
            v.name = name
        return v

    def _question(self, v: Viewer, text: str, now: float) -> None:
        """Câu hỏi trong comment (PLAN-135): câu hay gặp → lơ xe trả lời sẵn (gọi tên người hỏi); câu khác → xếp hàng cho AI
        nếu admin bật. Giãn cách: cả phòng ASK_GAP giây / câu trả lời sẵn, mỗi người ASK_PER_VIEWER giây / câu hỏi."""
        if now - v.last_ask < ASK_PER_VIEWER or not allow_chat(text):
            return
        key = faq(text)
        if key:
            if now - self.last_answer < ASK_GAP:
                return
            v.last_ask = self.last_answer = now
            self.loxe(self._faq_answer(key, v))
        elif self.ai_reply:
            v.last_ask = now
            self.questions = [*self.questions, {"uid": v.uid, "name": v.name, "text": text.strip()[:200], "at": now}][
                -QUESTIONS_KEEP:]

    def next_question(self, now: float, max_age: float) -> dict | None:
        """Câu hỏi cũ nhất còn mới (chờ quá `max_age` giây thì bỏ: trả lời lạc nhịp còn tệ hơn không trả lời)."""
        self.questions = [q for q in self.questions if now - q["at"] <= max_age]
        if self.questions:
            return self.questions.pop(0)
        self.chatter = [c for c in self.chatter if now - c["at"] <= max_age]
        if self.chatter and now - self.last_chatter >= CHATTER_GAP:  # không ai hỏi: đáp một câu chuyện phiếm mới nhất
            c = self.chatter.pop()
            self.last_chatter = now
            if c["uid"] in self.viewers:
                self.viewers[c["uid"]].last_chatter = now
            return c
        return None

    def _faq_answer(self, key: str, v: Viewer) -> str:
        """Câu trả lời sẵn theo tình hình thật lúc này (giọng lơ xe: không «!», không «nha»)."""
        name = v.name
        if key == "via":
            return f"{name} ơi, xe đón dọc đường đó, quê còn ở phía trước thì gõ tên tỉnh, ra điểm đón chờ Anh Tư tấp vô rước."
        if key == "how":
            return (f"{name} gõ tên tỉnh quê mình là có giường, thả tim cho xe chạy nhanh hơn, gõ xe nào để coi vé, "
                    "hổng về thì gõ không về.")
        if key == "gift":
            return (f"{name} hỏi quà hả, nhà xe chỉ có một xe 24 giường thôi, mỗi xu xe chạy nhanh gấp đôi thêm ba giây cho "
                    "chuyến sau tới sớm, tặng một xu là lên đầu hàng chuyến sau, có "
                    "giường thì giường vàng, mười xu pháo hoa, trăm xu băng rôn tên mình trên xe, ngàn xu cả xe dừng chúc "
                    "Tết, ai tặng nhiều nhất làm chủ nhà xe, chỉ người từ 18 tuổi tặng.")
        if key == "station":
            return f"{name} muốn xe ra bến khác thì gõ từ Hà Nội hay bến Đà Nẵng, đủ {STATION_VOTES} người gọi là xe ra."
        if key == "newname":
            return f"Tên tỉnh cũ hay mới đều được {name} ơi, quê sáp nhập thì gõ tên tỉnh cũ cho Anh Tư ghé đúng cổng."
        phase = self._phase_now()  # «depart»: khi nào xe chạy
        if phase == "BOARDING":
            left = max(0, round(self.phase_until - self.last_now))
            when = f"{left // 60} phút {left % 60} giây" if left >= 60 else f"{left} giây"
            return f"{name} ơi, chuyến {self.bus.no} xuất bến sau {when}, ai chưa lên gõ tên tỉnh lẹ."
        if phase == "REST":
            return f"Xe đang nghỉ trạm {name} ơi, chút xíu là chạy tiếp."
        if phase == "DROPOFF":
            return f"Đang thả khách {name} ơi, xong là chạy tiếp liền."
        if phase == "FINISH":
            return f"Xe về bến rồi {name} ơi, chuyến sau sắp đón, gõ tên tỉnh trước đi."
        return f"Chuyến {self.bus.no} đang chạy rồi {name} ơi, gõ tên tỉnh là giữ chỗ chuyến sau."

    def ai_context(self, uid: str) -> dict:
        """Tình hình thật cho AI trả lời đúng (không bịa): pha, xe, điểm kế, vé của người hỏi, mùa."""
        snap_leg = self.current_leg()
        nxt = (f"Trạm {BY_KEY[snap_leg.target].name}" if snap_leg.kind == "rest" else BY_KEY[snap_leg.target].name) if snap_leg else None
        return {"phase": self._phase_now(), "bus_no": self.bus.no, "lane": self.network.lane_by_key[self.bus.lane].label,
                "departure": self.network.departure.name, "riders": len(self.bus.riders()), "next": nxt,
                "waiting": self.waiting(), "days_to_tet": max(0, (season.TET_DAY - self._today()).days),
                "ticket": self.ticket_of(self.viewers[uid]) if uid in self.viewers else {"status": "none"}}

    def _same_home(self, v: Viewer) -> None:
        """Lên xe mà trên xe đã có người cùng tỉnh: lơ xe ghép đôi (PLAN-134 D — người xem thích được nhận ra, có «hội
        đồng hương»). Mỗi SAME_HOME_GAP giây tối đa một lần."""
        if self.last_now - self.last_same_home < SAME_HOME_GAP:
            return
        mate = next((self.viewers[u] for u in self.bus.riders() if u != v.uid and self.viewers[u].province == v.province), None)
        if mate is not None:
            self.last_same_home = self.last_now
            self.talk("same_home", name=v.name, other=mate.name, prov=BY_KEY[v.province].name)

    def take_dirty(self) -> list[dict]:
        """Hồ sơ người xem đã đổi từ lần lấy trước (Hub ghi SQLite theo lô)."""
        rows = [{"uid": v.uid, "name": v.name, "home": v.home, "trips": v.trips, "likes": v.likes, "gifts": v.gifts,
                 "comments": v.comments, "first_day": v.first_day, "last_day": v.last_day, "days": v.days}
                for uid in self.dirty if (v := self.viewers.get(uid))]
        self.dirty = set()
        return rows

    def _seen_today(self, v: Viewer, now: float) -> None:
        """Có tương tác thật (không tính vào phòng): ghi ngày ghé; khách buổi trước thì lơ xe chào lại (PLAN-134 D)."""
        today = self._today().isoformat()
        if v.last_day != today:
            v.first_day = v.first_day or today
            v.last_day = today
            v.days += 1
        self.dirty.add(v.uid)
        if v.returning and now - self.last_welcome >= WELCOME_GAP:
            v.returning = False
            self.last_welcome = now
            home = BY_KEY[v.home].name if v.home in BY_KEY else None
            self.emit("welcome", name=v.name, hue=v.hue, trips=v.trips, home=home, days=v.days)
            if v.trips and home:
                self.talk("welcome_trips", name=v.name, prov=home, n=v.trips)
            else:
                self.talk("welcome_back", name=v.name)

    def _set_phase(self, phase: str, now: float, seconds: float) -> None:
        self.phase = phase
        self.phase_started = now
        self.phase_until = now + seconds

    def current_leg(self) -> Leg | None:
        return self.legs[self.leg_index] if 0 <= self.leg_index < len(self.legs) else None

    def _today(self) -> date:
        return self.today or datetime.now(VN).date()

    def boarding_open(self) -> bool:
        """Đang đón khách (kể cả lúc chen cảnh chúc Tết giữa giờ đón)."""
        return self.phase == "BOARDING" or (self.phase == "SPECIAL" and self.resume[0] == "BOARDING")

    def on_trip(self, uid: str) -> bool:
        """Đang trên xe chạy (xe chính đã xuất bến, hoặc xe tăng cường): không đổi tỉnh / bỏ vé được nữa."""
        return ((not self.boarding_open() and self.bus.seat_of(uid) is not None)
                or any(uid in r.riders for r in self.reliefs))

    def lane_of_uid(self, uid: str) -> str | None:
        """Làn đang giữ chỗ (hàng chờ), None nếu không chờ."""
        return next((lane for lane, q in self.queues.items() if uid in q), None)

    def _unqueue(self, uid: str) -> None:
        for q in self.queues.values():
            if uid in q:
                q.remove(uid)
        self.queued_at.pop(uid, None)
        self.rollcalls.pop(uid, None)
        if uid in self.viewers:
            self.viewers[uid].priority = False

    def _update_patrons(self) -> None:
        """«👑 Chủ nhà xe» / «Phó nhà xe»: hai người tặng nhiều xu nhất buổi; đổi chủ thì lơ xe báo (anh chọn 03/11)."""
        top = sorted((v for v in self.viewers.values() if v.gift_session > 0), key=lambda v: -v.gift_session)[:2]
        uids = [v.uid for v in top]
        if uids and (not self.patrons or self.patrons[0] != uids[0]):
            owner = self.viewers[uids[0]]
            self.emit("patron", name=owner.name, hue=owner.hue, xu=owner.gift_session)
            self.talk("new_owner", name=owner.name, xu=owner.gift_session)
        self.patrons = uids

    def _prioritize(self, v: Viewer, lane: str) -> int:
        """Người đang chờ tặng quà (PLAN-144, anh chọn «quà giúp chính mình»): lên đầu hàng làn mình, sau những người tặng
        trước; cũng được ưu tiên khi xe làn khác chạy ngang quê. Trả thứ tự mới (1 = đầu hàng)."""
        q = self.queues[lane]
        q.remove(v.uid)
        at = 0
        while at < len(q) and self.viewers[q[at]].priority:
            at += 1
        q.insert(at, v.uid)
        v.priority = True
        self.queued_at[v.uid] = min(self.queued_at.values(), default=0.0) - 1.0
        return at + 1

    def _release(self, v: Viewer) -> None:
        """Bỏ vé hiện có (giường hoặc chỗ chờ): giường trống thì kéo người chờ cùng làn lên ngay."""
        seat = self.bus.seat_of(v.uid)
        if seat is not None:
            self.bus.seats[seat] = None
            self._fill_from_queue()
        self._unqueue(v.uid)
        if v.province:
            self.board[v.province] -= 1
            v.province = None

    def _queue_special(self, name: str) -> None:
        if len(self.specials) < SPECIALS_QUEUE_MAX:
            self.specials.append(name)

    def _prune_queues(self) -> None:
        """Vé ma (người chờ đã rời phòng quá lâu) không được tính vào chọn làn / cao điểm / số chờ."""
        for queue in self.queues.values():
            for uid in [u for u in queue if self._ghost(u)]:
                self._release(self.viewers[uid])
        if self.next_lane and not self.queues.get(self.next_lane):  # làn anh chọn đã hết người chờ: bỏ chọn, về thứ tự đặt vé
            self.next_lane = None

    def _ghost(self, uid: str) -> bool:
        """Vé ma: chỉ khi anh bật giới hạn im lặng (ticket_idle > 0) — TikTok không báo ai rời phòng, im lặng vẫn là đang xem."""
        return self.ticket_idle > 0 and self.last_now - self.viewers[uid].last_seen > self.ticket_idle

    def waiting(self) -> int:
        return sum(len(q) for q in self.queues.values())

    def _phase_now(self) -> str:
        """Pha thật của chuyến (đang chen cảnh chúc Tết thì là pha sẽ quay về)."""
        return self.resume[0] if self.phase == "SPECIAL" else self.phase

    # ---- chuyển pha -----------------------------------------------------

    def _enter_boarding(self, now: float) -> None:
        if self.trip_started is not None:  # đo một chuyến thật (xuất bến → về bến) → ước giờ chờ trên vé
            self.run_avg += AVG_WEIGHT * (now - self.trip_started - self.run_avg)
            self.trip_started = None
        self.boarding_started = now
        self.seated_at = []
        self.bus_counter += 1
        self.race_winner = None
        self.bus = Bus(self.bus_counter, lane=self._pick_lane(), banner=self.next_banner)
        if self.race_winner:  # vòng đua tỉnh này có tỉnh thắng: báo rồi sang vòng mới
            win = BY_KEY[self.race_winner].name
            self.emit("race_win", province=win, points=self.race[self.race_winner])
            self.talk("race_win", prov=win, main=True)
        self.race.clear()
        self.race_leader = None
        self.next_banner = None
        self.trip, self.legs, self.leg_index, self.progress = None, [], 0, 0.0
        self.pickups = {}
        self.halt = None
        self.block = None
        self.block_plan = []
        self.trip_likes = 0
        self.trip_gifted = False
        for v in self.viewers.values():
            v.likes_trip = 0
            v.snack = None
            v.full = 100.0
            v.hungry_told = False
            v.gift_trip = 0
            v.switched = False
        self.name_hold_from = None
        self.vendor = None
        self.vendor_done = False
        self.vendor_pool = {"paid": 0, "givers": {}}
        self._set_phase("BOARDING", now, 0.0)
        self._fill_from_queue()  # sau khi vào pha đón: người im lặng lâu được điểm danh trước khi xếp giường
        self.phase_until = now + self._board_time()  # giờ đón theo số giường còn trống sau khi xếp
        today = self._today()  # câu mời lên xe theo mùa: cao điểm 23–28 Chạp, giao thừa, ngày Tết (PLAN-134 C)
        kind = {season.PEAK: "boarding_peak", season.EVE: "boarding_eve", season.TET: "boarding_tet"}.get(
            season.phase(today), "boarding")
        self.talk(kind, dest=self._dest(self.bus.lane), lunar=season.lunar_label(today) or "", main=True)

    def _board_time(self) -> float:
        """Giờ đón tỉ lệ số giường còn trống: xe đã kín người chờ lên sẵn thì không bắt cả bến đợi đủ 3 phút."""
        free = SEATS - len(self.bus.riders())
        hold = self._full_hold()
        return hold + (max(self.board_seconds, hold) - hold) * free / SEATS

    def _full_hold(self) -> float:
        """Đủ giường thì chạy sau chừng này giây: ít nhất FULL_BUS_SECONDS, đủ cho lơ xe đọc tên người vừa lên."""
        recent = sum(1 for t in self.seated_at if t >= self.last_now - NAME_WINDOW_S)
        return max(FULL_BUS_SECONDS, min(FULL_HOLD_MAX, NAME_LEAD_S + recent * NAME_READ_S))

    def _pick_lane(self, consume: bool = True) -> str:
        """Tuyến của chuyến mới (PLAN-145): ai chờ quá LANE_MAX_WAIT giây thì tuyến của người chờ lâu nhất đi trước (không ai bị
        bỏ đói); còn lại chọn tuyến chở được nhiều người đang chờ nhất — tính cả người làn khác mà xe đi ngang quê họ."""
        self._prune_queues()
        waiting = [lane for lane, q in self.queues.items() if q]
        if not waiting:
            return self.bus.lane or self.network.lanes[0].key
        if self.next_lane in waiting:  # anh chọn trên /control: chuyến này chạy hướng đó
            lane = self.next_lane
            if consume:  # xem trước (bảng «chuyến sau» trên màn hình) thì giữ lựa chọn
                self.next_lane = None
            return lane
        if not self.race_on:  # anh 03/11: ai đặt trước lên trước, chỉ người tặng quà được ưu tiên
            return self._fifo_order()[0]
        oldest = min(waiting, key=lambda lane: self.queued_at.get(self.queues[lane][0], self.last_now))
        if self.last_now - self.queued_at.get(self.queues[oldest][0], self.last_now) > LANE_MAX_WAIT:
            return oldest
        people = [self.viewers[u].province for q in self.queues.values() for u in q]

        def load(lane: str) -> int:
            served = self.network.serves(lane)
            return sum(1 for prov in people if prov in served)
        # đua tỉnh: tỉnh nhiều điểm nhất (có người đang chờ) quyết hướng chuyến này
        contenders = [(pts, key) for key, pts in self.race.items() if pts > 0 and key in people]
        for _, key in sorted(contenders, reverse=True):
            lanes = [lane for lane in waiting if key in self.network.serves(lane)]
            if lanes:
                self.race_winner = key
                return max(lanes, key=lambda lane: (min(load(lane), SEATS), lane == oldest))
        return max(waiting, key=lambda lane: (min(load(lane), SEATS), lane == oldest))

    def _fifo_order(self) -> list[str]:
        """Thứ tự các hướng chạy tiếp theo: hướng của người tặng quà đang chờ trước, rồi người đặt vé sớm nhất (anh 03/11)."""
        first: dict[str, tuple] = {}
        for lane, q in self.queues.items():
            for u in q:
                key = (not self.viewers[u].priority, self.queued_at.get(u, self.last_now))
                if lane not in first or key < first[lane]:
                    first[lane] = key
        return sorted(first, key=lambda lane: first[lane])

    def focus_seat(self, seat: int) -> None:
        """/control bấm vào khách trên xe (giường `seat`, đếm từ 1): màn live zoom vào cửa sổ người đó; 0 = bỏ."""
        if seat <= 0:
            self.focus = None
            return
        uid = self.bus.seats[seat - 1] if seat <= len(self.bus.seats) else None
        if uid is None:
            raise Refused("Giường này đang trống.")
        self.focus = {"uid": uid, "until": self.last_now + FOCUS_SECONDS}

    def _focus_view(self) -> dict | None:
        f = self.focus
        if not f:
            return None
        seat = self.bus.seat_of(f["uid"])
        if seat is None or self.last_now >= f["until"]:  # đã xuống xe / hết giờ
            self.focus = None
            return None
        v = self.viewers[f["uid"]]
        t = self.ticket_of(v)
        return {"seat": seat, "name": v.name, "vip": v.vip, "province": BY_KEY[v.province].name if v.province else "",
                "stops_before": t.get("stops_before"), "in_s": t.get("in_s"), "trips": v.trips,
                "left": round(f["until"] - self.last_now, 1)}

    def set_next_lane(self, lane: str) -> None:
        """/control «Chạy kế tiếp»: chuyến sau (hết chuyến đang chạy) đi hướng này; "" = bỏ chọn, về thứ tự đặt vé."""
        if lane and lane not in self.queues:
            raise ValueError(lane)
        if lane and not self.queues[lane]:
            raise Refused("Hướng này chưa ai chờ.")
        self.next_lane = lane or None

    def upcoming(self) -> list[dict]:
        """Các chuyến sắp chạy cho /control: số chuyến, hướng, bao nhiêu người chờ, ai đầu hàng."""
        order = self._fifo_order()
        if self.next_lane in order:
            order.remove(self.next_lane)
            order.insert(0, self.next_lane)
        out = []
        for i, key in enumerate(order):
            ln = self.network.lane_by_key[key]
            head = self.viewers[self.queues[key][0]]
            out.append({"lane": key, "label": ln.label, "arrow": ln.arrow, "trip": self.bus.no + 1 + i,
                        "waiting": len(self.queues[key]), "first": head.name, "gift": head.priority,
                        "chosen": key == self.next_lane})
        return out

    def drive_seconds(self, total_km: float, rush: bool = False) -> float:
        """Giây chạy đường của cả chuyến `total_km` (BR-7): xa lâu hơn, nhưng cong (mũ DRIVE_CURVE) chứ không tỉ lệ thẳng."""
        seconds = max(DRIVE_MIN_SECONDS, self.trip_minutes * 60 * (total_km / LONGEST_KM) ** DRIVE_CURVE)
        return seconds * (RUSH_DRIVE_FACTOR if rush else 1.0)

    def _kmps(self, total_km: float) -> float:
        """Tốc độ nén (km / giây) cho cả chuyến xe chính."""
        return max(1e-3, total_km) / self.drive_seconds(total_km, self.rush())

    def _fits(self, province: str | None) -> bool:
        """Xe đang đón chở được tỉnh này: cùng làn, hoặc nằm dọc đường tới điểm cuối của làn (PLAN-134 C)."""
        return province is not None and province in self.network.serves(self.bus.lane)

    def _fill_from_queue(self) -> None:
        called: list[str] = []
        self._fill_seats(called)
        if called:  # gọi tên một lượt (một câu) cho mọi người im lặng lâu vừa tới lượt
            names = [self.viewers[u].name for u in called]
            self.emit("rollcall", names=names, name=names[0], seconds=round(self.roll_wait))
            who = ", ".join(names[:-1]) + f" và {names[-1]}" if len(names) > 1 else names[0]
            self.talk("rollcall", speak=False, name=who if len(names) <= 4 else f"{', '.join(names[:3])} và {len(names) - 3} bạn nữa",
                      seconds=round(self.roll_wait), main=True)

    def _fill_seats(self, called: list[str]) -> None:
        """Lấy người chờ lên xe: hàng chờ làn của xe trước, rồi người chờ làn khác mà xe đi ngang quê họ — ai chờ lâu
        trước (PLAN-134 C: khách Huế chờ xe «Hướng Đà Nẵng» lên được xe «Hướng Hà Nội» còn giường)."""
        served = self.network.serves(self.bus.lane)
        others = sorted((self.queued_at.get(uid, 0.0), uid) for lane, q in self.queues.items() if lane != self.bus.lane
                        for uid in q if self.viewers[uid].province in served)
        for uid in [*list(self.queues[self.bus.lane]), *(uid for _, uid in others)]:
            if (free := self.bus.free_seat()) is None:
                return
            if self._ghost(uid):  # vé ma: không chở người đã rời phòng
                self._release(self.viewers[uid])
                continue
            if uid in self.rollcalls or self.viewers[uid].roll_skip == self.bus.no:
                continue  # đang chờ trả lời điểm danh / đã lỡ điểm danh chuyến này
            if self.bus.seats.count(None) <= self._held_seats():
                return  # giường còn lại đang giữ cho người được gọi tên (gọi tên vừa đủ số giường trống)
            if self._needs_roll(uid):
                self.rollcalls[uid] = self.last_now + self.roll_wait
                called.append(uid)
                continue
            self._unqueue(uid)
            self.bus.seats[free] = uid
            self.seated_at.append(self.last_now)
            # báo người chờ là ĐÃ LÊN XE (rà soát live 02/11: 45 người giữ chỗ được xếp lên xe trong im lặng — thẻ vẫn ghi
            # «chuyến sau» dù đã nằm giường, có người về tới quê rồi)
            self._ticket(self.viewers[uid], free, changed=False, promoted=True)

    # ---- cô bán hàng lên xe (anh 03/11) ---------------------------------------------------------------------

    def _vendor_ready(self) -> bool:
        """Cô lên được lúc xe đang chạy đường bình thường (không bị chặn / đón / xem video / chen cảnh)."""
        return (self.phase == "DRIVING" and not self.block and not self.halt and not self.show and not self.vendor
                and not self.vendor_done and self.trip is not None and not self.quiz)

    def _vendor_tick(self, now: float) -> None:
        if self.vendor and self.vendor["stage"] == "sell" and self.phase in ("FINISH", "BOARDING"):  # hết chuyến: cô xuống
            sold = self.vendor["sold"]
            self.vendor = None
            self.emit("vendor_end", name=VENDOR_NAME, sold=sum(sold.values()))
            self.talk("vendor_end", name=VENDOR_NAME, n=sum(sold.values()), main=True)
        elif self.vendor_on and self.vendor_pool["paid"] >= self.vendor_xu and self._vendor_ready():
            givers = self.vendor_pool["givers"]
            self._start_vendor(max(givers.items(), key=lambda kv: kv[1])[0] if givers else "", now)

    def _hunger_tick(self, dt: float) -> None:
        """Xe chạy thì khách đói dần; vừa xuống dưới HUNGRY thì lơ xe gom tên nhắc (cô Ba trên xe: gõ món; chưa có: góp gọi cô)."""
        drop = HUNGER_PER_MIN * dt / 60.0
        for uid in self.bus.riders():
            v = self.viewers[uid]
            v.full = max(0.0, v.full - drop)
            if v.full < HUNGRY and not v.hungry_told:
                v.hungry_told = True
                self.hungry_new.append(v.name)
                self.emit("hungry", name=v.name, seat=self.bus.seat_of(uid), full=round(v.full))
        if self.hungry_new and self.last_now - self.last_hunger_talk >= HUNGER_TALK_GAP:
            self.last_hunger_talk = self.last_now
            names, self.hungry_new = self.hungry_new, []
            self.talk("hungry_vendor" if self.vendor else "hungry_call", name=who_of(names), vendor=VENDOR_NAME, main=True)

    def _feed(self, v: Viewer) -> None:
        v.full = 100.0
        v.hungry_told = False
        if v.name in self.hungry_new:
            self.hungry_new.remove(v.name)

    def vendor_now(self) -> None:
        """/control «Gọi cô bán hàng»: lên xe ngay (không cần góp), xe phải đang chạy đường."""
        if self.vendor:
            raise Refused("Cô bán hàng đang trên xe rồi.")
        if self._phase_now() != "DRIVING" or self.block or self.halt or self.show:
            raise Refused("Chỉ gọi được lúc xe đang chạy đường (không dừng đón / bị chặn / xem video).")
        self.vendor_done = False
        self._start_vendor("", self.last_now)

    def _start_vendor(self, by: str, now: float) -> None:
        self.vendor_done = True
        self.vendor_pool = {"paid": 0, "givers": {}}
        self.vendor = {"stage": "stop", "until": now + VENDOR_STOP_S, "by": by, "sold": Counter(), "treats": []}
        place = BY_KEY[self._where()[0]].name
        self.emit("vendor", stage="stop", name=VENDOR_NAME, by=by, place=place, seconds=round(VENDOR_STOP_S))
        self.talk("vendor_board" if by else "vendor_board_admin", name=by, vendor=VENDOR_NAME, prov=place, main=True)

    def _pay_vendor(self, v: Viewer, diamonds: int) -> str:
        """Quà (khi không bị chặn): cô đang bán → người tặng bao cả xe món mình gõ gần nhất; chưa lên → góp gọi cô."""
        if not self.vendor_on:
            return ""
        if self.vendor and self.vendor["stage"] == "sell":
            item = v.snack or "banh_mi"
            label, emoji = SNACKS[item]
            for uid in self.bus.riders():
                self.viewers[uid].snack = item
                self._feed(self.viewers[uid])
            self.vendor["sold"][item] += len(self.bus.riders())
            self.vendor["treats"].append(v.name)
            self.emit("vendor_treat", name=v.name, item=label, emoji=emoji, riders=len(self.bus.riders()))
            self.talk("vendor_treat", name=v.name, item=label.lower(), main=True)
            return f"{emoji} bao cả xe {label.lower()}"
        if self.vendor or self.vendor_done or self.phase in ("FINISH", "DROPOFF") or not self.bus.riders():
            return ""
        pool = self.vendor_pool
        pool["paid"] += diamonds
        pool["givers"][v.name] = pool["givers"].get(v.name, 0) + diamonds
        if pool["paid"] >= self.vendor_xu:
            return "🧺 góp đủ, cô bán hàng sắp lên xe"
        if self.last_now - self.last_vendor_remind >= VENDOR_REMIND_GAP:
            self.last_vendor_remind = self.last_now
            self.talk("vendor_pool", name=v.name, left=self.vendor_xu - pool["paid"], main=True)
        return f"🧺 góp gọi cô bán hàng · {pool['paid']}/{self.vendor_xu}"

    def _buy_snack(self, v: Viewer, item: str) -> None:
        if v.snack == item and v.full >= HUNGRY:
            return  # vừa mua món này, còn no
        self._feed(v)
        v.snack = item
        self.vendor["sold"][item] += 1
        label, emoji = SNACKS[item]
        self.emit("snack", name=v.name, hue=v.hue, item=label, emoji=emoji, seat=self.bus.seat_of(v.uid))

    def _vendor_view(self) -> dict | None:
        if self.vendor:
            vd = self.vendor
            left = round(max(0.0, vd["until"] - self.last_now)) if vd["stage"] == "stop" else None
            return {"stage": vd["stage"], "left": left, "name": VENDOR_NAME,
                    "by": vd["by"], "sold": sum(vd["sold"].values()), "treats": vd["treats"][-3:]}
        if self.vendor_on and not self.vendor_done and self.phase == "DRIVING" and self.bus.riders():
            return {"stage": "pool", "paid": self.vendor_pool["paid"], "goal": self.vendor_xu, "name": VENDOR_NAME}
        return None

    def _wait_names(self, now: float) -> bool:
        if not (self.names_pending and self.bus.riders()):
            return False
        if self.name_hold_from is None:
            self.name_hold_from = now
        return now - self.name_hold_from < NAME_HOLD_MAX

    def _needs_roll(self, uid: str) -> bool:
        """Điểm danh chỉ lúc tới lượt xếp giường ở bến (xe chính đang đón), với người im lặng lâu — im lặng vẫn có thể đang xem."""
        return (self.roll_on and self.boarding_open()
                and self.last_now - self.viewers[uid].last_seen > self.roll_idle)

    def _held_seats(self) -> int:
        """Giường giữ cho người đang được gọi tên ở xe này (chỉ người cùng làn / xe đi ngang quê)."""
        served = self.network.serves(self.bus.lane)
        return sum(1 for uid in self.rollcalls if uid in self.queued_at and self.viewers[uid].province in served)

    def _answer_roll(self, v: Viewer) -> None:
        """Người được gọi tên thả tim / bình luận / tặng quà: giữ vé, lên giường đang giữ (còn đang đón)."""
        v.roll_missed = 0
        v.roll_skip = -1
        if self.rollcalls.pop(v.uid, None) is None:
            return
        self.emit("rollcall_ok", name=v.name)
        self.talk("rollcall_ok", name=v.name, main=True)
        if self.boarding_open():
            self._fill_from_queue()

    def _expire_rolls(self) -> None:
        """Hết giờ điểm danh không ai trả lời: lần đầu lùi xuống chuyến sau, lỡ ROLL_MISS_MAX lần thì bỏ vé; giường giữ trả lại."""
        expired = [uid for uid, until in self.rollcalls.items() if self.last_now >= until]
        for uid in expired:
            del self.rollcalls[uid]
            v = self.viewers[uid]
            if uid not in self.queued_at:  # đã bỏ / đổi vé trong lúc chờ
                continue
            v.roll_missed += 1
            if v.roll_missed >= ROLL_MISS_MAX:
                v.roll_missed = 0
                v.roll_skip = -1
                self._release(v)
                self.emit("rollcall_drop", name=v.name)
                self.talk("rollcall_drop", name=v.name, main=True)
            else:
                v.roll_skip = self.bus.no
                self.emit("rollcall_skip", name=v.name)
                self.talk("rollcall_skip", name=v.name, main=True)
        if expired and self.boarding_open():
            self._fill_from_queue()

    def _depart(self, now: float) -> None:
        """BR-3: ghé theo đường thật (`Network.plan`); trạm nghỉ ở giữa quãng (chuyến dài: 2 trạm, chuyến ngắn: không),
        đặt ở tỉnh xe đang đi qua lúc đó."""
        net = self.network
        self.trip = trip = net.plan(sorted({self.viewers[uid].province for uid in self.bus.riders()}))
        legs = [Leg("stop", key, odo) for key, odo in trip.stops]
        total = trip.total
        stops = [key for key, _ in trip.stops]
        two = total > TWO_RESTS_KM and not self.rush() and not self.waiting()
        rest_at = [] if total < REST_MIN_KM else [total / 3, total * 2 / 3] if two else [total / 2]
        for km in rest_at:
            idx = next(i for i, leg in enumerate(legs) if leg.km >= km)
            legs.insert(idx, Leg("rest", net.place_at(*trip.at(km)), km))
        self.legs = legs
        self.leg_index = 0
        self.block_plan = self._plan_blocks(total)
        self.place_shown = self.place_cand = None
        if self.boarding_started is not None:
            self.board_avg += AVG_WEIGHT * (now - self.boarding_started - self.board_avg)
        self.trip_started = now
        self.clock0 = datetime.now(VN)
        # thưởng tốc độ theo xăng / độ sạch lúc xuất bến (PLAN-137); thiếu thì vẫn chạy bình thường
        self.trip_bonus = 1.0 + FUEL_BONUS * (self.fuel >= 0.8) + CLEAN_BONUS * (self.dirt <= 0.2)
        lane = net.lane_by_key[self.bus.lane]
        self.emit("depart", bus_no=self.bus.no, riders=len(self.bus.riders()), lane=lane.label,
                  stops=[BY_KEY[k].name for k in stops], km=round(total))
        self.talk("depart", dest=self._dest(self.bus.lane), hours=hours_phrase(Network.hours(total)), main=True)
        self._roll_weather(BY_KEY[self._where()[0]].region, now, force=True)
        self._enter_driving(now)

    def _leg_start_km(self) -> float:
        return self.legs[self.leg_index - 1].km if self.leg_index > 0 else 0.0

    def _enter_driving(self, now: float) -> None:
        # thời gian chặng tỉ lệ km thật; tính lại mỗi chặng: hàng chờ dài lên giữa chuyến thì xe chạy nhanh lên ngay
        km = max(0.0, self.current_leg().km - self._leg_start_km())
        self.leg_seconds = max(LEG_SECONDS_MIN, km / self._kmps(self.trip.total))
        self.progress = 0.0
        self._set_phase("DRIVING", now, 0)

    def trip_km(self) -> float:
        """Km xe đã chạy từ bến đi (giữa chặng thì nội suy theo tiến độ)."""
        leg = self.current_leg()
        if leg is None:
            return 0.0
        start = self._leg_start_km()
        phase = self._phase_now()
        if phase == "DRIVING":
            return start + (leg.km - start) * self.progress
        return leg.km if phase in ("DROPOFF", "REST") else start

    def _pace(self, trip: Trip, odo: float, kmps: float) -> float:
        """< 1 khi đang qua đèo / hầm: cả đoạn đèo kéo dài ít nhất PASS_SECONDS, hầm TUNNEL_SECONDS."""
        found = self.network.pass_at(*trip.at(odo))
        if found is None:
            return 1.0
        span = 2 * (TUNNEL_SPAN_KM if found.tunnel else PASS_SPAN_KM)
        seconds = TUNNEL_SECONDS if found.tunnel else PASS_SECONDS
        # thưởng xăng / rửa xe (PLAN-137) không rút ngắn đèo / hầm: vẫn đủ PASS_SECONDS cho người xem kịp thấy
        return min(1.0, span / kmps / seconds / self.trip_bonus)

    def rush(self) -> bool:
        """BR-9: cao điểm theo từng hướng — làn của xe này còn từ một xe khách chờ."""
        return len(self.queues[self.bus.lane]) >= RUSH_QUEUE

    def _arrive(self, now: float) -> None:
        leg = self.current_leg()
        if leg.kind == "rest":
            self.rest_orders = Counter()
            self.wc_line = []
            self.treated = set()
            self.honked = False
            self._set_phase("REST", now, min(self.rest_seconds, RUSH_REST_SECONDS) if self.rush() else self.rest_seconds)
            place = BY_KEY[leg.target]
            self.emit("rest", region=place.region, specialty=specialty_of(place.key), place=place.name)
            self.talk("rest", place=place.name, specialty=spoken_list(specialty_of(place.key)), main=True)
            return
        prov = BY_KEY[leg.target]
        uids = [uid for uid in self.bus.riders() if self.viewers[uid].province == leg.target]
        for uid in uids:
            self.bus.seats[self.bus.seat_of(uid)] = None
        info = self._deliver(uids, leg.target, self.bus.no)
        pages = max(1, math.ceil(len(uids) / NAMES_PER_PAGE))
        self._set_phase("DROPOFF", now, DROPOFF_BASE + PAGE_SECONDS * pages)
        self.emit("dropoff", **info)
        givers = [p["name"] for p in info["people"] if p["parcels"]]
        if givers:  # thùng quà Tết của ai thì giao tận cổng, gọi tên (PLAN-134 C)
            more = len(givers) - 3
            self.talk("parcels", names=", ".join(givers[:3]) + (f" và {more} người nữa" if more > 0 else ""), main=True)
        self.talk("dropoff_bubble", speak=False, prov=prov.name, main=True)  # giọng đọc có câu riêng kèm tên người xuống

    def _deliver(self, uids: list[str], province: str, bus_no: int) -> dict:
        """Thả khách về tới tỉnh (xe chính / xe tăng cường): cập nhật thống kê, trả nội dung băng rôn đọc tên."""
        prov = BY_KEY[province]
        km = self.network.km(province)  # km tuyến của khách (bến đi → tỉnh), không phải km xe đã chạy vòng
        people, fireworks = [], False
        for uid in uids:
            v = self.viewers[uid]
            v.home = province
            v.home_now = True
            v.province = None
            v.trips += 1
            self.dirty.add(uid)
            fireworks = fireworks or v.fireworks
            people.append({"name": v.name, "hue": v.hue, "vip": v.vip, "wish": pick(WISHES, f"{uid}:{bus_no}"),
                           "parcels": v.parcels})
            v.fireworks = False
            v.vip = False
            v.parcels = 0
        self.delivered += len(people)
        self.delivered_km += km * len(people)
        return {"province": prov.name, "region": prov.region, "people": people, "km": km, "bus_no": bus_no,
                "hours": round(Network.hours(km), 1), "departure": self.network.departure.short,
                "fireworks": fireworks, "page_size": NAMES_PER_PAGE, "page_seconds": PAGE_SECONDS}

    # ---- xe tăng cường ---------------------------------------------------

    def _dispatch_relief(self, lane: str, sponsor: Viewer | None = None, admin: bool = False) -> Relief | None:
        """Một xe tăng cường chở tối đa 24 người đầu hàng làn `lane` (người tặng quà lên trước) xuất bến ngay.
        Xe tự động giới hạn RELIEF_MAX; xe do quà / admin gọi được tới RELIEF_MAX_GIFT."""
        if len(self.reliefs) >= (RELIEF_MAX_GIFT if sponsor or admin else RELIEF_MAX):
            return None
        self._prune_queues()
        queue = self.queues[lane]
        if not queue:
            return None
        riders = [sponsor.uid] if sponsor and sponsor.uid in queue else []
        riders += [uid for uid in queue if uid not in riders][:SEATS - len(riders)]
        for uid in riders:
            self._unqueue(uid)
        trip = self.network.plan(sorted({self.viewers[uid].province for uid in riders}))
        ln_ = self.network.lane_by_key[lane]
        for uid in riders:  # từng người biết mình lên xe tăng cường số mấy (trước chỉ đọc 3 tên đầu)
            v = self.viewers[uid]
            self.emit("ticket", name=v.name, hue=v.hue, province=BY_KEY[v.province].name, seat=None, changed=False,
                      trip_no=v.trips + 1, lane=ln_.label, arrow=ln_.arrow, km=self.network.km(v.province),
                      departure=self.network.departure.short, bus_no=self.bus_counter + 1, next=False, relief=True,
                      promoted=True)
        self.bus_counter += 1
        relief = Relief(self.bus_counter, lane, riders, sponsor.name if sponsor else None, trip,
                        max(1e-3, trip.total) / self.drive_seconds(trip.total), datetime.now(VN))
        self.reliefs.append(relief)
        ln = self.network.lane_by_key[lane]
        names = [self.viewers[uid].name for uid in riders]
        self.emit("relief_depart", bus_no=relief.no, lane=ln.label, arrow=ln.arrow, sponsor=relief.sponsor,
                  names=names[:3], count=len(names), km=round(trip.total))
        dest = self._dest(lane)
        if sponsor:
            self.talk("relief_gift", name=sponsor.name, dest=dest)
        else:
            self.talk("relief_admin" if admin else "relief_auto", dest=dest)
        return relief

    def _run_reliefs(self, dt: float) -> None:
        """Tự gọi xe tăng cường cho làn đủ một xe người chờ; xe chạy (đèo / hầm chậm lại), tới tỉnh nào thả khách tỉnh đó."""
        self._prune_queues()
        if self.relief_auto and RELIEF_AUTO:
            for lane, queue in self.queues.items():
                while len(queue) >= SEATS and self._dispatch_relief(lane):
                    pass
        for relief in list(self.reliefs):
            relief.odo = min(relief.trip.total,
                             relief.odo + dt * relief.kmps * self._pace(relief.trip, relief.odo, relief.kmps))
            odo = relief.odo
            while relief.done < len(relief.trip.stops) and odo >= relief.trip.stops[relief.done][1]:
                province = relief.trip.stops[relief.done][0]
                relief.done += 1
                uids = [uid for uid in relief.riders if self.viewers[uid].province == province]
                relief.riders = [uid for uid in relief.riders if uid not in uids]
                relief.dropped_at = self.last_now
                self.emit("relief_dropoff", **self._deliver(uids, province, relief.no), sponsor=relief.sponsor)
                if relief.no == self.featured:  # giọng đọc có câu riêng kèm tên; bong bóng cho người đang xem xe này
                    self.talk("dropoff_bubble", speak=False, prov=BY_KEY[province].name)
            if relief.no == self.featured:
                self._watch_relief(relief)
            if relief.done >= len(relief.trip.stops):
                self.reliefs.remove(relief)
                if self.featured == relief.no:  # xe đang chiếu tới bến cuối → màn hình quay về xe chính
                    self.featured = None
                    self._introduce(None)
                self.music.pop(str(relief.no), None)

    # ---- admin: mọi chuyến xe -------------------------------------------

    def _relief(self, no: int) -> Relief:
        relief = next((r for r in self.reliefs if r.no == no), None)
        if relief is None:
            raise Refused(f"Xe tăng cường số {no} đã tới bến cuối (không còn chạy).")
        return relief

    def feature(self, no: int | None, manual: bool = True) -> None:
        """Chọn xe nào lên màn hình: None / số xe chính = xe chính; số xe tăng cường = màn hình theo xe đó.
        Admin bấm tay (`manual`) thì tự chiếu nhường admin MANUAL_HOLD giây."""
        featured = None if not no or no == self.bus.no else self._relief(int(no)).no
        changed = featured != self.featured
        if changed:
            self.featured_since = self.last_now
        self.featured = featured
        if changed:
            self._introduce(featured)
        if manual:
            self.manual_until = self.last_now + MANUAL_HOLD
            self.show_until = None

    def stage_of(self, relief: Relief) -> float:
        """Điểm lên sóng của một xe tăng cường = tổng điểm trong buổi của khách trên xe."""
        return sum(self.viewers[u].stage for u in relief.riders if u in self.viewers)

    def _on_air(self, relief: Relief, now: float) -> None:
        """Chiếu một xe tăng cường theo điểm: 15 giây + theo điểm, tối đa SHOW_MAX; báo tên người làm xe lên sóng."""
        score = self.stage_of(relief)
        seconds = min(SHOW_MAX, SHOW_BASE + score * SHOW_PER_POINT)
        relief.shown_at = now
        relief.dropped_at = None
        self.show_until = now + seconds
        self.feature(relief.no, manual=False)
        top = sorted((self.viewers[u] for u in relief.riders if u in self.viewers and self.viewers[u].stage > 0),
                     key=lambda v: (v.name != relief.sponsor, -v.stage))[:ON_AIR_NAMES]
        self.emit("on_air", bus_no=relief.no, names=[v.name for v in top], sponsor=relief.sponsor,
                  count=len(relief.riders), seconds=round(seconds), lane=self.network.lane_by_key[relief.lane].label)

    def auto_feature(self, mode: str, rotate_seconds: float) -> None:
        """Tự chiếu xe (PLAN-130), gọi mỗi nhịp. «events»: cảnh của xe chính (xuất bến, trạm, thả khách, về bến, chúc Tết)
        luôn được chiếu; lúc xe chính chỉ đang chạy thì nhảy sang xe tăng cường sắp thả khách, thả xong quay về.
        «rotate»: lần lượt xe chính → các xe tăng cường, mỗi xe `rotate_seconds` giây."""
        if mode not in FEATURE_MODES[1:] or self.paused or self.last_now < self.manual_until:
            return
        now = self.last_now
        held = now - self.featured_since
        if mode == "rotate":
            order = [None] + [r.no for r in self.reliefs]
            if len(order) > 1 and held >= rotate_seconds:
                at = order.index(self.featured) if self.featured in order else 0
                self.feature(order[(at + 1) % len(order)], manual=False)
            return
        arrive = self._arrivals()[0][self.leg_index] if self.leg_index < len(self.legs) else None
        main_scene = self._phase_now() != "DRIVING" or self.phase == "SPECIAL" or (
            arrive is not None and arrive < FEATURE_LEAD)
        current = next((r for r in self.reliefs if r.no == self.featured), None)
        if current is not None:  # đang chiếu xe tăng cường: thả khách xong / hết lượt lên sóng (hoặc xe chính có cảnh) thì về
            arrive_in = self._relief_arrivals(current)[current.done] if current.done < len(current.trip.stops) else None
            near = arrive_in is not None and arrive_in < FEATURE_LEAD
            ended = self.show_until is not None and now >= self.show_until and current.dropped_at is None and not near
            if main_scene or ended or (current.dropped_at is not None and now - current.dropped_at >= FEATURE_AFTER_DROP):
                self.show_until = None
                self.feature(None, manual=False)
            return
        if main_scene or held < FEATURE_MIN_SECONDS:
            return
        soon = [(self._relief_arrivals(r)[r.done], r) for r in self.reliefs if r.done < len(r.trip.stops)]
        soon = [(t, r) for t, r in soon if t is not None and t < FEATURE_LEAD]
        if soon:
            relief = min(soon, key=lambda x: x[0])[1]
            relief.dropped_at = None
            self.show_until = None
            self.feature(relief.no, manual=False)
            return
        pool = [r for r in self.reliefs if r.done < len(r.trip.stops) and now - r.shown_at >= SHOW_AGAIN]
        if pool:  # lên sóng theo điểm: xe nhiều điểm nhất trong các xe chưa vừa được chiếu
            self._on_air(max(pool, key=self.stage_of), now)

    def _music_key(self, no: int | None) -> str:
        if not no or no == self.bus.no:
            return "main"
        return str(self._relief(int(no)).no)

    def music_of(self, key: str) -> dict:
        """Đài của một xe: bài thứ `index`, bắt đầu lúc `since` (đồng hồ game). Xe tăng cường mặc định lệch bài theo số xe.
        Mỗi xe như một đài radio chạy liên tục kể cả khi không lên màn hình — chuyển sang xe nào là nghe đúng đoạn đang phát."""
        return self.music.setdefault(key, {"index": 0 if key == "main" else int(key), "on": True, "since": self.last_now})

    def advance_music(self, lengths: list[float], auto: bool) -> None:
        """Tự qua bài: đài nào phát hết bài (theo độ dài từng bài) thì sang bài kế, bắt đầu đúng lúc bài trước hết."""
        if not auto or not lengths:
            return
        for state in self.music.values():
            length = lengths[state["index"] % len(lengths)]
            if state["on"] and self.last_now - state["since"] >= length:
                state["index"] += 1
                state["since"] += length
                if self.last_now - state["since"] > length:  # tạm dừng lâu / đổi danh sách: bắt đầu lại bài mới
                    state["since"] = self.last_now

    def _music_view(self, key: str) -> dict:
        state = self.music_of(key)
        return {**state, "pos": round(self.last_now - state["since"], 1)}

    def music_step(self, no: int | None, step: int = 1) -> None:
        """Admin qua bài (step = 1) / lùi bài (−1) cho một xe; overlay lấy index theo vòng danh sách bài."""
        state = self.music_of(self._music_key(no))
        state["index"] += step
        state["since"] = self.last_now

    def music_set(self, no: int | None, index: int) -> None:
        """Admin chọn đúng bài thứ `index` (trong music_tracks) cho một xe."""
        if index < 0:
            raise Refused("Không có bài này.")
        state = self.music_of(self._music_key(no))
        state["index"] = index
        state["since"] = self.last_now

    def music_toggle(self, no: int | None) -> None:
        state = self.music_of(self._music_key(no))
        state["on"] = not state["on"]
        state["since"] = self.last_now  # bật lại: phát bài từ đầu

    def add_relief(self, lane: str) -> Relief:
        """Admin gọi thêm xe tăng cường cho một làn (không cần đủ 24 người chờ)."""
        if lane not in self.queues:
            raise Refused(f"Bến này không có làn «{lane}».")
        if not self.queues[lane]:
            raise Refused("Làn này hiện không có ai chờ — chưa cần xe tăng cường.")
        relief = self._dispatch_relief(lane, admin=True)
        if relief is None:
            raise Refused(f"Đang chạy đủ {RELIEF_MAX_GIFT} xe tăng cường — đợi một xe về bến rồi gọi thêm.")
        return relief

    def relief_next_stop(self, no: int) -> None:
        """Admin cho xe tăng cường tới ngay điểm thả khách kế tiếp."""
        relief = self._relief(int(no))
        relief.odo = max(relief.odo, relief.trip.stops[min(relief.done, len(relief.trip.stops) - 1)][1])

    def _next_leg(self, now: float) -> None:
        self.leg_index += 1
        if self.leg_index >= len(self.legs):
            self._finish(now)
        else:
            self._enter_driving(now)

    def _finish(self, now: float) -> None:
        top = max(self.viewers.values(), key=lambda v: v.likes_trip, default=None)
        top_liker = top.name if top and top.likes_trip > 0 else None
        self._set_phase("FINISH", now, FINISH_SECONDS)
        self.emit("finish", bus_no=self.bus.no, board=self._board_top(),
                  top_liker=top_liker, delivered=self.delivered, delivered_km=self.delivered_km)
        self.talk("finish", main=True)

    def _board_top(self, n: int = 5) -> list[dict]:
        return [{"province": BY_KEY[k].name, "count": c} for k, c in self.board.most_common(n) if c > 0]

    # ---- vòng thời gian ------------------------------------------------

    def _remind_direction(self, now: float) -> None:
        """«Đây là chuyến đi Hà Nội, ai đi Cà Mau, Đồng Tháp đợi chuyến sau» — anh dặn 02/11: người khác hướng comment liên tục
        mà không biết xe này không đi quê họ."""
        if not self.other_dirs or now - self.last_other_talk < OTHER_DIR_GAP:
            return
        # chỉ nhắc tỉnh còn người THẬT SỰ đang chờ làn khác (người đã được xếp lên xe này / xe tăng cường thì thôi)
        waiting = {BY_KEY[self.viewers[u].province].name for lane, q in self.queues.items() if lane != self.bus.lane for u in q
                   if self.viewers[u].province}
        self.other_dirs = [p for p in self.other_dirs if p in waiting]
        if not self.other_dirs:
            return
        self.last_other_talk = now
        names = ", ".join(self.other_dirs[-3:])
        self.other_dirs = []
        self.talk("this_trip", dest=self._dest(self.bus.lane), others=names, main=True)

    def tick(self, now: float) -> None:
        dt = max(0.0, now - self.last_now)
        self.last_now = now
        self.boost *= math.pow(0.5, dt / BOOST_HALF_LIFE)
        if self.paused:
            self.phase_until += dt  # đồng hồ pha đứng yên, xe không chạy
            if self.block:
                self.block["since"] += dt
                if "until" in self.block:
                    self.block["until"] += dt
            if self.quiz:
                self.quiz["until"] += dt
            if self.show:
                self.show["until"] += dt
                self.show["started"] += dt  # tạm dừng không tính vào giờ chờ góp (không tự bù lỗ ngay khi bỏ tạm dừng)
            if self.halt:
                self.halt["until"] += dt  # đang đón người ven đường: bỏ tạm dừng xong vẫn đủ giờ cho họ lên xe
            if self.vendor:
                self.vendor["until"] += dt
            for uid in self.rollcalls:
                self.rollcalls[uid] += dt  # đang gọi tên: tạm dừng không ăn vào giờ trả lời
            return
        self._run_reliefs(dt)
        if self.rollcalls:
            self._expire_rolls()
        self._vendor_tick(now)
        self._quiz_tick(now, dt)
        self._ad_tick(now)
        if self.phase == "DRIVING":
            self._hunger_tick(dt)
        self._remind_direction(now)
        self._remind_rules(now)
        if self.specials and self.phase in SPECIAL_FROM:
            self.resume = (self.phase, max(0.0, self.phase_until - now))
            self._set_phase("SPECIAL", now, SPECIAL_SECONDS)
            self.emit("special", name=self.specials.pop(0))
            return

        if self.phase == "BOARDING":
            self._maybe_switch_station(now)
            if now >= self.phase_until and self._held_seats():
                self.phase_until = min(self.rollcalls.values())  # đang chờ người được gọi tên: đợi hết giờ điểm danh rồi chạy
            elif now >= self.phase_until and self._wait_names(now):
                self.phase_until = now + 1.0  # lơ xe đọc chưa xong tên người lên xe: chờ đọc hết rồi mới chạy
            elif now >= self.phase_until:
                if self.bus.riders():
                    self._depart(now)
                else:  # xe trống: quay sang làn đang có người chờ (BR-4), cho họ lên rồi đón thêm một lúc
                    self.bus.lane = self._pick_lane()
                    self._fill_from_queue()
                    self.phase_until = now + EMPTY_BOARD_RETRY
                    if self.bus.riders():
                        self.talk("switch_lane", dest=self._dest(self.bus.lane), main=True)
        elif self.phase == "DRIVING" and self.vendor and self.vendor["stage"] == "stop":
            if now >= self.vendor["until"]:  # cô lên rồi: xe chạy tiếp, cô bán trong lúc xe chạy
                self.vendor.update(stage="sell", until=math.inf)  # bán suốt chuyến
                self.emit("vendor", stage="sell", name=VENDOR_NAME)
                self.talk("vendor_sell", name=VENDOR_NAME, main=True)
        elif self.phase == "DRIVING" and self.show:
            if now >= self.show["until"]:
                self._end_show()
        elif self.phase == "DRIVING" and self.block:
            self._block_tick(now)  # bị chặn: đứng yên tới khi góp đủ quà / Anh Tư bù lỗ
        elif self.phase == "DRIVING" and self.halt and now < self.halt["until"]:
            pass  # đang dừng bên đường: người chờ lên từng người, xe đứng yên
        elif self.phase == "DRIVING":
            self.halt = None
            self.turbo = max(0.0, self.turbo - dt)
            km_before = self.trip_km()
            self.progress += (dt * self.speed() / self.leg_seconds
                              * self._pace(self.trip, self.trip_km(), self._kmps(self.trip.total)))
            if self.progress >= 1.0:
                self.progress = 1.0
                self._check_pickups()
                self._arrive(now)
            else:
                self._check_pickups()
                self._watch_place(now)
                self._check_blocks(now)
                self._check_show(now)
            self._wear(self.trip_km() - km_before)
        elif self.phase == "SPECIAL":
            if now >= self.phase_until:
                phase, left = self.resume
                self._set_phase(phase, now, left)
        elif self.phase == "REST":
            if not self.honked and now >= self.phase_until - HONK_BEFORE_END:
                self.honked = True
                self.emit("honk")
                self.talk("honk", main=True)
            if now >= self.phase_until:
                self._next_leg(now)
        elif self.phase == "DROPOFF":
            if now >= self.phase_until:
                self._next_leg(now)
        elif self.phase == "FINISH":
            if now >= self.phase_until:
                self._enter_boarding(now)

    # ---- trạm thu phí / công an: chặn xe, góp quà đi tiếp (anh 03/11) -----------------------------

    def _plan_blocks(self, total: float) -> list[tuple[float, str]]:
        """Chỗ xe bị chặn trong chuyến: trạm thu phí cứ ~TOLL_EVERY_KM một trạm, công an ngẫu nhiên, sự cố dọc đường (xẹp
        lốp / kẹt xe / trâu qua đường) ngẫu nhiên; không sát điểm dừng."""
        rng = self.block_rng
        plan: list[tuple[float, str]] = []
        if self.blocks_on:
            if total >= TOLL_MIN_KM:
                n = min(TOLL_MAX, max(1, int(total // TOLL_EVERY_KM)))
                plan += [(total * (i + 1) / (n + 1) * rng.uniform(0.9, 1.1), "toll") for i in range(n)]
            if total >= POLICE_MIN_KM and rng.random() < POLICE_CHANCE:
                plan.append((total * rng.uniform(0.2, 0.85), "police"))
            chance = 1.0 if not self.fee_auto else max(BLOCK_KEEP_MIN, min(1.0, self._gift_rate() / BLOCK_FULL_RATE))
            plan = [(odo, kind) for odo, kind in plan if rng.random() < chance]
        if self.incidents_on and total >= INCIDENT_MIN_KM and rng.random() < INCIDENT_CHANCE:
            plan.append((total * rng.uniform(0.15, 0.85), rng.choice(tuple(INCIDENTS))))  # sự cố: không tốn ai đồng nào
        return self._clear_spots(plan, total)

    def _clear_spots(self, plan: list[tuple[float, str]], total: float) -> list[tuple[float, str]]:
        """Bỏ chỗ chặn sát điểm thả khách / trạm nghỉ / đầu cuối chuyến, và chỗ quá gần chỗ chặn trước."""
        keep: list[tuple[float, str]] = []
        for odo, kind in sorted(plan):
            if (BLOCK_CLEAR_KM < odo < total - BLOCK_CLEAR_KM and all(abs(odo - leg.km) > BLOCK_CLEAR_KM for leg in self.legs)
                    and all(abs(odo - o) > BLOCK_GAP_KM for o, _ in keep)):
                keep.append((odo, kind))
        return keep

    def _check_blocks(self, now: float) -> None:
        if (self.block or self.halt or self.show or self.quiz or not self.block_plan
                or self.trip_km() < self.block_plan[0][0]):
            return  # đang đố vui: trạm / công an / sự cố chờ câu đố xong (không thay mất thẻ câu hỏi giữa chừng)
        _, kind = self.block_plan.pop(0)
        self._start_block(kind, now)

    def block_now(self, kind: str) -> None:
        """Admin bấm «Trạm thu phí» / «Công an» trên /control: chặn xe ngay (xe phải đang chạy đường)."""
        if kind not in WHAT:
            raise ValueError(kind)
        if self._phase_now() != "DRIVING" or self.block or self.halt or self.show:
            raise Refused("Chỉ chặn được lúc xe đang chạy đường (không đang dừng đón / bị chặn / xem video).")
        self._start_block(kind, self.last_now)
        self.block["manual"] = True  # anh bấm tay: vẫn chặn dù đã tắt «tự gặp trạm / công an dọc đường»

    def _start_block(self, kind: str, now: float) -> None:
        place = BY_KEY[self._where()[0]].name
        speeding = False
        if kind in INCIDENTS:
            icon, title, _ = INCIDENTS[kind]
            goal = self._fee(self.incident_xu)
            self.block = {"kind": kind, "reason": title, "goal": goal, "paid": 0, "givers": {}, "since": now,
                          "place": place, "speeding": False, "until": now + INCIDENT_SECONDS}
            self.last_block_remind = now
            self.emit("block", block=kind, reason=title, goal=goal, place=place, speeding=False)
            self.talk(kind, place=place, goal=goal, main=True)
            return
        if kind == "toll":
            reason, goal = f"Trạm thu phí {place}", self._fee(self.toll_xu)
        else:
            speeding = self.turbo > 0  # giây chạy nhanh còn lại không mất: nộp phạt xong chạy tiếp
            if speeding:
                reason, goal = "chạy quá tốc độ", self._fee(self.fine_xu) * SPEEDING_FACTOR
            else:
                reason, goal = self.block_rng.choice(POLICE_REASONS), self._fee(self.fine_xu)
        self.block = {"kind": kind, "reason": reason, "goal": goal, "paid": 0, "givers": {}, "since": now,
                      "place": place, "speeding": speeding}
        self.last_block_remind = now
        self.emit("block", block=kind, reason=reason, goal=goal, place=place, speeding=speeding)
        if kind == "toll":
            self.talk("toll", place=place, goal=goal, main=True)
        else:
            self.talk("speeding" if speeding else "police", reason=reason, goal=goal, main=True)

    # ---- đố vui · chuyện từng tỉnh · thời tiết (anh 03/11: live đỡ lặp, đỡ giống video quay sẵn) -------------------

    def _quiz_ready(self) -> bool:
        return (self.quiz_on and self.phase == "DRIVING" and self.trip is not None and not self.block and not self.halt
                and not self.show and not (self.vendor and self.vendor["stage"] == "stop")
                and (1 - self.progress) * self.leg_seconds >= QUIZ_SECONDS + QUIZ_RESULT_S + QUIZ_LEAD_S)

    def _quiz_tick(self, now: float, dt: float = 0.0) -> None:
        q = self.quiz
        if q and not q["done"] and (self.block or self.show or (self.vendor and self.vendor["stage"] == "stop")
                                    or self.phase != "DRIVING"):
            q["until"] += dt  # thẻ câu hỏi bị thay (anh bấm chặn xe / chiếu video, xe tới điểm thả / trạm nghỉ) → đồng hồ chờ
        if q and now >= q["until"]:
            if q["done"]:
                self.quiz = None
            else:
                self._end_quiz(now)
        elif not q and now >= self.next_quiz and self._quiz_ready():
            self._start_quiz(now)

    def quiz_now(self) -> None:
        """Admin bấm «Đố vui ngay» trên /control."""
        if self.quiz and not self.quiz["done"]:
            raise Refused("Đang có câu đố rồi.")
        self._start_quiz(self.last_now)

    def _start_quiz(self, now: float) -> None:
        prefer = self.place_now if self.phase == "DRIVING" else None  # đố về chính tỉnh xe đang chạy qua
        q = make_quiz(self.rng, prefer, tuple(self.quiz_recent))
        self.quiz_recent = [*self.quiz_recent, q["key"]][-QUIZ_RECENT:]
        self.quiz = {**q, "until": now + QUIZ_SECONDS, "done": False, "answers": {}, "winners": []}
        self.next_quiz = now + self.quiz_gap
        a, b, c = q["options"]
        self.emit("quiz", question=q["question"], options=q["options"], seconds=QUIZ_SECONDS)
        self.talk("quiz_ask", q=q["question"], a=a, b=b, c=c)

    def _quiz_answer(self, v: Viewer, ans: int) -> None:
        """Mỗi người chỉ tính câu trả lời đầu tiên (không đoán dồn A rồi B rồi C)."""
        q = self.quiz
        if v.uid in q["answers"]:
            return
        q["answers"][v.uid] = ans
        if ans == q["answer"]:
            v.quiz_score += 1
            if len(q["winners"]) < QUIZ_WINNERS:
                q["winners"].append(v.name)
                self._race(v, QUIZ_RACE)

    def _end_quiz(self, now: float) -> None:
        q = self.quiz
        q.update(done=True, until=now + QUIZ_RESULT_S)
        right = sum(1 for a in q["answers"].values() if a == q["answer"])
        ans = f"{LETTERS[q['answer']]}, {q['options'][q['answer']]}"
        self.emit("quiz_end", answer=LETTERS[q["answer"]], option=q["options"][q["answer"]], winners=q["winners"],
                  right=right, total=len(q["answers"]))
        if q["winners"]:
            self.talk("quiz_win", ans=ans, name=who_of(q["winners"]))
        else:
            self.talk("quiz_none", ans=ans)

    def _quiz_view(self) -> dict | None:
        q = self.quiz
        if not q:
            return None
        view = {"question": q["question"], "options": q["options"], "left": round(max(0.0, q["until"] - self.last_now)),
                "answered": len(q["answers"]), "done": q["done"]}
        if q["done"]:
            view.update(answer=q["answer"], winners=q["winners"],
                        right=sum(1 for a in q["answers"].values() if a == q["answer"]))
        return view

    def _roll_weather(self, region: str, now: float, force: bool = False) -> None:
        """Xe vào vùng mới (hoặc xuất bến): bốc thời tiết theo vùng — mưa phùn Bắc, mưa rào Nam, sương Tây Nguyên."""
        if region == self.weather_region and not force:
            return
        self.weather_region = region
        roll, acc, kind = self.rng.random(), 0.0, "clear"
        for k, chance in WEATHER_ODDS.get(region, ()):
            acc += chance
            if roll < acc:
                kind = k
                break
        if kind == self.weather:
            return
        self.weather = kind
        self.emit("weather", sky=kind)
        if now - self.last_weather_talk >= WEATHER_TALK_GAP:
            self.last_weather_talk = now
            self.talk(f"weather_{kind}", main=True)

    def _ad_tick(self, now: float) -> None:
        """Lơ xe đọc quảng cáo bot của anh mỗi ad_gap giây, lần lượt từng bot; né lúc đang đố / bị chặn / chiếu video."""
        if not self.ads or now < self.next_ad or self.quiz or self.block or self.show or self.phase == "SPECIAL":
            return
        self.ad_now()

    def ad_now(self) -> None:
        """Đọc quảng cáo kế tiếp ngay (admin bấm trên /control)."""
        if not self.ads:
            raise Refused("Chưa có quảng cáo nào (hoặc đang tắt).")
        ad = self.ads[self.ad_index % len(self.ads)]
        self.ad_index += 1
        self.next_ad = self.last_now + self.ad_gap
        self.emit("ad", title=ad["title"], desc=ad.get("desc", ""))
        self.loxe(ad.get("say") or f"{ad['title']}, {ad.get('desc', '')}")

    def set_weather(self, kind: str) -> None:
        """Admin đổi thời tiết tay trên /control (giữ tới khi xe sang vùng mới)."""
        if kind not in ("clear", *(k for odds in WEATHER_ODDS.values() for k, _ in odds)):
            raise Refused("Không có kiểu thời tiết này.")
        if kind != self.weather:
            self.weather = kind
            self.emit("weather", sky=kind)
            self.last_weather_talk = self.last_now
            self.talk(f"weather_{kind}", main=True)

    def _chatter(self, v: Viewer, text: str, now: float) -> None:
        """Chuyện phiếm (không phải lệnh, không phải câu hỏi) khi bật AI: xếp hàng cho AI đáp lại — lơ xe nói chuyện với
        người xem thay vì chỉ đọc câu mẫu."""
        if (len(normalize(text).split()) < 3 or now - v.last_chatter < CHATTER_PER_VIEWER or not allow_chat(text)
                or any(c["uid"] == v.uid for c in self.chatter)):
            return
        self.chatter = [*self.chatter, {"uid": v.uid, "name": v.name, "text": text.strip()[:200], "at": now,
                                        "chat": True}][-CHATTER_KEEP:]

    # ---- đua tỉnh -------------------------------------------------------------------------------

    def _race(self, v: Viewer, points: int) -> None:
        """Cộng điểm đua tỉnh cho tỉnh quê của người xem (vé đang có, không thì quê đã về lần trước)."""
        key = v.province or v.home
        if not self.race_on or not key or points <= 0:
            return
        self.race[key] += points
        leader = self.race.most_common(1)[0][0]
        if leader != self.race_leader:
            self.race_leader = leader
            if self.last_now - self.last_race_talk >= RACE_TALK_GAP:
                self.last_race_talk = self.last_now
                self.talk("race_lead", prov=BY_KEY[leader].name)

    # ---- bảng quảng cáo: dừng xe xem video ----------------------------------------------------

    def _in_pass(self) -> bool:
        """Xe đang trong hầm / trên đèo: vách hầm, sườn núi che mất bảng quảng cáo (anh báo 03/11 «chiếu không hết video»)."""
        return self.trip is not None and self.network.pass_at(*self.trip.at(self.trip_km())) is not None

    def _check_show(self, now: float) -> None:
        pending = self.show_pending
        if self.show or self.block or self.halt or not self.videos or self._in_pass():
            return
        if pending is None and (not self.shows_on or now < self.next_show or self.quiz
                                or not SHOW_LEG_WINDOW[0] <= self.progress <= SHOW_LEG_WINDOW[1]):
            return  # tự chiếu: chỉ giữa chặng
        self.show_pending = None
        video = next((x for x in self.videos if x["name"] == pending), None) if pending else None
        if video is None:
            video = self.videos[self.show_index % len(self.videos)]
            self.show_index += 1
        self._start_show(video, now)

    def show_now(self, name: str = "") -> None:
        """Admin bấm «Chiếu ngay» (một video cụ thể hoặc video kế tiếp): xe phải đang chạy đường."""
        if not self.videos:
            raise Refused("Chưa có video nào — tải video lên trước.")
        if self._phase_now() != "DRIVING" or self.block or self.halt or self.show:
            raise Refused("Chỉ chiếu được lúc xe đang chạy đường (không đang dừng đón / bị chặn / đang chiếu).")
        if self._in_pass():
            self.show_pending = name or ""  # trong hầm / trên đèo: hẹn, ra chỗ thoáng là chiếu
            raise Refused("Xe đang trong hầm / trên đèo (vách che mất bảng) — đã hẹn, ra khỏi hầm / đèo xe tự dừng chiếu.")
        video = next((x for x in self.videos if x["name"] == name), None)
        if video is None:
            video = self.videos[self.show_index % len(self.videos)]
            self.show_index += 1
        self._start_show(video, self.last_now)

    def _start_show(self, video: dict, now: float) -> None:
        seconds = max(3.0, min(float(video.get("seconds") or 30), self.show_max))
        self.show = {"url": video["url"], "title": video["title"], "seconds": round(seconds, 1), "until": now + seconds,
                     "started": now}
        self.emit("show", url=video["url"], title=video["title"], seconds=round(seconds, 1))
        self.talk("show_start", title=video["title"], main=True)

    def stop_show(self) -> None:
        if not self.show:
            raise Refused("Đang không chiếu video.")
        self._end_show()

    def _end_show(self) -> None:
        self.show = None
        self.next_show = self.last_now + self.show_every
        self.emit("show_end")
        self.talk("show_end", main=True)

    def _advance_goal(self, v: Viewer, diamonds: int) -> None:
        """Thanh mục tiêu buổi: qua mốc nào thì cả phòng được cảnh vui đó; đủ 100 % thì chúc Tết + sang vòng mới."""
        goal = max(1, self.goal_xu)
        before, self.goal_have = self.goal_have, self.goal_have + diamonds
        for frac, fx, label in GOAL_STEPS:
            mark = goal * frac
            if before < mark <= self.goal_have:
                self.emit("goal_step", fx=fx, label=label, xu=round(mark), goal=goal, name=v.name, round=self.goal_round + 1)
                self.talk("goal_step", label=label.split(" ", 1)[1], xu=round(mark), name=v.name)
                if fx == "party" and v.gift_trip < 1000:  # quà ≥ 1000 xu tự có cảnh chúc Tết: không chiếu hai lần
                    self._queue_special("cả phòng")
        if self.goal_have >= goal:
            self.goal_have -= goal
            self.goal_round += 1

    def _goal_view(self) -> dict:
        goal = max(1, self.goal_xu)
        nxt = next(((round(goal * f), label) for f, _, label in GOAL_STEPS if goal * f > self.goal_have), (goal, GOAL_STEPS[-1][2]))
        return {"xu": self.goal_have, "goal": goal, "round": self.goal_round + 1, "next_xu": nxt[0], "next": nxt[1]}

    def money(self) -> dict:
        """Doanh thu cho /control: quà 1 giờ gần nhất, 10 phút gần nhất, người tặng, ước cả giờ theo nhịp hiện tại."""
        hour = [m for m in self.money_log if m[0] >= self.last_now - MONEY_WINDOW]
        ten = sum(x for t, x, _ in hour if t >= self.last_now - 600)
        by: dict[str, int] = {}
        for _, x, name in hour:
            by[name] = by.get(name, 0) + x
        span = min(MONEY_WINDOW, max(60.0, self.last_now - self.started_at))
        xu = sum(x for _, x, _ in hour)
        # ước cả giờ: chia cho ít nhất 10 phút — vài quà phút đầu không thành «750k / giờ»
        return {"hour_xu": xu, "ten_xu": ten, "gifts": len(hour), "gifters": len(by), "span_min": round(span / 60),
                "pace_xu": round(xu * MONEY_WINDOW / max(600.0, span)), "top": [{"name": n, "xu": x} for n, x in
                                                                 sorted(by.items(), key=lambda kv: -kv[1])[:5]]}

    def _fee(self, cap: int) -> int:
        """Phí / phạt: cố định `cap`, hoặc (fee_auto) theo lượng xu phòng hay tặng trong BLOCK_TARGET_MIN phút."""
        if not self.fee_auto:
            return max(1, cap)
        return max(1, min(cap, math.ceil(self._gift_rate() * BLOCK_TARGET_MIN)))

    def _gift_rate(self) -> float:
        """Xu / phút phòng tặng trong GIFT_RATE_WINDOW giây gần nhất (mỗi quà tính tối đa GIFT_RATE_CAP xu)."""
        xu = sum(min(x, GIFT_RATE_CAP) for t, x in self.gift_log if t >= self.last_now - GIFT_RATE_WINDOW)
        return xu / (GIFT_RATE_WINDOW / 60)

    def _block_tick(self, now: float) -> None:
        b = self.block
        # admin tắt tính năng giữa lúc đang bị chặn: xe đi luôn
        if not (self.incidents_on if "until" in b else self.blocks_on) and not b.get("manual"):
            self.block = None
            self.emit("block_end", block=b["kind"], by="off", name="", paid=b["paid"], goal=b["goal"])
            return
        if "until" in b:  # sự cố: tự xong khi hết giờ (tim rút ngắn), không nhắc góp quà / không bù lỗ
            if now >= b["until"]:
                self.block = None
                self.emit("block_end", block=b["kind"], by="time", name="", paid=b["paid"], goal=b["goal"])
                self.talk("incident_clear", what=WHAT[b["kind"]], main=True)
            return
        if self.cover_seconds > 0 and now - b["since"] >= self.cover_seconds:
            self.cover()
        elif now - self.last_block_remind >= BLOCK_REMIND_GAP:
            self.last_block_remind = now
            self.talk("block_remind", left=b["goal"] - b["paid"], what=WHAT[b["kind"]], main=True)

    def _pay_block(self, v: Viewer, diamonds: int) -> str:
        """Quà lúc xe đang bị chặn: góp vào phí / tiền phạt; đủ thì xe đi. Trả dòng cho thẻ quà (rỗng: không bị chặn)."""
        b = self.block
        if not b:
            return ""
        b["paid"] += diamonds
        b["givers"][v.name] = b["givers"].get(v.name, 0) + diamonds
        what = WHAT[b["kind"]]
        if b["paid"] < b["goal"]:
            return f"🚧 góp {diamonds} xu {what} · {b['paid']}/{b['goal']}"
        top = max(b["givers"].items(), key=lambda kv: kv[1])[0]
        self.block = None
        self.emit("block_end", block=b["kind"], by="gifts", name=top, paid=b["paid"], goal=b["goal"])
        self.talk("block_paid", name=top, what=what, main=True)
        return f"🚧 góp đủ {b['goal']} xu, xe đi tiếp"

    def cover(self) -> None:
        """«Anh Tư bù lỗ»: góp chưa đủ mà phòng ít quà → nhà xe trả phần thiếu, xe đi tiếp (admin bấm / tự sau N giây)."""
        b = self.block
        if not b:
            raise Refused("Xe đang không bị chặn.")
        self.block = None
        missing = b["goal"] - b["paid"]
        self.emit("block_end", block=b["kind"], by="cover", name="", paid=b["paid"], goal=b["goal"])
        self.talk("block_cover", missing=missing, what={"toll": "phí trạm", "police": "tiền phạt"}.get(b["kind"], "tiền thợ"),
                  main=True)

    def _block_view(self) -> dict | None:
        b = self.block
        if not b:
            return None
        top = sorted(b["givers"].items(), key=lambda kv: -kv[1])[:3]
        return {"kind": b["kind"], "reason": b["reason"], "goal": b["goal"], "paid": b["paid"], "place": b["place"],
                "speeding": b["speeding"], "top": [{"name": n, "xu": x} for n, x in top],
                "left": round(max(0.0, b["until"] - self.last_now)) if "until" in b else None,
                "total": round(b["until"] - b["since"]) if "until" in b else None,
                "waited": round(self.last_now - b["since"]), "cover_in": round(max(0.0, self.cover_seconds - (
                    self.last_now - b["since"]))) if self.cover_seconds > 0 and "until" not in b else None}

    def speed(self) -> float:
        base = (1.0 + self.boost) * self.trip_bonus
        return min(base * TURBO_MULT, max(base, TURBO_SPEED_CAP)) if self.turbo > 0 else base

    # ---- admin ---------------------------------------------------------

    def skip(self) -> None:
        if self.phase == "DRIVING":
            self.progress = 1.0
            self.block = None
            self.show = None
        self.phase_until = self.last_now

    def set_departure(self, key: str) -> None:
        """BR-8: chỉ đổi bến đi khi bến đang đón mà chưa ai lên xe và không ai giữ chỗ (tránh vé sai hướng)."""
        if not self.boarding_open() or self.bus.riders() or self.waiting() or self.reliefs:
            raise Refused("Chỉ đổi bến khi xe đang đón, chưa ai lên xe, không ai giữ chỗ và không còn xe tăng cường chạy.")
        self.network = self.network.switch(key)
        self.queues = {ln.key: [] for ln in self.network.lanes}
        self.queued_at = {}
        self.bus.lane = self.network.lanes[0].key
        self.talk("departure", station=self.network.departure.name, main=True)

    def extend(self, seconds: float) -> None:
        """Cộng / trừ thời gian pha đang chạy (đón khách, trạm dừng…); không áp cho lúc đang chạy đường.
        Đang chen cảnh chúc Tết thì cộng cho pha sẽ quay về, không kéo dài cảnh quà."""
        if self.phase == "SPECIAL":
            phase, left = self.resume
            if phase != "DRIVING":
                self.resume = (phase, max(1.0, left + seconds))
        elif self.phase != "DRIVING":
            self.phase_until = max(self.last_now + 1.0, self.phase_until + seconds)

    # ---- sự kiện từ TikTok / bảng điều khiển ---------------------------

    def handle(self, event: dict, now: float) -> bool:
        """Xử lý một sự kiện; False khi bị loại (thiếu người gửi) — app không cộng tim của sự kiện bị loại."""
        kind = event.get("type")
        name = str(event.get("name") or "").strip()[:32]
        uid = str(event.get("uid") or name.lower())
        if not uid:
            return False
        v = self.viewer(uid, name)
        if (url := avatar_url(event.get("avatar"))) and v.avatar != url:
            v.avatar = url
            self.avatars[v.name] = url
        if kind != "join" or v.province:  # vào phòng chưa tính là đang xem (người lướt qua); người có vé quay lại thì tính
            v.last_seen = now
            if v.roll_missed or v.uid in self.rollcalls:
                self._answer_roll(v)
            self._seen_today(v, now)
        if kind == "comment":
            v.comments += 1
            if v.stage_comments < STAGE_COMMENTS_MAX:
                v.stage_comments += 1
                v.stage += 1
            self._on_comment(v, str(event.get("text") or ""), now)
            if now - v.race_at >= RACE_COMMENT_GAP:
                v.race_at = now
                self._race(v, RACE_PER_COMMENT)
        elif kind == "like":
            count = max(1, min(LIKE_MAX, as_int(event.get("count"))))
            v.likes += count
            v.stage += count / STAGE_LIKES_PER_POINT
            self._on_like(v, count)
        elif kind == "gift":
            diamonds = max(1, as_int(event.get("diamonds")))
            v.gifts += diamonds
            v.stage += diamonds * STAGE_PER_XU
            self._on_gift(v, diamonds, str(event.get("gift") or "quà")[:24])
        elif kind == "follow":
            if not v.followed:  # follow / bỏ follow liên tục để được hiện tên → chỉ cảm ơn lần đầu
                v.followed = True
                self.emit("follow", name=v.name, hue=v.hue)
        elif kind == "share":
            if now - v.last_share >= SHARE_COOLDOWN:
                v.last_share = now
                prov = BY_KEY[v.province].name if v.province else None
                self.emit("share", name=v.name, province=prov)
        elif kind == "join":
            self.emit("join", name=v.name)
            self.joins_since_rules += 1
        return True

    def _on_comment(self, v: Viewer, text: str, now: float) -> None:
        if self.quiz and not self.quiz["done"] and (ans := answer_of(text)) is not None:
            self._quiz_answer(v, ans)  # đang đố: «A» / «câu B» là câu trả lời
            return
        if self.vendor and self.bus.seat_of(v.uid) is not None and (item := snack_of(text)):
            self._buy_snack(v, item)  # cô bán hàng đang trên xe: khách gõ «nem», «bánh mì»… là mua
            return
        cmd = parse(text, at_rest_stop=self.phase == "REST")
        if cmd.station:
            self._vote_station(v, cmd.station, now)
        if cmd.kind == "station":
            return
        if cmd.kind == "province":
            again = v.home_now and v.home is not None
            self._book(v, cmd.province.key)
            if again and (self.bus.seat_of(v.uid) is not None or self.lane_of_uid(v.uid)):
                v.home_now = False
                if now - self.last_back_talk >= BACK_TALK_GAP:
                    self.last_back_talk = now
                    self.talk("back_again", name=v.name, prov=BY_KEY[v.home].name)
        elif cmd.kind == "stay":
            self._stay(v)
        elif cmd.kind in ("fuel", "wash"):
            self._care(v, cmd.kind, now)
        elif cmd.kind == "where":
            self._show_ticket(v)
        elif cmd.kind == "board":
            self._board_intent(v, now)
        elif cmd.kind in ("food", "wc", "gift_shop"):
            if now - v.last_rest < REST_ACTION_COOLDOWN:
                return
            v.last_rest = now
            if cmd.kind == "food":
                self.rest_orders[cmd.item] += 1
                self._feed(v)  # ăn ở trạm dừng chân cũng no lại
                self.emit("rest_action", name=v.name, hue=v.hue, action="food",
                          item=cmd.item, emoji=FOOD_EMOJI[cmd.item])
            elif cmd.kind == "wc":
                if v.uid not in self.wc_line:
                    self.wc_line.append(v.uid)
                self.emit("rest_action", name=v.name, hue=v.hue, action="wc")
            else:
                self.emit("rest_action", name=v.name, hue=v.hue, action="shop")
        else:
            if faq(text) or is_question(text):
                self._question(v, text, now)
            elif self.ai_reply:
                self._chatter(v, text, now)
            seat = self.bus.seat_of(v.uid)
            if seat is None or now - v.last_chat < CHAT_COOLDOWN or not text.strip() or not allow_chat(text):
                return
            v.last_chat = now
            self.emit("chat", name=v.name, seat=seat, hue=v.hue, text=text.strip()[:40])

    def _show_ticket(self, v: Viewer) -> None:
        """Thẻ vé của người này (như gõ «xe nào»); WHERE_COOLDOWN giây một lần."""
        if v.last_seen - v.last_where >= WHERE_COOLDOWN:  # giờ của chính bình luận (nhịp game có thể chưa chạy tới)
            v.last_where = v.last_seen
            self.emit("where", name=v.name, hue=v.hue, **self.ticket_of(v))

    def _board_intent(self, v: Viewer, now: float) -> None:
        """«lên xe», «về quê», «cho đi với» mà không nói tỉnh (rà soát 02/11: trước đây im lặng). Có vé rồi → xem vé; khách
        quen biết quê → đặt vé về quê cũ; còn lại → lơ xe chỉ cách gõ tên tỉnh."""
        if v.province and not v.stay:
            self._show_ticket(v)
            return
        if v.home in BY_KEY and self.network.lane_of(v.home) is not None:
            self._book(v, v.home)
            if now - self.last_answer >= ASK_GAP:
                self.last_answer = now
                self.talk("board_home", name=v.name, prov=BY_KEY[v.home].name)
            return
        if now - v.last_ask >= ASK_PER_VIEWER and now - self.last_answer >= ASK_GAP:
            v.last_ask = now
            self.last_answer = now
            self.talk("board_hint", name=v.name)

    def _locked(self, v: Viewer) -> bool:
        """BOARD_LOCK giây cuối giờ đón: người đã ngồi không xuống / đổi tỉnh được nữa (lơ xe nhắc, 10 giây / câu)."""
        if self.bus.seat_of(v.uid) is None or not self.boarding_open():
            return False
        left = self.resume[1] if self.phase == "SPECIAL" else self.phase_until - self.last_now
        if left > BOARD_LOCK:
            return False
        if self.last_now - self.last_lock_talk >= 10:
            self.last_lock_talk = self.last_now
            self.talk("board_lock", name=v.name, main=True)
        else:
            self._show_ticket(v)  # lơ xe vừa nhắc người khác: người này vẫn thấy vé mình đang giữ
        return True

    def _book(self, v: Viewer, key: str) -> None:
        if self._locked(v):
            return
        v.stay = False
        if v.uid in self.staying:
            self.staying.remove(v.uid)
        if self.on_trip(v.uid):
            self._show_ticket(v)  # đang ngồi xe chạy: không đổi được — gõ lại tỉnh thì cho xem vé (rà soát 02/11)
            return
        lane = self.network.lane_of(key)
        if lane is None:  # BR-5: tỉnh của bến đi — đang giữ giường / chỗ chờ thì bỏ vé (đã ở quê, không đi đâu nữa)
            self._release(v)
            self._already_home(v, key)
            return
        seat = self.bus.seat_of(v.uid)
        queued = self.lane_of_uid(v.uid)
        changed = seat is not None or queued is not None
        if changed:
            if v.province == key or v.switched:  # gõ lại đúng tỉnh để xem mình lên chưa / đã đổi một lần: cho xem vé
                self._show_ticket(v)
                return
            v.switched = True
            if (self._fits(key) if seat is not None else lane == queued):  # xe vẫn chở được / cùng làn: giữ giường / chỗ chờ
                self.board[v.province] -= 1
                v.province = key
                self.board[key] += 1
                self._ticket(v, seat, changed=True)
                return
            self._release(v)  # sang làn khác: nhả giường (người chờ làn này lên thay) hoặc chỗ chờ cũ
        v.province = key
        self.board[key] += 1
        self._place(v, lane, changed)

    def _place(self, v: Viewer, lane: str, changed: bool) -> None:
        """BR-2: cùng làn xe đang đón + còn giường → lên ngay; khác làn / hết giường → giữ chỗ chuyến sau của làn đó."""
        if self.boarding_open() and not self.bus.riders() and not self._fits(v.province):
            self.bus.lane = lane  # BR-4: xe đang đón chưa có ai → quay đầu theo người đầu tiên
            self._fill_from_queue()
        if (self.boarding_open() and self._fits(v.province) and (free := self.bus.free_seat()) is not None
                and self.bus.seats.count(None) > self._held_seats()):  # giường đang giữ cho người được gọi tên: không lấy
            self.bus.seats[free] = v.uid
            self.seated_at.append(self.last_now)
            v.prio_credit = False  # có giường ngay: suất «lên đầu hàng» đã dùng cho lần đặt vé này
            self._ticket(v, free, changed)
            self._same_home(v)
            left = SEATS - len(self.bus.riders())
            if left == 0:
                hold = self._full_hold()
                if self.phase == "SPECIAL":
                    self.resume = ("BOARDING", min(self.resume[1], hold))
                else:
                    self.phase_until = min(self.phase_until, self.last_now + hold)
                self.talk("full", main=True)
            elif left == 5:
                self.talk("seats_left", n=left, main=True)
            elif left == 1:
                self.talk("last_seat", main=True)
        else:
            passed = self._roadside(v, changed)
            if passed is True:
                return
            self.queues[lane].append(v.uid)
            self.queued_at[v.uid] = v.last_seen
            if v.prio_credit:  # tặng quà lúc chưa có vé rồi mới gõ tỉnh: xếp đầu hàng MỘT lần (không phải cả buổi)
                v.prio_credit = False
                self._prioritize(v, lane)
            self._ticket(v, None, changed, passed=passed)

    def _care(self, v: Viewer, kind: str, now: float) -> None:
        """«đổ xăng» / «rửa xe» lúc xe đứng ở bến hoặc trạm dừng (đang chạy thì thôi): mỗi người CARE_COOLDOWN giây một lần."""
        if self._phase_now() not in ("BOARDING", "REST") or now - v.last_care < CARE_COOLDOWN:
            return
        v.last_care = now
        if kind == "fuel":
            self.fuel = min(1.0, self.fuel + FUEL_PER)
            level = self.fuel
        else:
            self.dirt = max(0.0, self.dirt - WASH_PER)
            level = 1 - self.dirt
        self.emit(kind, name=v.name, hue=v.hue, level=round(level, 2))
        if now - self.last_care_talk >= CARE_TALK_GAP:
            self.last_care_talk = now
            self.talk("fuel" if kind == "fuel" else "wash", name=v.name, n=round(level * 100), main=True)

    def _wear(self, km: float) -> None:
        """Xe chính chạy `km`: hết xăng + bẩn dần (mưa phùn miền Bắc / đèo bẩn nhanh hơn)."""
        if km <= 0 or self.trip is None:
            return
        self.fuel = max(0.0, self.fuel - km / FUEL_RANGE_KM)
        place, terrain = self._road_at(self.trip, self.trip_km())
        rate = (1.8 if BY_KEY[place].region == "bac" else 1.0) * (1.5 if terrain.get("pass") else 1.0)
        self.dirt = min(1.0, self.dirt + km * rate / DIRT_KM)

    def _vote_station(self, v: Viewer, key: str, now: float) -> None:
        """Gọi xe ra bến khác («từ Hà Nội», «bến Giáp Bát»): đủ STATION_VOTES người trong 15 phút thì lần tới bến hiện tại
        trống, xe ra bến đó (`_maybe_switch_station`)."""
        dep = self.network.departures.get(key)
        if dep is None or key not in self.network.data["departures"]:
            return
        if key == self.network.departure.key:
            self.station_votes.pop(v.uid, None)
            return
        self.station_votes[v.uid] = (key, now)
        votes = self._station_tally(now).get(key, 0)
        self.emit("station_vote", name=v.name, hue=v.hue, station=dep.name, votes=votes, need=STATION_VOTES)
        if now - self.last_station_talk >= STATION_TALK_GAP:
            self.last_station_talk = now
            self.talk("station_vote", name=v.name, station=dep.name, n=votes, need=STATION_VOTES)

    def _station_tally(self, now: float) -> Counter[str]:
        self.station_votes = {u: kv for u, kv in self.station_votes.items() if now - kv[1] <= STATION_VOTE_TTL}
        return Counter(key for key, _ in self.station_votes.values())

    def _maybe_switch_station(self, now: float) -> None:
        """Bến đang trống (chưa ai lên xe, không ai giữ chỗ, không xe tăng cường) + một bến đủ phiếu → xe ra bến đó."""
        if self.bus.riders() or self.waiting() or self.reliefs or not self.station_votes:
            return
        key, votes = max(self._station_tally(now).items(), key=lambda kv: kv[1], default=(None, 0))
        if key is None or votes < STATION_VOTES:
            return
        try:
            self.set_departure(key)
        except Refused:
            return
        self.station_votes = {u: kv for u, kv in self.station_votes.items() if kv[0] != key}
        self.emit("station_switch", station=self.network.departure.name, votes=votes)

    def station_view(self, now: float) -> list[dict]:
        """Bến đang được gọi (cho HUD / /control): tên, số phiếu / cần."""
        return [{"key": k, "name": self.network.departures[k].name, "votes": n, "need": STATION_VOTES}
                for k, n in self._station_tally(now).most_common(3)]

    def _roadside(self, v: Viewer, changed: bool) -> bool | str | None:
        """Bắt xe dọc đường (PLAN-136): xe chính đang trên đường mà quê người này còn ở phía trước, còn giường → đặt giường,
        hẹn ra điểm đón (chừng PICKUP_LEAD giây phía trước xe; xe đang nghỉ trạm / thả khách thì lên luôn ở đó), quê thành
        điểm trả nếu chưa có. True: đã đón / hẹn đón; tên tỉnh: xe đã qua / sắp qua quê họ → giữ chỗ xe sau; None: không
        liên quan (khác đường, hết giường, xe chưa chạy)."""
        phase = self._phase_now()
        if phase not in ("DRIVING", "REST", "DROPOFF") or self.trip is None:
            return None
        target = self._odo_of(v.province)
        if target is None:
            return None
        here = self.trip_km()
        name = BY_KEY[v.province].name
        if phase == "DRIVING":
            eta = self._eta_odo(target)
            if target <= here or eta is None or eta < PICKUP_LEAD + PICKUP_MARGIN:
                return name
            at = self._odo_at(PICKUP_LEAD)
            ahead = [a for _, a in self.pickups.values() if a > here]
            if ahead and (self._eta_odo(min(ahead)) or 0) >= PICKUP_LEAD * PICKUP_JOIN:
                at = min(ahead)  # đứng chung điểm đón sắp tới: xe dừng một lần cho cả nhóm
        else:
            if target <= here:
                return name
            at, eta = here, None
        free = self.bus.free_seat()
        if free is None:
            return None
        place = self.network.place_at(*self.trip.at(at))
        self._add_stop(v.province, target)
        self.bus.seats[free] = v.uid
        self.pickups[v.uid] = (place, at)
        wait = self._eta_odo(at) if phase == "DRIVING" else 0.0
        self._ticket(v, free, changed, pickup=BY_KEY[place].name, pickup_in=round(wait or 0))
        if phase == "DRIVING" and self.last_now - self.last_pickup_talk >= PICKUP_TALK_GAP:
            self.last_pickup_talk = self.last_now
            self.talk("pickup_wait", name=v.name, place=BY_KEY[place].name, main=True)
        if phase != "DRIVING":
            self._check_pickups()  # xe đang dừng ở trạm / đầu ngõ: lên luôn
        return True

    def _check_pickups(self) -> None:
        """Xe chính tới điểm đón: dừng hẳn bên lề (PLAN-145, anh 03/11 «tấp vào là dừng xe ở bên đường … xe tới dừng là lên»)
        — người hẹn ở điểm này lên lần lượt, lơ xe đọc tên; dừng PICKUP_STOP_BASE + PICKUP_STOP_STEP giây mỗi người."""
        here = self.trip_km()
        due = [(uid, place) for uid, (place, at) in self.pickups.items() if here + 1e-6 >= at]
        if not due:
            return
        people, place = [], due[0][1]
        for uid, _ in due:
            del self.pickups[uid]
            if self.bus.seat_of(uid) is None:  # đã bỏ vé / rời phòng trước khi xe tới
                continue
            v = self.viewers[uid]
            people.append({"name": v.name, "hue": v.hue, "province": BY_KEY[v.province].name if v.province else ""})
        if not people:
            return
        seconds = PICKUP_STOP_BASE + PICKUP_STOP_STEP * len(people)
        if self._phase_now() == "DRIVING":  # ở trạm / đầu ngõ xe vốn đang đứng: lên luôn, không cần dừng thêm
            self.halt = {"place": BY_KEY[place].name, "people": people, "until": self.last_now + seconds}
        self.emit("pickup_stop", place=BY_KEY[place].name, people=people, seconds=round(seconds, 1), bus_no=self.bus.no)
        names = ", ".join(p["name"] for p in people[:3]) + (f" và {len(people) - 3} người nữa" if len(people) > 3 else "")
        self.last_pickup_talk = self.last_now
        self.talk("pickup", name=names, place=BY_KEY[place].name, main=True)

    def _odo_of(self, province: str | None) -> float | None:
        """Odometer xe chính tới tỉnh này trên chuyến đang chạy: điểm trả chưa tới, hoặc tỉnh xe đi qua; None: ngoài đường."""
        if province is None or self.trip is None:
            return None
        for leg in self.legs[self.leg_index:]:
            if leg.kind == "stop" and leg.target == province:
                return leg.km
        return next((odo for k, odo in self.trip.via if k == province), None)

    def _drive_plan(self):
        """Các chặng còn lại tính từ vị trí xe (đang chạy): (km đầu, km cuối, giây bắt đầu chạy chặng, giây chạy chặng)."""
        kmps = self._kmps(self.trip.total)
        t = 0.0
        for i in range(self.leg_index, len(self.legs)):
            leg = self.legs[i]
            if i == self.leg_index:
                start, dur = self.trip_km(), (1 - self.progress) * self.leg_seconds
            else:
                start = self.legs[i - 1].km
                dur = max(LEG_SECONDS_MIN, (leg.km - start) / kmps)
            yield start, leg.km, t, dur
            t += dur + (self.rest_seconds if leg.kind == "rest" else DROPOFF_BASE + PAGE_SECONDS)

    def _eta_odo(self, odo: float) -> float | None:
        """Giây thật tới lúc xe chính (đang chạy) tới km `odo`; None: quá cuối chuyến."""
        for start, end, t0, dur in self._drive_plan():
            if odo <= end:
                return t0 + (dur * max(0.0, odo - start) / (end - start) if end > start else 0.0)
        return None

    def _odo_at(self, seconds: float) -> float:
        """Km xe chính (đang chạy) tới được sau `seconds` giây thật (đang dừng giữa hai chặng thì là điểm dừng đó)."""
        end = self.trip_km()
        for start, end, t0, dur in self._drive_plan():
            if seconds <= t0:
                return start
            if seconds <= t0 + dur:
                return start + (end - start) * (seconds - t0) / dur if dur > 0 else end
        return end

    def _add_stop(self, province: str, odo: float) -> None:
        """Thêm điểm trả ở tỉnh xe đi qua (chưa có ai xuống): chèn đúng chỗ theo km; nằm giữa chặng đang chạy thì tách chặng,
        giữ nguyên vị trí xe."""
        if any(leg.kind == "stop" and leg.target == province for leg in self.legs[self.leg_index:]):
            return
        i = next((j for j in range(self.leg_index, len(self.legs)) if self.legs[j].km > odo), len(self.legs))
        if i == self.leg_index and self._phase_now() == "DRIVING":
            here, start = self.trip_km(), self._leg_start_km()
            self.legs.insert(i, Leg("stop", province, odo))
            self.progress = (here - start) / (odo - start) if odo > start else 1.0
            self.leg_seconds = max(LEG_SECONDS_MIN, (odo - start) / self._kmps(self.trip.total))
        else:
            self.legs.insert(max(i, self.leg_index + 1), Leg("stop", province, odo))
        self.trip = replace(self.trip, via=tuple(x for x in self.trip.via if x[0] != province),
                            stops=tuple(sorted((*self.trip.stops, (province, odo)), key=lambda st: st[1])))

    def _ticket(self, v: Viewer, seat: int | None, changed: bool, **extra) -> None:
        # đang ngồi: làn của xe (khách Huế ngồi xe «Hướng Hà Nội»); giữ chỗ: làn của tỉnh mình
        lane = self.network.lane_by_key[self.bus.lane if seat is not None else self.network.lane_of(v.province)]
        km = self.network.km(v.province)
        info = {"name": v.name, "hue": v.hue, "province": BY_KEY[v.province].name, "seat": seat, "changed": changed,
                "trip_no": v.trips + 1,
                "lane": lane.label, "arrow": lane.arrow, "km": km, "departure": self.network.departure.short}
        if seat is not None:
            self.emit("ticket", **info, bus_no=self.bus.no, next=False, **extra)
            return
        bus_no, minutes = self._queue_eta(lane.key, self.queues[lane.key].index(v.uid))
        self.emit("ticket", **info, bus_no=bus_no, next=True, eta_min=minutes, **{k: x for k, x in extra.items() if x})
        if lane.key != self.bus.lane and not extra.get("passed"):  # khác hướng chuyến này: gom lại để lơ xe nhắc một câu
            self.other_dirs = [*(p for p in self.other_dirs if p != info["province"]), info["province"]][-5:]
        if extra.get("passed") and self.last_now - self.last_pickup_talk >= PICKUP_TALK_GAP:
            self.last_pickup_talk = self.last_now
            self.talk("passed", name=v.name, prov=extra["passed"], main=True)

    def _already_home(self, v: Viewer, key: str) -> None:
        """BR-5: comment đúng tỉnh của bến đi → không lên xe, vẫn được tính là đã về quê (một lần)."""
        if v.uid not in self.home_counted:
            self.home_counted.add(v.uid)
            self.board[key] += 1
        if self._noticed(v):
            name = BY_KEY[key].name
            self.emit("home", name=v.name, hue=v.hue, province=name)
            self.talk("home", name=v.name, prov=name)

    def _noticed(self, v: Viewer) -> bool:
        """Thẻ + lơ xe cho «không về» / «đã ở quê»: lặp lại trong NOTICE_COOLDOWN thì im (chống spam)."""
        if v.last_seen - v.last_notice < NOTICE_COOLDOWN:
            return False
        v.last_notice = v.last_seen
        return True

    def _stay(self, v: Viewer) -> None:
        if self.on_trip(v.uid) or self._locked(v):
            return
        self._release(v)
        if not v.stay:
            v.stay = True
            self.staying = [u for u in self.staying if u != v.uid][-(STAYING_KEEP - 1):] + [v.uid]
        if self._noticed(v):
            self.emit("stay", name=v.name, hue=v.hue, text=pick(STAY_MESSAGES, v.uid).format(name=v.name))

    def _on_like(self, v: Viewer, count: int) -> None:
        before = self.trip_likes
        self.trip_likes += count
        v.likes_trip += count
        self.boost = min(BOOST_MAX, self.boost + count * BOOST_PER_LIKE)
        b = self.block
        if b and "until" in b:  # sự cố: tim cả phòng giúp Anh Tư làm nhanh hơn
            floor = b["since"] + INCIDENT_SECONDS * (1 - INCIDENT_LIKE_MAX)
            b["until"] = max(floor, b["until"] - count * INCIDENT_LIKE_S)
        v.race_likes += count
        if v.race_likes >= RACE_LIKES_PER_POINT:
            self._race(v, v.race_likes // RACE_LIKES_PER_POINT)
            v.race_likes %= RACE_LIKES_PER_POINT
        for mark in LIKE_MILESTONES:
            if before < mark <= self.trip_likes:
                self.emit("like_milestone", total=mark)
                self.talk("likes", total=f"{mark:,}".replace(",", "."))
        self._invite(v)

    def _invite(self, v: Viewer) -> None:
        """Người thả tim đều mà chưa có vé (chưa gõ tỉnh, chưa chọn «không về», buổi này chưa về quê): lơ xe gọi tên mời
        một lần — người xem lặng lẽ thường chỉ cần được gọi tên là comment. Biết quê từ buổi trước thì mời đúng tỉnh."""
        if (v.invited or v.stay or v.home_now or v.province or v.likes_trip < INVITE_LIKES
                or self.last_now - self.last_invite < INVITE_GAP):
            return
        v.invited = True
        self.last_invite = self.last_now
        if v.home in BY_KEY:
            self.talk("invite_home", name=v.name, prov=BY_KEY[v.home].name)
        else:
            self.talk("invite", name=v.name)

    def _watch_place(self, now: float) -> None:
        """Xe chính vào địa phận tỉnh không ai xuống (PLAN-134): lơ xe gọi bà con tỉnh đó — quê họ cũng là một phần chuyến
        đi. Mỗi VIA_TALK_GAP giây tối đa một lần."""
        self._settle_place()
        place = self._where()[0]
        if place == self.place_now:
            return
        self.place_now = place
        self._roll_weather(BY_KEY[place].region, now)
        if now - self.last_via_talk >= VIA_TALK_GAP and any(k == place for k, _ in self.trip.via):
            self.last_via_talk = now
            name = BY_KEY[place].name
            self.emit("via", province=name, bus_no=self.bus.no)
            self.talk("via", place=name, main=True)
        elif now - self.last_fact >= FACT_GAP and (said := fact(place)):
            self.last_fact = now  # lơ xe kể chuyện tỉnh đang đi qua (đặc sản / thắng cảnh)
            self.talk("fact", fact=said, main=True)

    def _remind_rules(self, now: float) -> None:
        """Lơ xe đọc luật chơi: đủ RULES_GAP giây, hoặc ≥ RULES_JOINS người mới vào và đã qua RULES_MIN_GAP."""
        since = now - self.last_rules
        if since >= RULES_GAP or (self.joins_since_rules >= RULES_JOINS and since >= RULES_MIN_GAP):
            self.last_rules = now
            self.joins_since_rules = 0
            self.talk("rules")

    def _watch_relief(self, relief: Relief) -> None:
        """Xe tăng cường đang lên màn hình vào tỉnh nó chỉ đi qua: lơ xe gọi bà con tỉnh đó (như xe chính)."""
        place = self._road_at(relief.trip, relief.odo)[0]
        if place == relief.place_now:
            return
        relief.place_now = place
        if self.last_now - self.last_via_talk >= VIA_TALK_GAP and any(k == place for k, _ in relief.trip.via):
            self.last_via_talk = self.last_now
            name = BY_KEY[place].name
            self.emit("via", province=name, bus_no=relief.no)
            self.talk("via", place=name)

    def _introduce(self, no: int | None) -> None:
        """Màn hình vừa chuyển xe: lơ xe nói xe nào đang lên sóng, đi đâu, chở bao nhiêu, điểm kế."""
        if no is None:
            self.talk("screen_main", no=self.bus.no, dest=self._dest(self.bus.lane), n=len(self.bus.riders()))
            return
        relief = next((r for r in self.reliefs if r.no == no), None)
        if relief is None or relief.done >= len(relief.trip.stops):
            return
        nxt, odo = relief.trip.stops[relief.done]
        self.talk("screen_relief", no=relief.no, dest=self._dest(relief.lane), n=len(relief.riders),
                  next=BY_KEY[nxt].name, km=f"{max(1, round(odo - relief.odo)):,}".replace(",", "."))

    def manifest(self) -> dict:
        """Ai đang ở xe nào / chờ làn nào (rà soát 02/11: anh không biết người xem nào ở xe nào) — cho /control, gọi khi cần."""
        def person(uid: str, **extra) -> dict:
            v = self.viewers[uid]
            return {"name": v.name, "province": BY_KEY[v.province].name if v.province else "", **extra}
        lane = self.network.lane_by_key[self.bus.lane]
        buses = [{"no": self.bus.no, "main": True, "label": lane.label, "arrow": lane.arrow, "phase": self._phase_now(),
                  "featured": self.featured is None,
                  "riders": [person(uid, seat=i + 1) for i, uid in enumerate(self.bus.seats) if uid]}]
        for r in self.reliefs:
            ln = self.network.lane_by_key[r.lane]
            buses.append({"no": r.no, "main": False, "label": ln.label, "arrow": ln.arrow, "phase": "DRIVING",
                          "featured": self.featured == r.no, "sponsor": r.sponsor,
                          "riders": [person(uid) for uid in r.riders]})
        queues = [{"label": self.network.lane_by_key[k].label, "arrow": self.network.lane_by_key[k].arrow,
                   "people": [person(uid, pos=i + 1) for i, uid in enumerate(q)]} for k, q in self.queues.items() if q]
        return {"buses": buses, "queues": queues}

    def ticket_of(self, v: Viewer) -> dict:
        """Vé của một người xem lúc này, trả lời khi họ hỏi «xe nào / tới đâu rồi» (PLAN-134 B): xe số mấy, giường, còn mấy
        điểm nữa tới quê và bao lâu (giây thật); đang giữ chỗ thì thứ mấy, xe số mấy, bao nhiêu phút."""
        if v.province is None:
            return {"status": "home" if v.trips else "none"}
        province = BY_KEY[v.province].name
        seat = self.bus.seat_of(v.uid)
        if seat is not None:
            phase = self._phase_now()
            out = {"status": "seat", "bus_no": self.bus.no, "seat": seat, "province": province, "phase": phase}
            if phase in ("BOARDING", "FINISH"):
                out["depart_in"] = round(max(0.0, self.phase_until - self.last_now)) if phase == "BOARDING" else None
                return out
            if v.uid in self.pickups:  # hẹn bắt xe dọc đường: đang chờ ở điểm đón
                place, at = self.pickups[v.uid]
                out["pickup"] = BY_KEY[place].name
                out["pickup_in"] = round(self._eta_odo(at) or 0) if phase == "DRIVING" else 0
            arrivals = self._arrivals()[0]
            idx = next((i for i, leg in enumerate(self.legs) if leg.kind == "stop" and leg.target == v.province), None)
            if idx is not None and arrivals[idx] is not None:
                out["in_s"] = round(arrivals[idx])
                out["stops_before"] = sum(1 for leg in self.legs[self.leg_index:idx] if leg.kind == "stop")
            return out
        relief = next((r for r in self.reliefs if v.uid in r.riders), None)
        if relief is not None:
            idx = next((i for i, (k, _) in enumerate(relief.trip.stops) if k == v.province), relief.done)
            left = self._relief_arrivals(relief)[idx] if idx < len(relief.trip.stops) else None
            return {"status": "relief", "bus_no": relief.no, "province": province,
                    "in_s": None if left is None else round(left), "stops_before": max(0, idx - relief.done)}
        lane = self.lane_of_uid(v.uid)
        if lane is not None:
            position = self.queues[lane].index(v.uid)
            bus_no, minutes = self._queue_eta(lane, position)
            ln = self.network.lane_by_key[lane]
            return {"status": "queue", "bus_no": bus_no, "province": province, "position": position + 1,
                    "eta_min": minutes, "lane": ln.label, "arrow": ln.arrow}
        return {"status": "none", "province": province}

    def _queue_eta(self, lane: str, position: int) -> tuple[int, int]:
        """(số xe, số phút tới lúc được lên xe) cho người thứ `position` trong hàng chờ làn `lane`.

        Chuyến hiện tại phải xong trước; mỗi làn có người chờ lâu hơn người đầu hàng làn này thì đi trước một chuyến
        (BR-4 ai chờ trước đi trước).
        """
        if not self.race_on:  # cùng thứ tự với chuyến thật sẽ chạy (quà trước, đặt sớm trước, anh chọn trên /control trước)
            order = [u["lane"] for u in self.upcoming()]
            older = order.index(lane) if lane in order else len(order)
        else:
            queue = self.queues[lane]
            mine = self.queued_at.get(queue[0], self.last_now) if queue else self.last_now
            older = sum(1 for key, q in self.queues.items()
                        if key != lane and q and self.queued_at.get(q[0], self.last_now) < mine)
        trips = 1 + position // SEATS + older
        return self.bus.no + trips, self._eta_minutes(trips)

    def _eta_minutes(self, trips_ahead: int) -> int:
        """Phút tới khi xe thứ `trips_ahead` tính từ xe hiện tại vào bến đón (người chờ được xếp lên xe ngay lúc đó).
        Không trừ hao tim: hứa ít, tới sớm hơn thì người xem vui hơn."""
        phase = self._phase_now()
        special = max(0.0, self.phase_until - self.last_now) if self.phase == "SPECIAL" else 0.0
        phase_left = self.resume[1] if self.phase == "SPECIAL" else max(0.0, self.phase_until - self.last_now)
        if phase == "BOARDING":
            left = special + phase_left + self.run_avg
        elif phase == "FINISH":
            left = phase_left
        else:
            left = self._arrivals()[1] + FINISH_SECONDS
        left += max(0, trips_ahead - 1) * (self.board_avg + self.run_avg)
        return max(1, math.ceil(left / 60))

    def _arrivals(self) -> tuple[list[float | None], float]:
        """Giây thật tới lúc xe chính tới từng điểm dừng (None: đã qua; 0: đang dừng ở đó) + giây tới lúc xong điểm cuối.
        Không tính đèo / hầm chậm lại và tim đẩy nhanh — sai số vài giây, đủ cho bảng chặng."""
        out: list[float | None] = [None] * len(self.legs)
        phase = self._phase_now()
        if not self.trip or phase not in ("DRIVING", "REST", "DROPOFF"):
            return out, 0.0
        t = max(0.0, self.phase_until - self.last_now) if self.phase == "SPECIAL" else 0.0
        phase_left = self.resume[1] if self.phase == "SPECIAL" else max(0.0, self.phase_until - self.last_now)
        kmps = self._kmps(self.trip.total)
        for i in range(self.leg_index, len(self.legs)):
            leg, current = self.legs[i], i == self.leg_index
            if not current or phase == "DRIVING":
                leg_km = leg.km - (self.legs[i - 1].km if i > 0 else 0.0)
                t += ((1 - self.progress) if current else 1.0) * max(LEG_SECONDS_MIN, leg_km / kmps)
            out[i] = t
            if current and phase in ("REST", "DROPOFF"):
                t += phase_left
            elif leg.kind == "rest":
                t += RUSH_REST_SECONDS if self.rush() else self.rest_seconds
            else:
                t += DROPOFF_BASE + PAGE_SECONDS
        return out, t

    @staticmethod
    def _relief_arrivals(relief: Relief) -> list[float | None]:
        return [None if i < relief.done else max(0.0, odo - relief.odo) / relief.kmps
                for i, (_, odo) in enumerate(relief.trip.stops)]

    # ---- đồng hồ trên xe ---------------------------------------------------

    def _main_hours(self) -> float:
        """Số giờ (đồng hồ trên xe) xe chính đã đi: km / BUS_KMH + REST_HOURS mỗi trạm đã ghé (đang nghỉ thì tính dần)."""
        if self.clock0 is None or not self.legs:
            return 0.0
        rests = sum(1 for leg in self.legs[:self.leg_index] if leg.kind == "rest")
        if self.leg_index >= len(self.legs):  # về bến
            return Network.hours(self.trip.total) + REST_HOURS * rests
        if self._phase_now() == "REST":
            left = self.resume[1] if self.phase == "SPECIAL" else max(0.0, self.phase_until - self.last_now)
            rests += 1 - min(1.0, left / max(1.0, RUSH_REST_SECONDS if self.rush() else self.rest_seconds))
        return Network.hours(self.trip_km()) + REST_HOURS * rests

    @staticmethod
    def _clock(clock0: datetime, hours: float) -> dict:
        """Đồng hồ trên xe: giờ trong ngày (trời sáng / tối theo giờ này), «HH:MM», ngày thứ mấy kể từ hôm xuất bến."""
        at = clock0 + timedelta(hours=hours)  # «HH:MM» ghép tay: strftime gọi ~1 triệu lần / 30 phút phòng đông (đo 02/11)
        return {"hour": round(at.hour + at.minute / 60, 3), "time": f"{at.hour:02d}:{at.minute:02d}",
                "day": (at.date() - clock0.date()).days}

    def _route_view(self, stops: list[tuple[str, str, float]], arrivals: list[float | None], clock0: datetime | None,
                    hours_before: list[float]) -> list[dict]:
        """Các điểm dừng cho bảng chặng: (loại, tên, km) + giờ tới theo đồng hồ xe + còn bao nhiêu giây thật."""
        out = []
        for (kind, name, km), left, hours in zip(stops, arrivals, hours_before):
            clock = self._clock(clock0, hours) if clock0 else None
            out.append({"kind": kind, "name": name, "km": round(km), "done": left is None,
                        "in_s": None if left is None else round(left), "at": clock and clock["time"],
                        "day": clock and clock["day"]})
        return out

    def _main_route(self) -> dict:
        """Bảng chặng xe chính — snapshot cần hai lần (thẻ tuyến + bảng đội xe): dựng một lần mỗi snapshot."""
        if self._route_memo is not None and self._route_memo[0] == self._snap_no:
            return self._route_memo[1]
        route = self._build_main_route()
        self._route_memo = (self._snap_no, route)
        return route

    def _build_main_route(self) -> dict:
        legs = self.legs
        stops = [(leg.kind, f"Trạm {BY_KEY[leg.target].name}" if leg.kind == "rest" else BY_KEY[leg.target].name, leg.km)
                 for leg in legs]
        hours, rests = [], 0
        for leg in legs:
            hours.append(Network.hours(leg.km) + REST_HOURS * rests)
            rests += leg.kind == "rest"
        clock = self._clock(self.clock0, self._main_hours()) if self.clock0 and legs else self._clock(datetime.now(VN), 0)
        return {"stops": self._route_view(stops, self._arrivals()[0], self.clock0 if legs else None, hours),
                "via": self._via_view(self.trip, self.trip_km()),
                "odo": round(self.trip_km(), 1), "total": round(self.trip.total) if self.trip else 0, "clock": clock}

    @staticmethod
    def _stops_of(route: dict) -> dict:
        return {"stops": route["stops"], "via": route["via"]}

    @staticmethod
    def _via_view(trip: Trip | None, odo: float) -> list[dict]:
        """Tỉnh xe đi qua mà không ai xuống (PLAN-134): vẫn hiện trên bảng chặng — xe chạy qua địa phận quê họ."""
        return [{"name": BY_KEY[k].name, "km": round(at), "done": at <= odo} for k, at in trip.via] if trip else []

    def _relief_route(self, relief: Relief) -> dict:
        stops = [("stop", BY_KEY[key].name, odo) for key, odo in relief.trip.stops]
        return {"stops": self._route_view(stops, self._relief_arrivals(relief), relief.clock0,
                                          [Network.hours(odo) for _, _, odo in stops]),
                "via": self._via_view(relief.trip, relief.odo),
                "odo": round(relief.odo, 1), "total": round(relief.trip.total),
                "clock": self._clock(relief.clock0, Network.hours(relief.odo))}

    def _fleet(self) -> list[dict]:
        """Mọi xe đang chạy cho bảng chặng (/control + overlay): đang ở đâu, điểm kế, còn bao lâu, đồng hồ trên xe."""
        lane = self.network.lane_by_key[self.bus.lane]
        phase = self._phase_now()
        arrivals = self._arrivals()[0]
        nxt = next((i for i, t in enumerate(arrivals) if t is not None), None)
        main = {"no": self.bus.no, "main": True, "featured": self.featured is None, "arrow": lane.arrow,
                "label": lane.label, "phase": phase, "riders": len(self.bus.riders()),
                "left_km": round(self.trip.total - self.trip_km()) if self.trip else None,
                "next": None, "in_s": None, "clock": None, **self._stops_of(self._main_route())}
        if nxt is not None:
            leg = self.legs[nxt]
            main.update(next=f"Trạm {BY_KEY[leg.target].name}" if leg.kind == "rest" else BY_KEY[leg.target].name,
                        in_s=round(arrivals[nxt]), clock=self._clock(self.clock0, self._main_hours()))
        elif phase in ("BOARDING", "FINISH"):
            main["in_s"] = round(max(0.0, self.phase_until - self.last_now))
        out = [main]
        for r in self.reliefs:
            ln = self.network.lane_by_key[r.lane]
            idx = min(r.done, len(r.trip.stops) - 1)
            out.append({"no": r.no, "main": False, "featured": r.no == self.featured, "arrow": ln.arrow,
                        "label": ln.label, "phase": "DRIVING", "riders": len(r.riders),
                        "left_km": round(r.trip.total - r.odo), "next": BY_KEY[r.trip.stops[idx][0]].name,
                        "in_s": round(self._relief_arrivals(r)[idx] or 0),
                        "clock": self._clock(r.clock0, Network.hours(r.odo)), "sponsor": r.sponsor,
                        **self._stops_of(self._relief_route(r))})
        return out

    def _on_gift(self, v: Viewer, diamonds: int, gift: str) -> None:
        # Cộng dồn trong chuyến: 10 hoa hồng = 10 xu → lên bậc pháo hoa (REVIEW BA-9)
        before = v.gift_trip
        v.gift_trip += diamonds
        total = v.gift_trip
        tier = next(t for floor, t in GIFT_TIERS if total >= floor)
        tier_before = next((t for floor, t in GIFT_TIERS if before >= floor), 0)
        queued = self.lane_of_uid(v.uid)
        relief = None  # PLAN-144 (anh 03/11): bỏ xe tăng cường; chỉ một xe 24 chỗ — quà không gọi xe nào khác
        ticketed = self.bus.seat_of(v.uid) is not None or queued is not None
        v.gift_session += diamonds
        self.gift_log = [(t, x) for t, x in self.gift_log if t >= self.last_now - GIFT_RATE_WINDOW] + [(self.last_now, diamonds)]
        self.money_log = [m for m in self.money_log if m[0] >= self.last_now - MONEY_WINDOW] + [(self.last_now, diamonds, v.name)]
        self._advance_goal(v, diamonds)
        self._race(v, diamonds * RACE_PER_XU)
        paid = self._pay_block(v, diamonds) or self._pay_vendor(v, diamonds)
        added = min(TURBO_MAX, self.turbo + diamonds * TURBO_PER_XU) - self.turbo
        self.turbo += added
        self.turbo_by = v.name
        if not ticketed:
            v.prio_credit = True
        moved = None
        if queued and not v.priority:
            moved = self._prioritize(v, queued)
        self._update_patrons()
        if tier >= 1:
            v.vip = True
        if tier >= 2:
            v.fireworks = True
        if tier >= 3 and relief is None:  # có xe tăng cường thì tên đã nằm trên xe đó, không dán lên xe chính
            if self.phase == "FINISH":
                self.next_banner = v.name  # xe này sắp về bến, dán cho xe sau để quà không mất
            else:
                self.bus.banner = v.name
        if tier >= 4:
            # mỗi lần vượt thêm một mốc 1000 xu = thêm một lần cả xe chúc Tết (tối đa 3 lần / lần tặng)
            for _ in range(min(SPECIALS_PER_GIFT, total // 1000 - before // 1000)):
                self._queue_special(v.name)
        # quà Tết lên gầm xe: người có vé (đang ngồi / giữ chỗ / xe tăng cường) tặng quà → thêm một thùng mang tên mình
        parcel = (ticketed or any(v.uid in r.riders for r in self.reliefs)) and v.parcels < PARCELS_MAX
        v.parcels += int(parcel)
        fx, fx_n = gift_fx(gift, diamonds)
        perk = GIFT_LABELS[tier][0 if ticketed else 1]
        if moved:
            ln = self.network.lane_by_key[queued]
            perk = f"⚡ lên đầu hàng chờ {ln.arrow} {ln.label} · thứ {moved}"
            if self.last_now - self.last_priority_talk >= PRIORITY_TALK_GAP:
                self.last_priority_talk = self.last_now
                self.talk("priority", name=v.name, dest=self._dest(queued), pos=moved)
        if added >= 1:
            perk = f"🚀 xe chạy x2 thêm {round(added)} giây · " + perk
        if paid:
            perk = paid + " · " + perk
            if not moved and self.last_now - self.last_turbo_talk >= TURBO_TALK_GAP:
                self.last_turbo_talk = self.last_now
                self.talk("turbo", name=v.name, secs=round(self.turbo))
        self.emit("gift", name=v.name, hue=v.hue, tier=tier, tier_up=tier > tier_before, gift=gift,
                  diamonds=diamonds, total=total, perk=perk, next_tier=self._next_tier_hint(total),
                  parcel=parcel, parcels=v.parcels, fx=fx, fx_n=fx_n)
        if self.phase == "REST" and v.uid not in self.treated:  # combo 30 hoa hồng chỉ «bao cả xe» một lần
            self.treated.add(v.uid)
            self.emit("treat", name=v.name)
            self.talk("treat", name=v.name)

    @staticmethod
    def _next_tier_hint(total: int, queued: bool = False) -> str:
        """«Tặng thêm 6 xu → pháo hoa…»: mục tiêu gần trước mắt thì người ta tặng tiếp. Đã tới bậc cao nhất (1000 xu) thì
        thôi gợi ý: không mở vòng «thêm N xu → chúc Tết lần nữa» không đáy cho người đã tặng nhiều."""
        if total >= 1000:
            return ""
        floor, tier = min(((f, t) for f, t in GIFT_TIERS if f > total), key=lambda ft: ft[0])
        return f"thêm {floor - total} xu → {GIFT_LABELS[tier][0]}"

    # ---- trạng thái cho overlay ----------------------------------------

    def _where(self) -> tuple[str, dict]:
        """Tỉnh xe chính đang ở / đi qua + hồ sơ đường tại đó cho overlay uốn đường và đổi cảnh."""
        leg = self.current_leg()
        if leg is None or self.trip is None:
            return self.network.departure.province, dict(FLAT)  # ở bến / về bến: cảnh của bến đi
        if self._phase_now() != "DRIVING":
            return leg.target, dict(FLAT)
        place, terrain = self._road_at(self.trip, self.trip_km())
        if leg.kind == "stop" and leg.km - self.trip_km() <= ARRIVE_SHOW_KM:
            return leg.target, terrain  # sắp tới điểm thả khách: ghi đúng tỉnh đó (tỉnh lỵ sát ranh như TP.HCM — Đồng Nai)
        return self.place_shown or place, terrain

    def _settle_place(self) -> None:
        """Tên tỉnh trên màn đổi khi tỉnh mới đã giữ PLACE_HOLD_KM km (gọi mỗi nhịp lúc xe chạy)."""
        odo = self.trip_km()
        raw = self._road_at(self.trip, odo)[0]
        leg = self.current_leg()
        if leg and leg.kind == "stop" and leg.km - odo <= ARRIVE_SHOW_KM:
            raw = self.place_shown = leg.target  # sắp tới điểm thả: đổi ngay (khớp `_where`), rời đi thì giữ tên này
            self.place_cand = None
        if raw == self.place_shown or self.place_shown is None:
            self.place_shown, self.place_cand = raw, None
        elif self.place_cand is None or self.place_cand[0] != raw:
            self.place_cand = (raw, odo)
        elif odo - self.place_cand[1] >= PLACE_HOLD_KM:
            self.place_shown, self.place_cand = raw, None

    def _road_at(self, trip: Trip, odo: float) -> tuple[str, dict]:
        """Tỉnh đang đi qua + độ quanh co, đèo / hầm, chiều dốc ở km `odo` của chuyến `trip`."""
        net = self.network
        route, km = trip.at(odo)
        found = net.pass_at(route, km)
        climb = 0  # đèo: +1 đang leo (chưa tới đỉnh theo chiều xe chạy), −1 đang đổ dốc; hầm / đường thường: 0
        if found and not found.tunnel:
            climb = 1 if (found.km - km) * trip.direction(odo) > 0 else -1
        terrain = {"wind": net.wind_at(route, km), "pass": found.name if found else None,
                   "tunnel": bool(found and found.tunnel), "climb": climb}
        return net.place_at(route, km), terrain

    def _queue_view(self) -> tuple[dict | None, list[dict]]:
        """Làn chạy kế tiếp + người đang chờ (làn đó trước) — người chờ luôn thấy tên mình và thứ tự trên màn hình."""
        if not self.waiting():
            return None, []
        net, nxt = self.network, self._pick_lane(consume=False)
        order = sorted(net.lanes, key=lambda ln: (ln.key != nxt, -len(self.queues[ln.key])))
        people = []
        for ln in order:
            for pos, uid in enumerate(self.queues[ln.key][:QUEUE_SHOW - len(people)]):
                v = self.viewers[uid]
                people.append({"name": v.name, "hue": v.hue, "province": BY_KEY[v.province].name,
                               "arrow": ln.arrow, "pos": pos + 1})
        lane = net.lane_by_key[nxt]
        bus_no, minutes = self._queue_eta(nxt, 0)
        return {"label": lane.label, "arrow": lane.arrow, "bus_no": bus_no, "eta_min": minutes}, people

    def _relief_view(self, relief: Relief) -> dict:
        ln = self.network.lane_by_key[relief.lane]
        nxt = relief.trip.stops[min(relief.done, len(relief.trip.stops) - 1)][0]
        return {"no": relief.no, "arrow": ln.arrow, "label": ln.label, "sponsor": relief.sponsor,
                "riders": len(relief.riders), "next": BY_KEY[nxt].name, "featured": relief.no == self.featured,
                "left_km": round(relief.trip.total - relief.odo), "music": self._music_view(str(relief.no))}

    def _seats_view(self, uids: list[str | None]) -> list[dict | None]:
        out = []
        for uid in uids:
            v = self.viewers.get(uid) if uid else None
            out.append({"name": v.name, "hue": v.hue, "vip": v.vip, "snack": SNACKS[v.snack][1] if v.snack else "",
                        "full": math.floor(v.full),  # làm tròn xuống: 29,9% là «sắp đói» (dưới 30)
                        "avatar": v.avatar,
                        "province": BY_KEY[v.province].name if v.province else ""} if v else None)
        return out

    def _relief_screen(self, relief: Relief) -> dict:
        """Phần trạng thái màn hình khi admin chiếu xe tăng cường: overlay vẽ xe đó y như xe chính đang chạy."""
        stops = relief.trip.stops
        idx = min(relief.done, len(stops) - 1)
        start = stops[idx - 1][1] if idx > 0 else 0.0
        place, terrain = self._road_at(relief.trip, relief.odo)
        ln = self.network.lane_by_key[relief.lane]
        region = BY_KEY[place].region
        riders = relief.riders + [None] * (SEATS - len(relief.riders))
        return {
            "phase": "DRIVING", "phase_left": None, "phase_total": None,
            "bus": {"no": relief.no, "seats": self._seats_view(riders), "banner": relief.sponsor,
                    "riders": len(relief.riders), "lane": ln.label, "arrow": ln.arrow, "to": BY_KEY[ln.to].name,
                    "km": round(relief.trip.total)},
            "legs": [{"kind": "stop", "km": round(odo), "label": BY_KEY[key].name} for key, odo in stops],
            "leg_index": idx, "progress": round((relief.odo - start) / max(1e-6, stops[idx][1] - start), 4),
            "trip_km": round(relief.odo, 1), "terrain": terrain, "region": region, "place": BY_KEY[place].name,
            "specialty": specialty_of(place), "rush": False, "route": self._relief_route(relief),
        }

    def snapshot(self) -> dict:
        self._snap_no += 1
        place, terrain = self._where()
        region = BY_KEY[place].region
        seats = self._seats_view(self.bus.seats)
        net = self.network
        legs = [{"kind": item.kind, "km": round(item.km),
                 "label": f"Trạm {BY_KEY[item.target].name}" if item.kind == "rest" else BY_KEY[item.target].name}
                for item in self.legs]
        bus_lane = net.lane_by_key[self.bus.lane]
        next_lane, queue = self._queue_view()
        today = self._today()
        state = {
            "phase": self.phase,
            "paused": self.paused,
            "phase_left": max(0.0, self.phase_until - self.last_now) if self.phase != "DRIVING" else None,
            "phase_total": max(0.0, self.phase_until - self.phase_started) if self.phase != "DRIVING" else None,
            "bus": {"no": self.bus.no, "seats": seats, "banner": self.bus.banner,
                    "parcels": sum(self.viewers[u].parcels for u in self.bus.riders()),
                    "riders": len(self.bus.riders()), "lane": bus_lane.label, "arrow": bus_lane.arrow,
                    "to": BY_KEY[bus_lane.to].name,
                    "km": round(self.trip.total) if self.trip else None},
            "departure": {"key": net.departure.key, "name": net.departure.name, "short": net.departure.short},
            "lanes": [{"key": ln.key, "label": ln.label, "arrow": ln.arrow, "waiting": len(self.queues[ln.key]),
                       "current": ln.key == self.bus.lane} for ln in net.lanes],
            "waiting": self.waiting(),
            "reliefs": [self._relief_view(r) for r in self.reliefs],
            "next_lane": next_lane,
            "queue": queue,
            "legs": legs,
            "trip_km": round(self.trip_km(), 1),
            "terrain": terrain,
            "leg_index": self.leg_index,
            "progress": round(self.progress, 4),
            "speed": 0.0 if self.halt or self.block or self.show else round(self.speed(), 3),
            "show": {"url": self.show["url"], "title": self.show["title"], "seconds": self.show["seconds"],
                     "left": round(max(0.0, self.show["until"] - self.last_now), 1)} if self.show else None,
            "race": [{"province": BY_KEY[k].name, "points": p} for k, p in self.race.most_common(5) if p > 0],
            "upcoming": self.upcoming(),
            "focus": self._focus_view(),
            "block": self._block_view(),
            "goal": self._goal_view(),
            "turbo": {"left": round(self.turbo), "by": self.turbo_by} if self.turbo > 0 else None,
            "vendor": self._vendor_view(),
            "quiz": self._quiz_view(),
            "weather": self.weather,
            "name_hold": self.phase == "BOARDING" and self.name_hold_from is not None,
            "rollcall": [{"name": self.viewers[u].name, "left": round(max(0.0, t - self.last_now))}
                         for u, t in self.rollcalls.items()][:5],
            "halt": {"place": self.halt["place"], "people": self.halt["people"],
                     "left": round(max(0.0, self.halt["until"] - self.last_now), 1)} if self.halt else None,
            "leg_seconds": self.leg_seconds,
            "region": region,
            "place": BY_KEY[place].name,
            "specialty": specialty_of(place),
            "rest": {"orders": [{"item": k, "emoji": FOOD_EMOJI[k], "count": c}
                                for k, c in self.rest_orders.most_common(REST_ORDERS_SHOW)],
                     "wc_count": len(self.wc_line)},
            "staying": [self.viewers[u].name for u in self.staying[-STAYING_SHOW:]],
            "staying_count": len(self.staying),
            "board": self._board_top(),
            "trip_likes": self.trip_likes,
            "patrons": [{"name": self.viewers[u].name, "xu": self.viewers[u].gift_session} for u in self.patrons],
            "delivered": self.delivered,
            "days_to_tet": max(0, (season.TET_DAY - today).days),
            "season": season.view(today),
            "care": {"fuel": round(self.fuel, 2), "dirt": round(self.dirt, 2), "bonus": round(self.trip_bonus, 2)},
            "stations": self.station_view(self.last_now),  # bến người xem đang gọi (PLAN-136)
            "rush": self.rush(),
            # xe chính cho trang admin (khi màn hình đang chiếu xe tăng cường thì các trường trên là của xe đó)
            "main": {"no": self.bus.no, "phase": self.phase, "riders": len(self.bus.riders()), "lane": bus_lane.label,
                     "arrow": bus_lane.arrow, "phase_left": max(0.0, self.phase_until - self.last_now)
                     if self.phase != "DRIVING" else None, "trip_km": round(self.trip_km()),
                     "km": round(self.trip.total) if self.trip else None, "music": self._music_view("main")},
            "featured": self.featured,
            "music": self._music_view(str(self.featured) if self.featured else "main"),  # đài của xe đang chiếu
            "relief_auto": self.relief_auto,
            "route": self._main_route(),  # bảng chặng của xe đang chiếu (PLAN-130)
            "fleet": self._fleet(),
            "trip_minutes": self.trip_minutes,
        }
        relief = next((r for r in self.reliefs if r.no == self.featured), None)
        if relief:
            state.update(self._relief_screen(relief))
        return state
