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
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .moderation import allow_chat, clean_name
from .network import PASS_SPAN_KM, TUNNEL_SPAN_KM, Network, Trip
from .parser import FOOD_EMOJI, parse
from .provinces import BY_KEY, specialty_of

SEATS = 24
BOARD_SECONDS = 180.0
FULL_BUS_SECONDS = 10.0
REST_SECONDS = 90.0
HONK_BEFORE_END = 15.0
FINISH_SECONDS = 12.0
SPECIAL_SECONDS = 20.0
DROPOFF_BASE = 3.0  # giây mở màn thả khách, cộng thêm mỗi trang tên
EMPTY_BOARD_RETRY = 30.0  # hết giờ đón mà xe trống: đổi sang làn có người chờ / chờ thêm
# Nén thời gian (BR-7, sửa 01/11): km vẫn thật nhưng phần chạy đường của một chuyến tối đa ~4 phút (cao điểm 2,5 phút),
# tối thiểu 3 km / giây. Người xem TikTok ở lại vài phút — chuyến 12–18 phút làm người chờ xe sau bỏ đi trước khi lên xe.
KM_PER_SECOND = 3.0
TRIP_DRIVE_SECONDS = 240.0
LEG_SECONDS_MIN = 6.0
REST_MIN_KM = 150  # chuyến ngắn hơn không ghé trạm (xe khách thật nghỉ sau ~4 giờ lái — Luật TTATGT 2024)
TWO_RESTS_KM = 900  # chuyến dài hơn → nghỉ 2 trạm, nhưng chỉ khi không ai chờ xe sau (trạm là cảnh vui, không bắt chờ)
# Qua đèo / hầm chạy chậm lại để người xem kịp thấy (nén 3–7 km / giây thì đèo 16 km lướt qua trong 2–5 giây);
# xe khách thật cũng bò qua đèo. Chỉ kéo dài thêm ~10–15 giây mỗi đèo.
PASS_SECONDS = 16.0
TUNNEL_SECONDS = 8.0
# Giờ cao điểm (BR-9: theo từng hướng): làn của xe đang chạy còn một xe khách chờ → chạy nhanh hơn, 1 trạm ngắn.
RUSH_QUEUE = 24
RUSH_KM_PER_SECOND = 5.0
RUSH_TRIP_DRIVE_SECONDS = 150.0
RUSH_REST_SECONDS = 45.0
# Chọn làn xuất bến (BR-4, sửa 01/11): người chờ lâu nhất đi trước — xe chạy làn của vé chờ cũ nhất. Mô phỏng 4 giờ
# (bến TP.HCM, 1 comment / 20 s): 82 % người được lên xe trong 30 phút, làn thiệt nhất 78 % — hơn hẳn chọn theo số
# người chờ (làn nhỏ bị bỏ đói còn 24–46 %). Dễ giải thích với người xem: «ai chờ trước đi trước».
BOARD_AVG_START = 120.0  # ước lượng giờ đón / giờ chạy một chuyến trước khi đo được chuyến thật (ước giờ chờ trên vé)
RUN_AVG_START = 420.0
AVG_WEIGHT = 0.4  # trung bình trượt: chuyến mới đo chiếm 40 %
TICKET_IDLE = 30 * 60.0  # người trong hàng chờ im lặng quá lâu (đã rời phòng) → bỏ vé, nhường chỗ người đang xem
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
BOOST_MAX = 2.0
BOOST_PER_LIKE = 0.01
BOOST_HALF_LIFE = 6.0
CHAT_COOLDOWN = 5.0
REST_ACTION_COOLDOWN = 3.0
NAMES_PER_PAGE = 4  # thả khách: đọc tên tất cả, mỗi trang 4 người (chữ to đọc được trên điện thoại)
PAGE_SECONDS = 3.5
LIKE_MILESTONES = (1000, 5000, 10000)
TET_DAY = date(2027, 2, 6)
VN = ZoneInfo("Asia/Ho_Chi_Minh")  # máy chủ chạy UTC; đếm ngược Tết phải theo ngày Việt Nam
SPECIAL_FROM = ("BOARDING", "DRIVING", "REST")
FLAT = {"wind": 0.0, "pass": None, "tunnel": False, "climb": 0}  # đứng ở bến / trạm: đường thẳng, phẳng  # quà lớn chen ngay ở các pha này, xong quay lại đúng chỗ

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
    1: ("⭐ VIP: tên viền vàng trên xe", "⭐ VIP khi lên xe — comment tên tỉnh nha"),
    2: ("pháo hoa ngay + khi về tới quê", "pháo hoa mừng"),
    3: ("băng rôn «Xe Tết của bạn»", "băng rôn «Xe Tết của bạn»"),
    4: ("cả xe dừng lại chúc Tết", "cả xe dừng lại chúc Tết"),
}


def as_int(value, default: int = 1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def hue_of(uid: str) -> int:
    return int(hashlib.md5(uid.encode()).hexdigest()[:4], 16) % 360


def pick(options: tuple[str, ...], seed: str) -> str:
    return options[int(hashlib.md5(seed.encode()).hexdigest()[:6], 16) % len(options)]


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
    trips: int = 0
    followed: bool = False
    switched: bool = False
    last_chat: float = -1e9
    last_rest: float = -1e9
    gift_trip: int = 0  # xu cộng dồn trong chuyến này → tính bậc quà
    last_seen: float = 0.0  # lần cuối có bất kỳ tương tác nào (TikTok không báo ai rời phòng)
    last_share: float = -1e9
    last_notice: float = -1e9


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
    odo: float = 0.0  # km xe đã chạy
    done: int = 0  # số điểm đã thả khách


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
        self.viewers: dict[str, Viewer] = {}
        self.outbox: list[dict] = []
        self.queues: dict[str, list[str]] = {ln.key: [] for ln in self.network.lanes}  # vé chờ theo làn
        self.queued_at: dict[str, float] = {}  # giờ bắt đầu chờ của từng vé (giữ nguyên khi đổi tỉnh cùng làn)
        self.staying: list[str] = []
        self.board: Counter[str] = Counter()  # vé theo tỉnh trong phiên
        self.trip_likes = 0
        self.boost = 0.0
        self.bus_counter = 0
        self.trip: Trip | None = None
        self.reliefs: list[Relief] = []
        self.relief_auto = True  # admin tắt được: chỉ gọi xe tăng cường bằng tay / bằng quà
        self.featured: int | None = None  # xe tăng cường đang lên màn hình (None: xe chính)
        self.legs: list[Leg] = []
        self.leg_index = 0
        self.progress = 0.0
        self.leg_seconds = LEG_SECONDS_MIN
        self.rest_orders: Counter[str] = Counter()
        self.wc_line: list[str] = []
        self.honked = False
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
        self.outbox.append({"type": type_, **data})

    def loxe(self, text: str) -> None:
        self.emit("loxe", text=text)

    def drain(self) -> list[dict]:
        out, self.outbox = self.outbox, []
        return out

    def viewer(self, uid: str, name: str) -> Viewer:
        name = clean_name(name) if name else name
        v = self.viewers.get(uid)
        if v is None:
            v = self.viewers[uid] = Viewer(uid, name or uid, hue_of(uid))
        elif name:
            v.name = name
        return v

    def _set_phase(self, phase: str, now: float, seconds: float) -> None:
        self.phase = phase
        self.phase_started = now
        self.phase_until = now + seconds

    def current_leg(self) -> Leg | None:
        return self.legs[self.leg_index] if 0 <= self.leg_index < len(self.legs) else None

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

    def _prune_queues(self) -> None:
        """Vé ma (người chờ đã rời phòng quá lâu) không được tính vào chọn làn / cao điểm / số chờ."""
        for queue in self.queues.values():
            for uid in [u for u in queue if self.last_now - self.viewers[u].last_seen > TICKET_IDLE]:
                self._release(self.viewers[uid])

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
        self.bus_counter += 1
        self.bus = Bus(self.bus_counter, lane=self._pick_lane(), banner=self.next_banner)
        self.next_banner = None
        self.trip, self.legs, self.leg_index, self.progress = None, [], 0, 0.0
        self.trip_likes = 0
        for v in self.viewers.values():
            v.likes_trip = 0
            v.gift_trip = 0
            v.switched = False
        self._fill_from_queue()
        self._set_phase("BOARDING", now, self._board_time())
        lane = self.network.lane_by_key[self.bus.lane]
        self.loxe(f"Xe số {self.bus.no} {lane.label.lower()} vào bến! Comment tên tỉnh để lên xe nha bà con!")

    def _board_time(self) -> float:
        """Giờ đón tỉ lệ số giường còn trống: xe đã kín người chờ lên sẵn thì không bắt cả bến đợi đủ 3 phút."""
        free = SEATS - len(self.bus.riders())
        return FULL_BUS_SECONDS + (self.board_seconds - FULL_BUS_SECONDS) * free / SEATS

    def _pick_lane(self) -> str:
        """BR-4: làn của người đang chờ lâu nhất (công bằng theo người, không làn nào bị bỏ đói)."""
        self._prune_queues()
        waiting = [lane for lane, q in self.queues.items() if q]
        if not waiting:
            return self.bus.lane or self.network.lanes[0].key
        return min(waiting, key=lambda lane: self.queued_at.get(self.queues[lane][0], self.last_now))

    def _kmps(self, total_km: float) -> float:
        """Tốc độ nén cho cả chuyến: chuyến dài chạy nhanh hơn để phần chạy đường không quá ~4 phút (BR-7)."""
        if self.rush():
            return max(RUSH_KM_PER_SECOND, total_km / RUSH_TRIP_DRIVE_SECONDS)
        return max(KM_PER_SECOND, total_km / TRIP_DRIVE_SECONDS)

    def _fill_from_queue(self) -> None:
        queue = self.queues[self.bus.lane]
        while queue and (free := self.bus.free_seat()) is not None:
            uid = queue[0]
            if self.last_now - self.viewers[uid].last_seen > TICKET_IDLE:  # vé ma: không chở người đã rời phòng
                self._release(self.viewers[uid])
                continue
            self._unqueue(uid)
            self.bus.seats[free] = uid

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
        if self.boarding_started is not None:
            self.board_avg += AVG_WEIGHT * (now - self.boarding_started - self.board_avg)
        self.trip_started = now
        lane = net.lane_by_key[self.bus.lane]
        self.emit("depart", bus_no=self.bus.no, riders=len(self.bus.riders()), lane=lane.label,
                  stops=[BY_KEY[k].name for k in stops], km=round(total))
        self.loxe(f"Xe số {self.bus.no} xuất bến {lane.label.lower()}, {round(total)} km! Thả tim cho bác tài nhấn ga nào!")
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
        return min(1.0, span / kmps / seconds)

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
            self.loxe(f"Tới trạm dừng chân {place.name}! Xe nghỉ 15 phút, bà con xuống ăn uống, vệ sinh nha!")
            return
        prov = BY_KEY[leg.target]
        uids = [uid for uid in self.bus.riders() if self.viewers[uid].province == leg.target]
        for uid in uids:
            self.bus.seats[self.bus.seat_of(uid)] = None
        info = self._deliver(uids, leg.target, self.bus.no)
        pages = max(1, math.ceil(len(uids) / NAMES_PER_PAGE))
        self._set_phase("DROPOFF", now, DROPOFF_BASE + PAGE_SECONDS * pages)
        self.emit("dropoff", **info)
        self.loxe(f"{prov.name} tới rồi bà con ơi! Ai xuống {prov.name} chuẩn bị nha!")

    def _deliver(self, uids: list[str], province: str, bus_no: int) -> dict:
        """Thả khách về tới tỉnh (xe chính / xe tăng cường): cập nhật thống kê, trả nội dung băng rôn đọc tên."""
        prov = BY_KEY[province]
        km = self.network.km(province)  # km tuyến của khách (bến đi → tỉnh), không phải km xe đã chạy vòng
        people, fireworks = [], False
        for uid in uids:
            v = self.viewers[uid]
            v.province = None
            v.trips += 1
            fireworks = fireworks or v.fireworks
            people.append({"name": v.name, "hue": v.hue, "vip": v.vip, "wish": pick(WISHES, f"{uid}:{bus_no}")})
            v.fireworks = False
            v.vip = False
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
        self.bus_counter += 1
        relief = Relief(self.bus_counter, lane, riders, sponsor.name if sponsor else None, trip,
                        max(KM_PER_SECOND, trip.total / TRIP_DRIVE_SECONDS))
        self.reliefs.append(relief)
        ln = self.network.lane_by_key[lane]
        names = [self.viewers[uid].name for uid in riders]
        self.emit("relief_depart", bus_no=relief.no, lane=ln.label, arrow=ln.arrow, sponsor=relief.sponsor,
                  names=names[:3], count=len(names), km=round(trip.total))
        if sponsor:
            self.loxe(f"{sponsor.name} bao nguyên xe tăng cường cho bà con {ln.label.lower()}! Xe chạy liền!")
        elif admin:
            self.loxe(f"Nhà xe cho thêm xe tăng cường số {relief.no} {ln.label.lower()}, bà con chờ lên xe nha!")
        else:
            self.loxe(f"Bà con {ln.label.lower()} đông quá, nhà xe cho thêm xe tăng cường số {relief.no} chạy liền!")
        return relief

    def _run_reliefs(self, dt: float) -> None:
        """Tự gọi xe tăng cường cho làn đủ một xe người chờ; xe chạy (đèo / hầm chậm lại), tới tỉnh nào thả khách tỉnh đó."""
        self._prune_queues()
        if self.relief_auto:
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
                self.emit("relief_dropoff", **self._deliver(uids, province, relief.no), sponsor=relief.sponsor)
            if relief.done >= len(relief.trip.stops):
                self.reliefs.remove(relief)
                if self.featured == relief.no:  # xe đang chiếu tới bến cuối → màn hình quay về xe chính
                    self.featured = None

    # ---- admin: mọi chuyến xe -------------------------------------------

    def _relief(self, no: int) -> Relief:
        relief = next((r for r in self.reliefs if r.no == no), None)
        if relief is None:
            raise ValueError(f"không có xe tăng cường số {no} đang chạy")
        return relief

    def feature(self, no: int | None) -> None:
        """Admin chọn xe nào lên màn hình: None / số xe chính = xe chính; số xe tăng cường = màn hình theo xe đó."""
        self.featured = None if not no or no == self.bus.no else self._relief(int(no)).no

    def add_relief(self, lane: str) -> Relief:
        """Admin gọi thêm xe tăng cường cho một làn (không cần đủ 24 người chờ)."""
        if lane not in self.queues:
            raise ValueError(f"không có làn «{lane}»")
        relief = self._dispatch_relief(lane, admin=True)
        if relief is None:
            raise ValueError("làn này không có ai chờ hoặc đã đủ số xe tăng cường")
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
        self.loxe(f"Xe số {self.bus.no} về hết bến! Cảm ơn bà con đã đi cùng nhà xe!")

    def _board_top(self, n: int = 5) -> list[dict]:
        return [{"province": BY_KEY[k].name, "count": c} for k, c in self.board.most_common(n) if c > 0]

    # ---- vòng thời gian ------------------------------------------------

    def tick(self, now: float) -> None:
        dt = max(0.0, now - self.last_now)
        self.last_now = now
        self.boost *= math.pow(0.5, dt / BOOST_HALF_LIFE)
        if self.paused:
            self.phase_until += dt  # đồng hồ pha đứng yên, xe không chạy
            return
        self._run_reliefs(dt)
        if self.specials and self.phase in SPECIAL_FROM:
            self.resume = (self.phase, max(0.0, self.phase_until - now))
            self._set_phase("SPECIAL", now, SPECIAL_SECONDS)
            self.emit("special", name=self.specials.pop(0))
            return

        if self.phase == "BOARDING":
            if now >= self.phase_until:
                if self.bus.riders():
                    self._depart(now)
                else:  # xe trống: quay sang làn đang có người chờ (BR-4), cho họ lên rồi đón thêm một lúc
                    self.bus.lane = self._pick_lane()
                    self._fill_from_queue()
                    self.phase_until = now + EMPTY_BOARD_RETRY
                    if self.bus.riders():
                        lane = self.network.lane_by_key[self.bus.lane]
                        self.loxe(f"Xe số {self.bus.no} chuyển sang {lane.label.lower()}, bà con chờ hướng này lên xe nha!")
        elif self.phase == "DRIVING":
            self.progress += (dt * self.speed() / self.leg_seconds
                              * self._pace(self.trip, self.trip_km(), self._kmps(self.trip.total)))
            if self.progress >= 1.0:
                self.progress = 1.0
                self._arrive(now)
        elif self.phase == "SPECIAL":
            if now >= self.phase_until:
                phase, left = self.resume
                self._set_phase(phase, now, left)
        elif self.phase == "REST":
            if not self.honked and now >= self.phase_until - HONK_BEFORE_END:
                self.honked = True
                self.emit("honk")
                self.loxe("Bíp bíp! Lên xe bà con ơi, xe chạy rồi!")
            if now >= self.phase_until:
                self._next_leg(now)
        elif self.phase == "DROPOFF":
            if now >= self.phase_until:
                self._next_leg(now)
        elif self.phase == "FINISH":
            if now >= self.phase_until:
                self._enter_boarding(now)

    def speed(self) -> float:
        return 1.0 + self.boost

    # ---- admin ---------------------------------------------------------

    def skip(self) -> None:
        if self.phase == "DRIVING":
            self.progress = 1.0
        self.phase_until = self.last_now

    def set_departure(self, key: str) -> None:
        """BR-8: chỉ đổi bến đi khi bến đang đón mà chưa ai lên xe và không ai giữ chỗ (tránh vé sai hướng)."""
        if not self.boarding_open() or self.bus.riders() or self.waiting() or self.reliefs:
            raise ValueError("chỉ đổi bến đi khi xe đang đón, chưa ai lên xe, không ai giữ chỗ và hết xe tăng cường")
        self.network = self.network.switch(key)
        self.queues = {ln.key: [] for ln in self.network.lanes}
        self.queued_at = {}
        self.bus.lane = self.network.lanes[0].key
        self.loxe(f"Nhà xe chuyển về {self.network.departure.name}! Comment tên tỉnh để lên xe nha!")

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
        if kind != "join":  # vào phòng chưa tính là đang xem (tránh giữ vé cho người lướt qua)
            v.last_seen = now
        if kind == "comment":
            self._on_comment(v, str(event.get("text") or ""), now)
        elif kind == "like":
            self._on_like(v, max(1, min(LIKE_MAX, as_int(event.get("count")))))
        elif kind == "gift":
            self._on_gift(v, max(1, as_int(event.get("diamonds"))), str(event.get("gift") or "quà")[:24])
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
        return True

    def _on_comment(self, v: Viewer, text: str, now: float) -> None:
        cmd = parse(text, at_rest_stop=self.phase == "REST")
        if cmd.kind == "province":
            self._book(v, cmd.province.key)
        elif cmd.kind == "stay":
            self._stay(v)
        elif cmd.kind in ("food", "wc", "gift_shop"):
            if now - v.last_rest < REST_ACTION_COOLDOWN:
                return
            v.last_rest = now
            if cmd.kind == "food":
                self.rest_orders[cmd.item] += 1
                self.emit("rest_action", name=v.name, hue=v.hue, action="food",
                          item=cmd.item, emoji=FOOD_EMOJI[cmd.item])
            elif cmd.kind == "wc":
                if v.uid not in self.wc_line:
                    self.wc_line.append(v.uid)
                self.emit("rest_action", name=v.name, hue=v.hue, action="wc")
            else:
                self.emit("rest_action", name=v.name, hue=v.hue, action="shop")
        else:
            seat = self.bus.seat_of(v.uid)
            if seat is None or now - v.last_chat < CHAT_COOLDOWN or not text.strip() or not allow_chat(text):
                return
            v.last_chat = now
            self.emit("chat", name=v.name, seat=seat, hue=v.hue, text=text.strip()[:40])

    def _book(self, v: Viewer, key: str) -> None:
        v.stay = False
        if v.uid in self.staying:
            self.staying.remove(v.uid)
        if self.on_trip(v.uid):
            return  # đang ngồi xe chạy: không đổi được
        lane = self.network.lane_of(key)
        if lane is None:  # BR-5: tỉnh của bến đi — đang giữ giường / chỗ chờ thì bỏ vé (đã ở quê, không đi đâu nữa)
            self._release(v)
            self._already_home(v, key)
            return
        seat = self.bus.seat_of(v.uid)
        queued = self.lane_of_uid(v.uid)
        changed = seat is not None or queued is not None
        if changed:
            if v.province == key or v.switched:
                return
            v.switched = True
            if lane == (self.bus.lane if seat is not None else queued):  # đổi tỉnh cùng làn: giữ giường / thứ tự chờ
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
        if self.boarding_open() and not self.bus.riders() and lane != self.bus.lane:
            self.bus.lane = lane  # BR-4: xe đang đón chưa có ai → quay đầu theo người đầu tiên
            self._fill_from_queue()
        if self.boarding_open() and lane == self.bus.lane and (free := self.bus.free_seat()) is not None:
            self.bus.seats[free] = v.uid
            self._ticket(v, free, changed)
            left = SEATS - len(self.bus.riders())
            if left == 0:
                if self.phase == "SPECIAL":
                    self.resume = ("BOARDING", min(self.resume[1], FULL_BUS_SECONDS))
                else:
                    self.phase_until = min(self.phase_until, self.last_now + FULL_BUS_SECONDS)
                self.loxe(f"Xe đủ {SEATS} khách rồi! Chuẩn bị xuất bến!")
            elif left in (5, 1):
                self.loxe(f"Còn {left} chỗ, còn {left} chỗ! Lên lẹ đi bà con!")
        else:
            self.queues[lane].append(v.uid)
            self.queued_at[v.uid] = v.last_seen
            self._ticket(v, None, changed)

    def _ticket(self, v: Viewer, seat: int | None, changed: bool) -> None:
        lane = self.network.lane_by_key[self.network.lane_of(v.province)]
        km = self.network.km(v.province)
        info = {"name": v.name, "hue": v.hue, "province": BY_KEY[v.province].name, "seat": seat, "changed": changed,
                "lane": lane.label, "arrow": lane.arrow, "km": km, "departure": self.network.departure.short}
        if seat is not None:
            self.emit("ticket", **info, bus_no=self.bus.no, next=False)
            return
        bus_no, minutes = self._queue_eta(lane.key, self.queues[lane.key].index(v.uid))
        self.emit("ticket", **info, bus_no=bus_no, next=True, eta_min=minutes)

    def _already_home(self, v: Viewer, key: str) -> None:
        """BR-5: comment đúng tỉnh của bến đi → không lên xe, vẫn được tính là đã về quê (một lần)."""
        if v.uid not in self.home_counted:
            self.home_counted.add(v.uid)
            self.board[key] += 1
        if self._noticed(v):
            name = BY_KEY[key].name
            self.emit("home", name=v.name, hue=v.hue, province=name)
            self.loxe(f"{v.name} ở ngay {name} rồi, đi bộ về nhà nha!")

    def _noticed(self, v: Viewer) -> bool:
        """Thẻ + lơ xe cho «không về» / «đã ở quê»: lặp lại trong NOTICE_COOLDOWN thì im (chống spam)."""
        if v.last_seen - v.last_notice < NOTICE_COOLDOWN:
            return False
        v.last_notice = v.last_seen
        return True

    def _stay(self, v: Viewer) -> None:
        if self.on_trip(v.uid):
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
        for mark in LIKE_MILESTONES:
            if before < mark <= self.trip_likes:
                self.emit("like_milestone", total=mark)
                self.loxe(f"{mark:,} tim rồi! Bác tài nhấn ga nào!".replace(",", "."))

    def _queue_eta(self, lane: str, position: int) -> tuple[int, int]:
        """(số xe, số phút tới lúc được lên xe) cho người thứ `position` trong hàng chờ làn `lane`.

        Chuyến hiện tại phải xong trước; mỗi làn có người chờ lâu hơn người đầu hàng làn này thì đi trước một chuyến
        (BR-4 ai chờ trước đi trước).
        """
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
            left = special
            kmps = self._kmps(self.trip.total) if self.trip else KM_PER_SECOND
            for i in range(self.leg_index, len(self.legs)):
                leg, current = self.legs[i], i == self.leg_index
                if not current or phase == "DRIVING":
                    leg_km = leg.km - (self.legs[i - 1].km if i > 0 else 0.0)
                    left += ((1 - self.progress) if current else 1.0) * max(LEG_SECONDS_MIN, leg_km / kmps)
                if current and phase in ("REST", "DROPOFF"):
                    left += phase_left
                elif leg.kind == "rest":
                    left += RUSH_REST_SECONDS if self.rush() else self.rest_seconds
                else:
                    left += DROPOFF_BASE + PAGE_SECONDS
            left += FINISH_SECONDS
        left += max(0, trips_ahead - 1) * (self.board_avg + self.run_avg)
        return max(1, math.ceil(left / 60))

    def _on_gift(self, v: Viewer, diamonds: int, gift: str) -> None:
        # Cộng dồn trong chuyến: 10 hoa hồng = 10 xu → lên bậc pháo hoa (REVIEW BA-9)
        before = v.gift_trip
        v.gift_trip += diamonds
        total = v.gift_trip
        tier = next(t for floor, t in GIFT_TIERS if total >= floor)
        tier_before = next((t for floor, t in GIFT_TIERS if before >= floor), 0)
        queued = self.lane_of_uid(v.uid)
        relief = None
        if queued and tier >= RELIEF_GIFT_TIER > tier_before:  # đang chờ xe sau + lên bậc băng rôn → bao xe tăng cường
            relief = self._dispatch_relief(queued, sponsor=v)
        ticketed = self.bus.seat_of(v.uid) is not None or queued is not None
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
                self.specials.append(v.name)
        perk = GIFT_LABELS[tier][0 if ticketed else 1]
        if relief:
            perk = f"🚌 xe tăng cường chạy ngay cho bà con {self.network.lane_by_key[relief.lane].label.lower()}"
        self.emit("gift", name=v.name, hue=v.hue, tier=tier, tier_up=tier > tier_before, gift=gift,
                  diamonds=diamonds, total=total, perk=perk, next_tier=self._next_tier_hint(total, queued is not None))
        if self.phase == "REST" and v.uid not in self.treated:  # combo 30 hoa hồng chỉ «bao cả xe» một lần
            self.treated.add(v.uid)
            self.emit("treat", name=v.name)
            self.loxe(f"{v.name} bao cả xe trà đá! Cảm ơn nha!")

    @staticmethod
    def _next_tier_hint(total: int, queued: bool = False) -> str:
        """«Tặng thêm 6 xu → pháo hoa…»: mục tiêu gần trước mắt thì người ta tặng tiếp."""
        if total >= 1000:
            need = 1000 - total % 1000
            return f"thêm {need} xu → cả xe chúc Tết thêm lần nữa"
        floor, tier = min(((f, t) for f, t in GIFT_TIERS if f > total), key=lambda ft: ft[0])
        if tier == RELIEF_GIFT_TIER and queued:  # đang chờ xe sau: mốc kế tiếp là gọi được xe cho cả làn mình
            return f"thêm {floor - total} xu → xe tăng cường chạy ngay cho cả làn của bạn"
        return f"thêm {floor - total} xu → {GIFT_LABELS[tier][0]}"

    # ---- trạng thái cho overlay ----------------------------------------

    def _where(self) -> tuple[str, dict]:
        """Tỉnh xe chính đang ở / đi qua + hồ sơ đường tại đó cho overlay uốn đường và đổi cảnh."""
        leg = self.current_leg()
        if leg is None or self.trip is None:
            return self.network.departure.province, dict(FLAT)  # ở bến / về bến: cảnh của bến đi
        if self._phase_now() != "DRIVING":
            return leg.target, dict(FLAT)
        return self._road_at(self.trip, self.trip_km())

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
        net, nxt = self.network, self._pick_lane()
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
                "left_km": round(relief.trip.total - relief.odo)}

    def _seats_view(self, uids: list[str | None]) -> list[dict | None]:
        out = []
        for uid in uids:
            v = self.viewers.get(uid) if uid else None
            out.append({"name": v.name, "hue": v.hue, "vip": v.vip,
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
            "specialty": specialty_of(place), "rush": False,
        }

    def snapshot(self) -> dict:
        place, terrain = self._where()
        region = BY_KEY[place].region
        seats = self._seats_view(self.bus.seats)
        net = self.network
        legs = [{"kind": item.kind, "km": round(item.km),
                 "label": f"Trạm {BY_KEY[item.target].name}" if item.kind == "rest" else BY_KEY[item.target].name}
                for item in self.legs]
        bus_lane = net.lane_by_key[self.bus.lane]
        next_lane, queue = self._queue_view()
        today = self.today or datetime.now(VN).date()
        state = {
            "phase": self.phase,
            "paused": self.paused,
            "phase_left": max(0.0, self.phase_until - self.last_now) if self.phase != "DRIVING" else None,
            "phase_total": max(0.0, self.phase_until - self.phase_started) if self.phase != "DRIVING" else None,
            "bus": {"no": self.bus.no, "seats": seats, "banner": self.bus.banner,
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
            "speed": round(self.speed(), 3),
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
            "delivered": self.delivered,
            "days_to_tet": max(0, (TET_DAY - today).days),
            "rush": self.rush(),
            # xe chính cho trang admin (khi màn hình đang chiếu xe tăng cường thì các trường trên là của xe đó)
            "main": {"no": self.bus.no, "phase": self.phase, "riders": len(self.bus.riders()), "lane": bus_lane.label,
                     "arrow": bus_lane.arrow, "phase_left": max(0.0, self.phase_until - self.last_now)
                     if self.phase != "DRIVING" else None, "trip_km": round(self.trip_km()),
                     "km": round(self.trip.total) if self.trip else None},
            "featured": self.featured,
            "relief_auto": self.relief_auto,
        }
        relief = next((r for r in self.reliefs if r.no == self.featured), None)
        if relief:
            state.update(self._relief_screen(relief))
        return state
