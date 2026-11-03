import itertools
from datetime import date

from xe_tet.server.game.engine import (BOARD_SECONDS, FULL_BUS_SECONDS, NOTICE_COOLDOWN, REST_MIN_KM, SEATS,
                                       SPECIAL_SECONDS, Engine)
from xe_tet.server.game.parser import normalize, parse
from xe_tet.server.game.provinces import BY_KEY, PROVINCES


def types(events):
    return [e["type"] for e in events]


def run_until(engine, phase, start, limit=3000.0, step=0.5):
    t = start
    while engine.phase != phase and t < start + limit:
        t += step
        engine.tick(t)
    assert engine.phase == phase, f"kẹt ở {engine.phase}"
    return t


# ---- nhận diện comment ---------------------------------------------------

def test_63_provinces_with_unique_plates():
    assert len(PROVINCES) == 63
    plates = [code for p in PROVINCES for code in p.plates]
    assert len(plates) == len(set(plates))


def test_normalize_strips_vietnamese_marks():
    assert normalize("Về ĐÀ NẴNG thôi!!") == "ve da nang thoi"


def test_parse_province_variants():
    cases = {
        "Nghệ An": "nghean", "nghe an": "nghean", "37": "nghean", "về nghệ an thôi": "nghean",
        "sg": "hcm", "Sài Gòn": "hcm", "51": "hcm", "huế": "hue", "về Huế": "hue",
        "Quảng Nam": "quangnam", "hà nam": "hanam", "đà lạt": "lamdong", "Thanh Hoá": "thanhhoa",
    }
    for text, key in cases.items():
        cmd = parse(text)
        assert cmd.kind == "province" and cmd.province.key == key, text


def test_short_codes_only_match_whole_comment():
    assert parse("na").province.key == "nghean"
    assert parse("na ná nhau").kind == "chat"
    assert parse("anh 37 tuổi").kind == "chat"


def test_parse_stay_beats_province():
    assert parse("không về Nghệ An được").kind == "stay"
    assert parse("ko ve").kind == "stay"


def test_rest_commands_only_at_rest_stop():
    assert parse("phở").kind == "chat"
    assert parse("bánh mì", at_rest_stop=True).item == "Bánh mì"
    assert parse("cho 1 tô phở", at_rest_stop=True).item == "Phở"
    assert parse("đi vệ sinh", at_rest_stop=True).kind == "wc"
    assert parse("mua quà", at_rest_stop=True).kind == "gift_shop"
    assert parse("Nghệ An", at_rest_stop=True).kind == "province"


# ---- luật chơi -----------------------------------------------------------

def comment(engine, name, text, t):
    engine.handle({"type": "comment", "name": name, "text": text}, t)


def test_full_trip_cycle():
    """Bến đi TP.HCM: Hà Nội + Nghệ An cùng hướng Bắc lên xe 1; Cà Mau khác hướng giữ chỗ xe hướng Nam kế tiếp."""
    e = Engine(0.0, today=date(2026, 12, 15))
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Bình", "Cà Mau", 1)
    comment(e, "Chi", "37", 1)
    assert e.bus.lane == "north" and e.bus.riders() == ["an", "chi"]
    assert e.queues["south"] == ["bình"]
    e.drain()
    t = run_until(e, "DRIVING", 1)
    assert t >= BOARD_SECONDS
    stops = [leg.target for leg in e.legs if leg.kind == "stop"]
    assert stops == ["nghean", "hanoi"]  # theo km thật tăng dần, không vòng xuống Cà Mau
    assert [leg.km for leg in e.legs] == sorted(leg.km for leg in e.legs)
    t = run_until(e, "DROPOFF", t)
    events = e.drain()
    drop = [ev for ev in events if ev["type"] == "dropoff"][0]
    assert drop["province"] == "Nghệ An" and drop["people"][0]["name"] == "Chi"
    assert drop["km"] == e.network.km("nghean") and drop["departure"] == "TP.HCM"
    t = run_until(e, "FINISH", t)
    events += e.drain()  # chuyến dài: trạm nghỉ (còi) có thể nằm trước Nghệ An
    assert "honk" in types(events) and "finish" in types(events)
    assert e.delivered == 2 and e.bus.riders() == []
    run_until(e, "BOARDING", t)
    assert e.bus.no == 2 and e.bus.lane == "south" and e.bus.riders() == ["bình"]
    assert e.snapshot()["days_to_tet"] == 53


def test_full_bus_departs_fast_and_overflow_goes_to_next_bus():
    e = Engine(0.0)
    for i in range(SEATS + 3):
        comment(e, f"K{i}", "Huế", 1)
    assert len(e.bus.riders()) == SEATS and len(e.queues["north"]) == 3
    # đủ giường thì chạy sớm, nhưng 24 người vừa lên dồn thì giữ đủ lâu cho lơ xe đọc tên từng người (rà soát 03/11)
    from xe_tet.server.game.engine import FULL_HOLD_MAX
    assert 1 + SEATS * 1.0 <= e.phase_until <= 1 + FULL_HOLD_MAX
    tickets = [ev for ev in e.drain() if ev["type"] == "ticket"]
    assert tickets[-1]["next"] is True and tickets[-1]["bus_no"] == 2
    t = run_until(e, "FINISH", 1)
    run_until(e, "BOARDING", t)
    assert len(e.bus.riders()) == 3 and e.waiting() == 0


def test_stay_releases_seat_and_cannot_jump_off_moving_bus():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    comment(e, "An", "không về", 2)
    assert e.bus.riders() == [] and e.staying == ["an"]
    comment(e, "An", "Huế", 3)
    assert e.bus.riders() == ["an"] and e.staying == []
    run_until(e, "DRIVING", 3)
    comment(e, "An", "không về", 300)
    assert e.bus.riders() == ["an"]


def test_switch_province_once_per_trip():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    comment(e, "An", "Hà Nội", 2)
    comment(e, "An", "Cà Mau", 3)
    assert e.viewers["an"].province == "hanoi"


def test_likes_speed_up_and_decay():
    e = Engine(0.0)
    e.handle({"type": "like", "name": "An", "count": 100}, 1)
    assert e.speed() > 1.9
    e.tick(60)
    assert e.speed() < 1.01


def test_gift_tiers_are_fixed_rewards():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    e.drain()
    e.handle({"type": "gift", "name": "An", "diamonds": 1}, 2)
    e.handle({"type": "gift", "name": "Bo", "diamonds": 199}, 2)
    gifts = [ev for ev in e.drain() if ev["type"] == "gift"]
    assert [g["tier"] for g in gifts] == [1, 3]
    assert e.viewers["an"].vip and e.bus.banner == "Bo"


def test_big_gift_interrupts_driving_with_special_scene():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    t = run_until(e, "DRIVING", 1)
    e.handle({"type": "gift", "name": "Bo", "diamonds": 1000}, t)
    e.tick(t + 0.5)
    assert e.phase == "SPECIAL"
    e.tick(t + 0.5 + SPECIAL_SECONDS + 0.1)
    assert e.phase == "DRIVING"


def test_rest_stop_actions_and_treat():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    t = run_until(e, "REST", 1)
    e.drain()
    comment(e, "Bo", "phở", t)
    comment(e, "Bo", "wc", t + 1)  # còn trong thời gian chờ 3 s
    comment(e, "Cu", "wc", t + 1)
    e.handle({"type": "gift", "name": "Cu", "diamonds": 1}, t + 2)
    events = e.drain()
    assert types(events).count("rest_action") == 2
    assert "treat" in types(events)
    snap = e.snapshot()
    assert snap["rest"]["orders"][0]["item"] == "Phở" and snap["rest"]["wc_count"] == 1


def test_chat_bubble_only_for_riders_with_cooldown():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    e.drain()
    comment(e, "An", "nhớ nhà quá", 2)
    comment(e, "An", "đói", 3)
    comment(e, "Lạ", "hello", 3)
    chats = [ev for ev in e.drain() if ev["type"] == "chat"]
    assert len(chats) == 1 and chats[0]["seat"] == 0


def test_events_never_use_reserved_kind_field():
    """Server bọc sự kiện trong khung {"kind": "event"}; sự kiện có trường "kind" sẽ làm overlay bỏ qua."""
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    t = run_until(e, "REST", 1)
    comment(e, "Bo", "phở", t)
    comment(e, "Cu", "wc", t)
    comment(e, "Du", "mua quà", t)
    actions = [ev for ev in e.drain() if ev["type"] == "rest_action"]
    assert [a["action"] for a in actions] == ["food", "wc", "shop"]
    assert all("kind" not in ev for ev in actions)


# ---- rà soát 31/10: lỗi nghiệp vụ đã sửa ----------------------------------

def test_chatter_does_not_book_or_cancel():
    for text in ("Hà Nội lạnh quá", "chị Huệ ơi", "Hà Giang ơi vào đây", "nhớ Nghệ An quá", "Thái Bình đẹp trai"):
        assert parse(text).kind == "chat", text
    for text in ("mẹ chưa về à", "ai ở lại không", "ko về thì sao"):
        assert parse(text).kind == "chat", text
    for text, kind in (("cho mình về Huế nha", "province"), ("về quê Hà Nội", "province"),
                       ("năm nay không về được", "stay"), ("tết này em ko về", "stay")):
        assert parse(text).kind == kind, text


def test_seated_rider_chatting_keeps_seat():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    comment(e, "An", "mẹ chưa về à", 2)
    comment(e, "An", "Hà Nội lạnh quá", 3)
    assert e.bus.riders() == ["an"] and e.viewers["an"].province == "hue"


def test_everyone_dropped_off_is_named():
    e = Engine(0.0)
    for i in range(20):
        comment(e, f"N{i}", "Nghệ An", 1)
    run_until(e, "DROPOFF", 1)
    drop = [ev for ev in e.drain() if ev["type"] == "dropoff"][0]
    assert len(drop["people"]) == 20
    from xe_tet.server.game.engine import DROPOFF_BASE, NAMES_PER_PAGE, PAGE_SECONDS
    assert e.phase_until - e.phase_started >= DROPOFF_BASE + PAGE_SECONDS * (20 // NAMES_PER_PAGE)  # đủ giờ lật hết trang


def test_banner_gift_during_finish_goes_to_next_bus():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    t = run_until(e, "FINISH", 1)
    e.handle({"type": "gift", "name": "Bo", "diamonds": 199}, t)
    run_until(e, "BOARDING", t)
    assert e.bus.banner == "Bo"


def test_big_gift_during_boarding_plays_now_and_resumes_boarding():
    e = Engine(0.0, board_seconds=100)
    e.handle({"type": "gift", "name": "Bo", "diamonds": 1000}, 10)
    e.tick(10)
    assert e.phase == "SPECIAL"
    comment(e, "An", "Huế", 11)  # vẫn lên được xe đang đón
    assert e.bus.riders() == ["an"]
    e.tick(10 + SPECIAL_SECONDS + 0.1)
    assert e.phase == "BOARDING" and 85 < e.phase_until - e.last_now <= 90


def test_gift_perk_text_matches_ticket():
    e = Engine(0.0)
    e.handle({"type": "gift", "name": "Lạ", "diamonds": 1}, 1)
    comment(e, "An", "Huế", 1)
    e.handle({"type": "gift", "name": "An", "diamonds": 1}, 2)
    perks = [ev["perk"] for ev in e.drain() if ev["type"] == "gift"]
    assert "gõ tên tỉnh" in perks[0] and "trên xe" in perks[1]


def test_moderation_masks_names_and_drops_bad_chat():
    e = Engine(0.0)
    comment(e, "Thằng đm", "Huế", 1)
    assert "đm" not in e.viewers["thằng đm"].name
    e.drain()
    for i, text in enumerate(("vl thật", "zalo 0912 345 678", "vào www.abc.com", "đi về các bạn ơi")):
        comment(e, "Thằng đm", text, 10 + i * 10)
    chats = [ev["text"] for ev in e.drain() if ev["type"] == "chat"]
    assert chats == ["đi về các bạn ơi"]  # «đi», «các» không bị nhầm là từ bậy


def test_bad_numbers_do_not_crash():
    e = Engine(0.0)
    e.handle({"type": "like", "name": "A", "count": "abc"}, 1)
    e.handle({"type": "gift", "name": "A", "diamonds": None}, 1)
    assert e.trip_likes == 1
    assert e.handle({"type": "comment", "name": 5, "text": "Huế"}, 1)  # tên không phải chữ: ép thành chuỗi, không lỗi
    assert not e.handle({"type": "like", "count": 5}, 1) and e.trip_likes == 1  # không có người gửi: bị loại


def test_countdown_uses_vietnam_date():
    from datetime import datetime
    from xe_tet.server.game.engine import VN
    from xe_tet.server.game.season import TET_DAY
    assert Engine(0.0).snapshot()["days_to_tet"] == (TET_DAY - datetime.now(VN).date()).days


# ---- đề xuất đã duyệt 31/10: giờ cao điểm, giờ chờ, cộng dồn quà ------------

def test_rush_hour_shortens_trip_when_queue_is_long(monkeypatch):
    """Cao điểm là phương án cuối: chỉ khi xe tăng cường đã chạy hết số cho phép mà làn vẫn còn ≥ 1 xe người chờ."""
    from xe_tet.server.game import engine as engine_module
    from xe_tet.server.game.engine import LEG_SECONDS_MIN, RUSH_DRIVE_FACTOR, RUSH_REST_SECONDS
    monkeypatch.setattr(engine_module, "RELIEF_MAX", 0)
    calm = Engine(0.0)
    busy = Engine(0.0)
    provs = [p.name for p in PROVINCES[:24]]
    for e, extra in ((calm, 0), (busy, 30)):
        for i in range(24 + extra):
            comment(e, f"K{i}", provs[i % 24], 1)
    for e in (calm, busy):
        run_until(e, "DRIVING", 1)
    assert not calm.rush() and busy.rush()
    first_km = busy.legs[0].km
    assert abs(busy.trip.total / busy._kmps(busy.trip.total)
               - busy.drive_seconds(busy.trip.total) * RUSH_DRIVE_FACTOR) < 1e-6  # chạy nhanh hơn
    assert busy.leg_seconds == max(LEG_SECONDS_MIN, first_km / busy._kmps(busy.trip.total))
    assert busy._kmps(busy.trip.total) > calm._kmps(calm.trip.total)
    assert sum(leg.kind == "rest" for leg in busy.legs) == 1 < sum(leg.kind == "rest" for leg in calm.legs)
    t = run_until(busy, "REST", 300)
    assert busy.phase_until - t <= RUSH_REST_SECONDS
    assert busy.snapshot()["rush"] is True


def test_queued_ticket_carries_wait_estimate():
    e = Engine(0.0)
    for i in range(24 + 30):
        comment(e, f"K{i}", "Huế", 1)
    tickets = [ev for ev in e.drain() if ev["type"] == "ticket"]
    next_bus, after = tickets[24], tickets[-1]  # người đầu hàng chờ (xe 2) và người cuối (xe 3)
    assert next_bus["bus_no"] == 2 and after["bus_no"] == 3
    assert 1 <= next_bus["eta_min"] < after["eta_min"]


def test_gifts_add_up_within_trip():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    e.drain()
    for _ in range(10):
        e.handle({"type": "gift", "name": "An", "diamonds": 1}, 2)
    gifts = [ev for ev in e.drain() if ev["type"] == "gift"]
    assert [g["tier"] for g in gifts][-1] == 2 and gifts[-1]["total"] == 10
    assert "thêm 90 xu → băng rôn" in gifts[-1]["next_tier"]
    assert "thêm 9 xu" in gifts[0]["next_tier"]


def test_each_1000_crossed_adds_one_special():
    e = Engine(0.0)
    e.handle({"type": "gift", "name": "Bo", "diamonds": 600}, 1)
    e.handle({"type": "gift", "name": "Bo", "diamonds": 600}, 1)  # 1200 → 1 lần
    e.handle({"type": "gift", "name": "Bo", "diamonds": 900}, 1)  # 2100 → thêm 1
    assert e.specials == ["Bo", "Bo"]


def test_gift_total_resets_next_trip():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    e.handle({"type": "gift", "name": "An", "diamonds": 50}, 2)
    t = run_until(e, "FINISH", 2)
    run_until(e, "BOARDING", t)
    assert e.viewers["an"].gift_trip == 0


# ---- rà soát lần 2 (dữ liệu live thật) ------------------------------------

def test_combo_at_rest_stop_does_not_spam():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    t = run_until(e, "REST", 1)
    e.drain()
    for _ in range(30):  # combo 30 hoa hồng
        e.handle({"type": "gift", "name": "Đại Gia", "diamonds": 1}, t)
    out = e.drain()
    assert types(out).count("treat") == 1
    assert [g["tier"] for g in out if g["type"] == "gift" and g["tier_up"]] == [1, 2]  # pháo hoa chỉ khi lên bậc


def test_follow_once_and_share_cooldown():
    e = Engine(0.0)
    e.drain()
    for i in range(5):
        e.handle({"type": "follow", "name": "Spam"}, 1 + i)
    for i in range(10):
        e.handle({"type": "share", "name": "Spam"}, 1 + i)
    e.handle({"type": "share", "name": "Spam"}, 100)
    out = types(e.drain())
    assert out.count("follow") == 1 and out.count("share") == 2


def test_idle_queued_ticket_expires_active_one_rides():
    from xe_tet.server.game.engine import TICKET_IDLE
    e = Engine(0.0)
    for i in range(24):
        comment(e, f"K{i}", "Huế", 1)
    comment(e, "Ma", "Huế", 2)  # xếp hàng rồi rời phòng
    comment(e, "Thật", "Huế", 3)  # xếp hàng, vẫn thả tim
    t = run_until(e, "DRIVING", 3)
    while e.phase != "FINISH":
        t += 30
        e.handle({"type": "like", "name": "Thật", "count": 1}, t)
        e.tick(t)
    e.last_now = t = max(t, 2 + TICKET_IDLE + 1)
    e.handle({"type": "like", "name": "Thật", "count": 1}, t)
    run_until(e, "BOARDING", t)
    assert e.bus.riders() == ["thật"] and "ma" not in e.queued_at



# ---- tuyến thật: làn theo hướng, km thật (BRD-tuyen-xe.md) ------------------

def test_other_direction_waits_for_its_own_bus_at_dalat():
    """Câu hỏi của anh: xe ở bến Đà Lạt đang đón hướng Bắc, có người comment Cà Mau."""
    e = Engine(0.0)
    e.set_departure("dalat")
    comment(e, "An", "Hà Nội", 1)  # xe quay đầu theo người đầu tiên: hướng Bắc
    comment(e, "Út", "Cà Mau", 2)
    assert e.bus.lane == "north" and e.bus.riders() == ["an"]
    ticket = [ev for ev in e.drain() if ev["type"] == "ticket"][-1]
    assert ticket["next"] is True and ticket["lane"] == "Hướng Nam" and ticket["departure"] == "Đà Lạt"
    assert ticket["km"] == e.network.km("camau") and ticket["eta_min"] >= 1
    t = run_until(e, "FINISH", 2)
    assert all(leg.target != "camau" for leg in e.legs)  # xe hướng Bắc không vòng xuống Cà Mau
    run_until(e, "BOARDING", t)
    assert e.bus.lane == "south" and e.bus.riders() == ["út"]


def test_empty_boarding_bus_turns_to_first_passenger():
    e = Engine(0.0)
    assert e.bus.riders() == []
    comment(e, "Út", "Cà Mau", 1)
    assert e.bus.lane == "south" and e.bus.riders() == ["út"]


def test_oldest_ticket_goes_first():
    """BR-4: người chờ quá lâu (LANE_MAX_WAIT) thì tuyến của họ chạy trước, kể cả làn kia 40 người."""
    from xe_tet.server.game.engine import LANE_MAX_WAIT
    e = Engine(0.0)
    for i in range(24):
        comment(e, f"B{i}", "Huế", 1)  # Bắc: 1 xe đầy
    comment(e, "Út", "Cà Mau", 1)  # Nam: 1 người, giữ chỗ trước
    for i in range(40):
        comment(e, f"C{i}", "Huế", 2)  # Bắc: 40 người giữ chỗ sau
    t = run_until(e, "FINISH", 1)
    e.queued_at["út"] = t - LANE_MAX_WAIT - 1  # Út đã chờ quá lâu
    run_until(e, "BOARDING", t)
    # PLAN-145: bình thường chuyến mới chọn tuyến đông người — nhưng Út chờ quá LANE_MAX_WAIT nên tuyến Nam đi trước
    assert e.bus.lane == "south" and e.bus.seat_of("út") is not None


def test_new_trip_takes_the_fullest_route_unless_someone_waited_too_long():
    """PLAN-145: chỉ một xe — chuyến mới chở tuyến đông người chờ nhất (đi cùng tuyến về đầy đủ); chưa ai chờ quá lâu."""
    e = Engine(0.0)
    comment(e, "Út", "Cà Mau", 1)  # Nam: 1 người, chờ trước
    for i in range(10):
        comment(e, f"C{i}", "Huế", 2)  # Bắc: 10 người
    e.queues  # Bắc đã lên xe chính (đang đón) — cho xe chạy rồi về để chọn tuyến chuyến sau
    e.bus.lane = "south"
    e._enter_boarding(3)
    assert e.bus.lane == "north"


def test_home_province_is_not_a_trip():
    """BR-5: ở bến TP.HCM mà comment Sài Gòn → không lên xe, vẫn ghi tên tỉnh (một lần)."""
    e = Engine(0.0)
    comment(e, "Tèo", "Sài Gòn", 1)
    comment(e, "Tèo", "sg", 2)
    assert e.bus.riders() == [] and e.waiting() == 0
    assert "home" in types(e.drain())
    assert e.board["hcm"] == 1


def test_switching_to_other_direction_moves_ticket():
    e = Engine(0.0)
    comment(e, "An", "Huế", 1)
    comment(e, "Bo", "Hà Nội", 1)
    comment(e, "An", "Cà Mau", 2)  # đổi sang hướng khác: rời giường, giữ chỗ làn Nam
    assert e.bus.riders() == ["bo"] and e.queues["south"] == ["an"]


def test_set_departure_only_when_station_is_empty():
    e = Engine(0.0)
    e.set_departure("hn_giapbat")
    assert e.network.departure.short == "Hà Nội"
    comment(e, "An", "Huế", 1)
    try:
        e.set_departure("dalat")
        raise AssertionError("phải từ chối khi đã có khách")
    except ValueError:
        pass


def test_snapshot_reports_real_km_and_terrain():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    t = run_until(e, "DRIVING", 1)
    e.tick(t + 3)
    snap = e.snapshot()
    assert snap["bus"]["km"] == e.network.km("hanoi") and snap["departure"]["short"] == "TP.HCM"
    assert 0 < snap["trip_km"] < snap["bus"]["km"]
    assert snap["terrain"]["wind"] >= 0 and [ln["key"] for ln in snap["lanes"]] == ["north", "south"]


def test_real_route_table(real_routes):
    """Dữ liệu OSRM thật: đi trong nước (QL1, không vòng qua Lào), km hợp lý, Cà Mau và Hà Nội khác làn."""
    from xe_tet.server.game.network import Network
    hcm = Network(real_routes, "hcm_miendong")
    assert 1600 < hcm.km("hanoi") < 1800 and hcm.lane_of("camau") != hcm.lane_of("hanoi")
    assert hcm.lane_by_key[hcm.lane_of("hanoi")].label == "Hướng Hà Nội"
    assert hcm.lane_of("nghean") == hcm.lane_of("hanoi")  # dọc trục Bắc – Nam
    passes = {p.name: p.tunnel for p in hcm.routes["hanoi"].passes}
    assert passes.get("Hầm Hải Vân") is True and passes.get("Hầm Cù Mông") is True  # cao tốc / QL1 đi hầm
    assert {p.name: p.tunnel for p in Network(real_routes, "hn_giapbat").routes["dienbien"].passes}["Đèo Pha Đin"] is False
    dalat = Network(real_routes, "dalat")
    assert 540 < dalat.km("camau") < 650 and dalat.lane_of("camau") != dalat.lane_of("hanoi")
    assert dalat.lane_of("lamdong") is None
    for net in (hcm, dalat):
        assert 2 <= len(net.lanes) <= 5
        assert max(w for r in net.routes.values() for w in r.wind) < 300  # độ / km: đèo gắt nhất (Khau Phạ) ~220; nhiễu phố cũ 500–700


# ---- rà soát 01/11 (PLAN-123): mỗi lỗi một test hồi quy ---------------------

def test_km_runs_after_big_gift_during_boarding():
    """Quà 1000 xu lúc đón khách → cảnh chúc Tết → xe chạy: km phải tăng (trước đây đứng 0 cả chuyến)."""
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    e.handle({"type": "gift", "name": "Bo", "diamonds": 1000}, 2)
    e.tick(2.5)
    assert e.phase == "SPECIAL"
    t = run_until(e, "DRIVING", 3)
    e.tick(t + 20)
    assert e.trip_km() > 0 and e.snapshot()["trip_km"] > 0


def test_last_seconds_before_departure_nobody_gets_off():
    """Anh dặn 02/11 «10s lên xe thì ko cho ai xuống hết»: BOARD_LOCK giây cuối giờ đón (xe đầy là đếm ngược 10 giây) khách đang
    ngồi không đổi tỉnh / bỏ vé được; lơ xe nhắc. Còn sớm thì vẫn đổi được như cũ."""
    e = Engine(0.0)
    for i in range(SEATS):
        comment(e, f"K{i}", "Hà Nội", 1)
    comment(e, "Cho", "Hà Nội", 2)  # hàng chờ cùng làn
    e.drain()
    lock = e.phase_until - 5  # xe đầy → đếm ngược; 10 giây cuối: không xuống được
    e.tick(lock)
    comment(e, "K0", "Cà Mau", lock)
    comment(e, "K1", "không về", lock)
    assert e.bus.seat_of("k0") is not None and e.bus.seat_of("k1") is not None and e.lane_of_uid("cho")
    assert any(ev["type"] == "loxe" for ev in e.drain())
    early = Engine(0.0)
    comment(early, "An", "Hà Nội", 1)
    comment(early, "An", "Cà Mau", 2)  # còn lâu mới chạy: đổi được
    assert early.bus.seat_of("an") is None or early.viewers["an"].province == "camau"


def test_empty_bus_turns_to_lane_with_waiting_people():
    e = Engine(0.0)
    e.queues["south"].append("ca")
    e.viewer("ca", "Cà").province = "camau"
    e.viewers["ca"].last_seen = 1
    e.queued_at["ca"] = 1
    assert e.bus.lane == "north" and not e.bus.riders()
    run_until(e, "DRIVING", 1)
    assert e.bus.lane == "south"


def test_home_province_releases_ticket():
    e = Engine(0.0)  # bến TP.HCM
    comment(e, "An", "Huế", 1)
    comment(e, "An", "Sài Gòn", 2)
    assert e.bus.seat_of("an") is None and e.board["hue"] == 0 and e.board["hcm"] == 1


def test_same_lane_switch_keeps_queue_position():
    e = Engine(0.0)
    for i in range(SEATS):
        comment(e, f"K{i}", "Hà Nội", 1)
    for name in ("A", "B", "C"):
        comment(e, name, "Hà Nội", 2)
    comment(e, "A", "Nghệ An", 3)
    assert e.queues["north"] == ["a", "b", "c"]


def test_short_trip_has_no_rest_stop():
    e = Engine(0.0)
    comment(e, "An", "Bình Dương", 1)
    run_until(e, "DRIVING", 1)
    assert e.trip.total < REST_MIN_KM and not any(leg.kind == "rest" for leg in e.legs)


def test_rest_stop_is_named_after_place_on_the_road():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    run_until(e, "REST", 1)
    rest = [ev for ev in e.drain() if ev["type"] == "rest"][0]
    assert rest["place"] and e.snapshot()["place"] == rest["place"]


def test_long_trip_drive_is_compressed_but_km_real():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    run_until(e, "DRIVING", 1)
    drive = sum(max(6.0, (leg.km - (e.legs[i - 1].km if i else 0)) / e._kmps(e.trip.total))
                for i, leg in enumerate(e.legs))
    assert drive <= e.trip_minutes * 60 + 6 * len(e.legs)
    assert e.snapshot()["bus"]["km"] == e.network.km("hanoi")


def test_far_trips_take_clearly_longer_and_minutes_are_adjustable():
    """PLAN-130: xa lâu hơn rõ rệt (không còn trần 4 phút chung), «dài nhất» admin chỉnh được."""
    e = Engine(0.0)
    near, mid, far = (e.drive_seconds(km) for km in (300, 900, 1700))
    assert 110 < near < 150 and 260 < mid < 320 and 440 < far <= 480
    assert far / near > 3
    assert e.drive_seconds(20) == 45.0
    e.trip_minutes = 4
    assert e.drive_seconds(1700) < far / 1.9


def test_rush_is_per_direction():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    for i in range(30):
        comment(e, f"S{i}", "Cà Mau", 1)  # đông hướng Nam, xe đang đón hướng Bắc
    assert not e.rush()


def test_extend_during_special_extends_resumed_phase():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    e.handle({"type": "gift", "name": "Bo", "diamonds": 1000}, 2)
    e.tick(2.5)
    before_special, before_resume = e.phase_until, e.resume[1]
    e.extend(60)
    assert e.phase_until == before_special and e.resume[1] == before_resume + 60


def test_stay_and_home_spam_shows_once_per_cooldown():
    e = Engine(0.0)
    for t in (1, 2, 3):
        comment(e, "An", "không về", t)
    comment(e, "An", "không về", 1 + NOTICE_COOLDOWN + 1)
    assert types(e.drain()).count("stay") == 2


def test_queue_is_on_screen_with_next_lane():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)
    snap = e.snapshot()
    assert snap["next_lane"]["label"] == "Hướng Nam"
    assert snap["queue"][0]["name"] == "Út" and snap["queue"][0]["pos"] == 1


def test_eta_in_finish_includes_boarding_and_counts_phase():
    e = Engine(0.0)
    for i in range(SEATS + 1):
        comment(e, f"K{i}", "Huế", 1)
    run_until(e, "FINISH", 1)
    assert e._eta_minutes(1) == 1 and e._eta_minutes(2) >= 2


def test_trip_follows_road_graph_not_back_to_fork(real_routes):
    """Xe số 2 ngày 01/11 (ảnh anh): 16 tỉnh hướng Hà Nội, mô hình cây cũ vòng 4.441 km (Cao Bằng → quay về chỗ rẽ trước
    Hà Nội → Hòa Bình … Lào Cai → Vĩnh Phúc). Đồ thị đường bộ: không chạy ngược, có tỉnh «đi qua», đoạn nối liền."""
    from xe_tet.server.game.network import Network
    from xe_tet.server.game.provinces import BY_KEY
    net = Network(real_routes, "hcm_miendong")
    key = {p.name: k for k, p in BY_KEY.items()}
    names = ["Lâm Đồng", "Ninh Thuận", "Phú Yên", "Bình Định", "Quảng Trị", "Ninh Bình", "Hà Nam", "Hưng Yên", "Hà Nội",
             "Hải Dương", "Cao Bằng", "Hòa Bình", "Tuyên Quang", "Yên Bái", "Lào Cai", "Vĩnh Phúc"]
    trip = net.plan([key[n] for n in names])
    order = [BY_KEY[k].name for k, _ in trip.stops]
    assert sorted(order) == sorted(names) and trip.total < 3500  # thật ~2.800–2.900 km; mô hình cây cũ 4.441
    assert order.index("Vĩnh Phúc") < order.index("Lào Cai") and order.index("Hà Nội") < order.index("Cao Bằng")
    via = [k for k, _ in trip.via]
    assert "thanhhoa" in via and "nghean" in via and not set(via) & {k for k, _ in trip.stops} and len(via) == len(set(via))
    assert all(abs(a.odo1 - b.odo0) < 1e-6 for a, b in itertools.pairwise(trip.segments))
    assert net.plan(["hanoi"]).total == net.km("hanoi")  # một tỉnh: đúng tuyến OSRM, khớp km trên vé
    assert trip.at(trip.total - 1)[0] in net.profiles  # khúc cuối nằm trên một tuyến thật (đèo / hầm / cảnh vùng đúng)


def test_every_province_has_a_specialty():
    from xe_tet.server.game.provinces import PROVINCE_SPECIALTIES
    assert {p.key for p in PROVINCES} == set(PROVINCE_SPECIALTIES)


def test_rest_stop_sells_local_specialty():
    from xe_tet.server.game.provinces import BY_KEY, specialty_of
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    run_until(e, "REST", 1)
    rest = [ev for ev in e.drain() if ev["type"] == "rest"][0]
    place = next(p for p in BY_KEY.values() if p.name == rest["place"])
    assert rest["specialty"] == specialty_of(place.key) == e.snapshot()["specialty"]


def test_pass_climbs_before_summit_then_descends():
    """Đèo Thử (mạng giả lập) ở km(Hà Nội) − 120: trước đỉnh xe leo (+1), qua đỉnh đổ dốc (−1)."""
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    run_until(e, "DRIVING", 1)
    summit = e.network.routes["hanoi"].passes[0].km
    seen = set()
    t = 1.0
    while e.phase != "DROPOFF" and t < 5000:
        t += 0.5
        e.tick(t)
        terrain = e.snapshot()["terrain"]
        if terrain["pass"]:
            route, km = e.trip.at(e.trip_km())
            seen.add((terrain["climb"], km < summit))
    assert (1, True) in seen and (-1, False) in seen and (1, False) not in seen


def test_pass_lasts_long_enough_to_see():
    """Đoạn đèo (±8 km) kéo dài ít nhất PASS_SECONDS dù nén 3+ km / giây."""
    from xe_tet.server.game.engine import PASS_SECONDS
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    run_until(e, "DRIVING", 1)
    t, on_pass = 1.0, 0.0
    while e.phase != "DROPOFF" and t < 5000:
        t += 0.25
        e.tick(t)
        if e.phase == "DRIVING" and e.snapshot()["terrain"]["pass"]:
            on_pass += 0.25
    assert on_pass >= PASS_SECONDS - 1



# ---- xe tăng cường (PLAN-125) ---------------------------------------------

def fill_lane(e, lane_province, n, t, prefix="Q"):
    for i in range(n):
        comment(e, f"{prefix}{i}", lane_province, t)


def test_relief_departs_when_lane_has_a_busload_waiting(monkeypatch):
    monkeypatch.setattr("xe_tet.server.game.engine.RELIEF_AUTO", True)  # PLAN-144: tắt mặc định, máy giữ cho admin
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)  # xe chính đón hướng Bắc
    fill_lane(e, "Cà Mau", SEATS, 2)  # đủ một xe hướng Nam đang chờ
    e.tick(2.5)
    departs = [ev for ev in e.drain() if ev["type"] == "relief_depart"]
    assert len(departs) == 1 and departs[0]["count"] == SEATS and departs[0]["sponsor"] is None
    assert e.waiting() == 0 and len(e.reliefs) == 1 and e.snapshot()["reliefs"][0]["riders"] == SEATS


def test_relief_drops_everyone_with_names_and_counts(monkeypatch):
    monkeypatch.setattr("xe_tet.server.game.engine.RELIEF_AUTO", True)  # PLAN-144: tắt mặc định, máy giữ cho admin
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    fill_lane(e, "Cà Mau", SEATS, 2)
    t = 2.5
    e.tick(t)
    dropped = []
    while e.reliefs and t < 3000:
        t += 1
        e.tick(t)
        dropped += [p["name"] for ev in e.drain() if ev["type"] == "relief_dropoff" for p in ev["people"]]
    assert sorted(dropped) == sorted(f"Q{i}" for i in range(SEATS))
    assert e.delivered == SEATS and all(e.viewers[f"q{i}"].province is None for i in range(SEATS))


def test_big_gift_sends_no_other_vehicle_only_one_bus():
    """Anh 03/11 «mình làm gì có máy bay đâu, mình chỉ có 1 xe 24 chỗ»: quà lớn không đưa ai về quê bằng xe khác, không
    sinh xe tăng cường — người tặng đang chờ thì lên đầu hàng; tặng trước rồi mới gõ tỉnh cũng được xếp đầu hàng."""
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    fill_lane(e, "Cà Mau", 5, 2)
    comment(e, "Út", "Bạc Liêu", 3)
    e.drain()
    e.handle({"type": "gift", "name": "Út", "diamonds": 500}, 4)
    events = e.drain()
    assert not [ev for ev in events if ev["type"] in ("ride_home", "relief_depart")] and not e.reliefs
    assert e.waiting() == 6 and e.queues["south"][0] == "út" and e.delivered == 0
    e.handle({"type": "gift", "name": "Lạ", "diamonds": 1}, 5)  # chưa có vé
    comment(e, "Lạ", "Cà Mau", 6)
    assert e.queues["south"][:2] == ["út", "lạ"]


def test_top_gifters_are_owner_and_deputy():
    e = Engine(0.0)
    e.handle({"type": "gift", "name": "A", "diamonds": 5}, 1)
    e.handle({"type": "gift", "name": "B", "diamonds": 9}, 2)
    e.handle({"type": "gift", "name": "A", "diamonds": 7}, 3)
    patrons = [ev for ev in e.drain() if ev["type"] == "patron"]
    assert [p["name"] for p in patrons] == ["A", "B", "A"]  # đổi chủ thì báo
    assert e.snapshot()["patrons"] == [{"name": "A", "xu": 12}, {"name": "B", "xu": 9}]


def test_relief_respects_limit_and_blocks_departure_switch(monkeypatch):
    monkeypatch.setattr("xe_tet.server.game.engine.RELIEF_AUTO", True)  # PLAN-144: tắt mặc định, máy giữ cho admin
    import pytest
    from xe_tet.server.game.engine import RELIEF_MAX
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    fill_lane(e, "Cà Mau", SEATS * (RELIEF_MAX + 1), 2)
    e.tick(2.5)
    assert len(e.reliefs) == RELIEF_MAX and e.waiting() == SEATS
    with pytest.raises(ValueError):
        e.set_departure("dalat")


def test_relief_rider_is_in_exactly_one_place(monkeypatch):
    monkeypatch.setattr("xe_tet.server.game.engine.RELIEF_AUTO", True)  # PLAN-144: tắt mặc định, máy giữ cho admin
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    fill_lane(e, "Cà Mau", SEATS, 2)
    e.tick(2.5)
    comment(e, "Q0", "Hà Nội", 3)  # đang trên xe tăng cường: không đổi tỉnh, không giữ chỗ thêm
    assert e.lane_of_uid("q0") is None and e.bus.seat_of("q0") is None
    assert any("q0" in r.riders for r in e.reliefs)


def test_featured_relief_drives_screen_then_returns_to_main():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)
    relief = e.add_relief("south")
    e.feature(relief.no)
    snap = e.snapshot()
    assert snap["bus"]["no"] == relief.no and snap["phase"] == "DRIVING" and snap["main"]["phase"] == "BOARDING"
    assert snap["bus"]["seats"][0]["name"] == "Út" and snap["legs"][-1]["label"] == "Cà Mau"
    t = 2.0
    while e.reliefs and t < 3000:
        t += 1
        e.tick(t)
    assert e.featured is None and e.snapshot()["bus"]["no"] == e.bus.no


# ---- nhạc trong xe (PLAN-127) ----------------------------------------------

def test_each_bus_has_its_own_music_and_screen_follows_featured():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)
    relief = e.add_relief("south")
    pick = lambda m: {k: m[k] for k in ("index", "on")}  # noqa: E731
    assert pick(e.snapshot()["music"]) == {"index": 0, "on": True}  # đang chiếu xe chính
    e.music_step(0)
    e.music_toggle(relief.no)
    e.feature(relief.no)
    snap = e.snapshot()
    assert pick(snap["music"]) == {"index": relief.no, "on": False}  # tiếng theo xe đang chiếu
    assert snap["main"]["music"]["index"] == 1 and snap["reliefs"][0]["music"]["on"] is False



def test_each_bus_radio_advances_when_song_ends():
    """Mỗi xe một đài chạy liên tục: hết bài thì tự sang bài kế, kể cả xe không lên màn hình; tắt tự qua bài thì đứng."""
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)
    relief = e.add_relief("south")
    e.music_set(0, 0)
    e.music_set(relief.no, 1)
    lengths = [10.0, 20.0, 30.0]
    e.tick(5)
    e.advance_music(lengths, auto=True)
    assert e.music_of("main")["index"] == 0 and e.snapshot()["music"]["pos"] == 5
    e.tick(12)
    e.advance_music(lengths, auto=True)
    main, other = e.music_of("main"), e.music_of(str(relief.no))
    assert main["index"] == 1 and main["since"] == 10  # bài 2 bắt đầu đúng lúc bài 1 hết
    assert other["index"] == 1  # bài 20 giây của xe tăng cường chưa hết
    e.tick(40)
    e.advance_music(lengths, auto=False)
    assert e.music_of("main")["index"] == 1  # tắt tự qua bài: đứng yên (bài lặp lại)


# ---- đồng hồ trên xe, bảng chặng, tự chiếu xe (PLAN-130) ----------------------

def test_bus_clock_runs_the_hours_the_loxe_says():
    from datetime import timedelta
    from xe_tet.server.game.engine import REST_HOURS
    from xe_tet.server.game.network import Network
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Bình", "Nghệ An", 1)
    t = run_until(e, "DRIVING", 1)
    route = e.snapshot()["route"]
    stops = route["stops"]
    assert [s["done"] for s in stops] == [False] * len(stops)
    waits = [s["in_s"] for s in stops]
    assert waits == sorted(waits) and waits[0] > 0
    rests = 0
    for stop, leg in zip(stops, e.legs):  # giờ tới mỗi điểm = giờ xuất bến + km / 52 km/h + 30 phút mỗi trạm trước đó
        at = e.clock0 + timedelta(hours=Network.hours(leg.km) + REST_HOURS * rests)
        assert stop["at"] == at.strftime("%H:%M") and stop["day"] == (at.date() - e.clock0.date()).days
        rests += leg.kind == "rest"
    start = route["clock"]["hour"]
    run_until(e, "FINISH", t)
    hours = Network.hours(e.trip.total) + REST_HOURS * sum(leg.kind == "rest" for leg in e.legs)
    end = e.snapshot()["route"]["clock"]
    assert abs((end["hour"] + 24 * end["day"] - start) - hours) < 0.05  # đồng hồ chạy đủ số giờ của chuyến


def test_fleet_lists_every_bus_with_next_stop():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)
    relief = e.add_relief("south")
    fleet = e.snapshot()["fleet"]
    assert [b["no"] for b in fleet] == [e.bus.no, relief.no]
    assert fleet[0]["phase"] == "BOARDING" and fleet[0]["in_s"] > 0
    assert fleet[1]["next"] == "Cà Mau" and fleet[1]["in_s"] > 0 and fleet[1]["clock"]
    e.feature(relief.no)
    snap = e.snapshot()
    assert snap["route"]["stops"][-1]["name"] == "Cà Mau" and snap["fleet"][1]["featured"]


def drive_with_director(e, mode, t, until, rotate=60.0):
    seen = []
    while t < until:
        t += 1
        e.tick(t)
        e.auto_feature(mode, rotate)
        seen.append((e.featured, e._phase_now()))
    return t, seen


def test_auto_feature_follows_relief_dropoff_then_returns_to_main():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)
    e.skip()
    e.tick(3)
    assert e.phase == "DRIVING"
    relief = e.add_relief("south")
    _, seen = drive_with_director(e, "events", 3, 2000)
    shown = [phase for no, phase in seen if no == relief.no]
    assert shown and set(shown) == {"DRIVING"}  # chỉ chiếu xe tăng cường lúc xe chính đang chạy (không có cảnh riêng)
    assert seen[-1][0] is None  # xong thì về xe chính
    rest_or_drop = [no for no, phase in seen if phase in ("REST", "DROPOFF", "BOARDING")]
    assert set(rest_or_drop) <= {None}  # cảnh của xe chính luôn là xe chính


def test_manual_feature_pauses_director_and_rotate_mode_cycles():
    from xe_tet.server.game.engine import MANUAL_HOLD
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)
    relief = e.add_relief("south")
    e.tick(3)
    e.feature(relief.no)  # admin bấm tay
    _, seen = drive_with_director(e, "rotate", 3, 3 + MANUAL_HOLD - 5, rotate=10)
    assert {no for no, _ in seen} == {relief.no}
    _, seen = drive_with_director(e, "rotate", 3 + MANUAL_HOLD, 3 + MANUAL_HOLD + 40, rotate=10)
    assert {no for no, _ in seen} == {None, relief.no}  # hết giờ nhường admin: xoay vòng mỗi 10 giây
    e.auto_feature("off", 10)


def test_on_air_by_stage_score_gifter_bus_shown_longer_and_others_get_turns(monkeypatch):
    """PLAN-141: xe chính chỉ đang chạy → chiếu xe tăng cường nhiều điểm (quà 3 / xu, bình luận 1, tim 50 = 1) trước và lâu hơn
    (15 giây + điểm, tối đa SHOW_MAX), về xe chính ≥ FEATURE_MIN_SECONDS, rồi xe ít điểm cũng tới lượt; cảnh xe chính vẫn ưu tiên."""
    from xe_tet.server.game.engine import FEATURE_MIN_SECONDS, SHOW_BASE, SHOW_MAX
    monkeypatch.setattr("xe_tet.server.game.engine.TURBO_PER_XU", 0.0)  # quà tăng tốc xe chính làm lệch giờ của bài thử này
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 1)
    rich = e.add_relief("south")
    comment(e, "Bình", "Cà Mau", 2)  # cùng điểm xa: xe ít điểm còn chạy tới lượt mình
    poor = e.add_relief("south")
    e.handle({"type": "gift", "name": "Út", "diamonds": 100}, 2)
    assert e.stage_of(rich) > e.stage_of(poor)
    e.skip()
    e.tick(3)
    e.drain()
    t, seen = drive_with_director(e, "events", 3, 260)
    events = e.drain()
    runs = []  # (xe, số giây liền)
    for no, _ in seen:
        if runs and runs[-1][0] == no:
            runs[-1][1] += 1
        else:
            runs.append([no, 1])
    shown = [r for r in runs if r[0] is not None]
    assert shown[0][0] == rich.no and shown[0][1] >= SHOW_MAX - 2  # xe có quà lên trước, đủ lượt dài nhất
    assert any(no == poor.no and n <= SHOW_BASE + 2 for no, n in shown)  # xe ít điểm vẫn có lượt ngắn
    mains = [n for no, n in runs[1:-1] if no is None]
    assert all(n >= FEATURE_MIN_SECONDS for n in mains)  # giữa hai lượt, xe chính ít nhất 20 giây
    air = [ev for ev in events if ev["type"] == "on_air"]
    assert air and air[0]["bus_no"] == rich.no and air[0]["names"][0] == "Út"
    assert {no for no, phase in seen if phase != "DRIVING"} <= {None}  # cảnh của xe chính luôn là xe chính


def test_stage_score_caps_comment_spam():
    from xe_tet.server.game.engine import STAGE_COMMENTS_MAX
    e = Engine(0.0)
    for i in range(STAGE_COMMENTS_MAX + 20):
        e.handle({"type": "comment", "name": "Spam", "text": f"hello {i}"}, 1 + i)
    e.handle({"type": "like", "name": "Spam", "count": 100}, 100)
    assert e.viewers["spam"].stage == STAGE_COMMENTS_MAX + 2


def test_loxe_follows_the_bus_on_screen(monkeypatch):
    """PLAN-142 (anh báo 02/11): chiếu xe tăng cường thì lơ xe không đọc chỗ của xe chính — câu nhỏ (qua tỉnh, bóp còi) bỏ,
    câu khác ghi rõ «Xe số N.»; chuyển xe thì giới thiệu xe đang chiếu, quay về thì báo về xe chính."""
    import xe_tet.server.game.engine as eng
    monkeypatch.setattr(eng, "line", lambda kind, rng=None, style="mix", **fields: kind)
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 1)
    relief = e.add_relief("south")
    e.skip()
    e.tick(3)
    e.drain()
    e.feature(relief.no)
    said = []
    t = 3
    while t < 400 and e.featured == relief.no:
        t += 1
        e.tick(t)
        said += [ev["text"] for ev in e.drain() if ev["type"] == "loxe"]
    e.feature(None)
    said_back = [ev["text"] for ev in e.drain() if ev["type"] == "loxe"]
    assert "via" not in said and "honk" not in said  # câu nhỏ của xe chính: không nói khi không lên hình
    main_kinds = {"rest", "depart", "finish", "parcels", "pickup", "pickup_wait", "passed"}  # (thả khách: xe đang chiếu)
    assert not [x for x in said if x in main_kinds]  # câu của xe chính đều có «Xe số N.» ở đầu
    assert "screen_main" in said + said_back  # xe tăng cường tới bến cuối hoặc admin chuyển về: lơ xe báo về xe chính


def test_loxe_introduces_featured_relief():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 1)
    relief = e.add_relief("south")
    e.tick(2)
    e.drain()
    e.feature(relief.no)
    text = next(ev["text"] for ev in e.drain() if ev["type"] == "loxe")
    assert f"{relief.no}" in text and "Cà Mau" in text


def test_rules_reminder_every_three_minutes_or_after_newcomers():
    from xe_tet.server.game.engine import RULES_GAP, RULES_MIN_GAP, RULES_JOINS
    e = Engine(0.0)
    for i in range(RULES_JOINS):
        e.handle({"type": "join", "name": f"Mới {i}"}, 1)
    e.tick(RULES_MIN_GAP - 1)
    e.drain()
    e.tick(RULES_MIN_GAP + 1)
    assert e.last_rules == RULES_MIN_GAP + 1  # đủ người mới + qua 1 phút: đọc luật
    e.tick(RULES_MIN_GAP + 100)
    assert e.last_rules == RULES_MIN_GAP + 1  # không có người mới: chờ đủ 3 phút
    e.tick(RULES_MIN_GAP + 1 + RULES_GAP)
    assert e.last_rules == RULES_MIN_GAP + 1 + RULES_GAP


def test_each_gift_has_its_own_effect():
    """PLAN-142: hiệu ứng theo tên món, không khớp thì theo giá một món; món đắt không bao giờ hiệu ứng nhỏ; sự kiện quà mang fx."""
    from xe_tet.server.game.engine import gift_fx
    assert gift_fx("Rose", 1) == ("petals", 1) and gift_fx("Rose ×5", 5) == ("petals", 5)
    assert gift_fx("TikTok", 1)[0] == "honk" and gift_fx("Finger Heart", 5)[0] == "hearts"
    assert gift_fx("Hoa hồng", 1)[0] == "petals" and gift_fx("Ultimate", 10)[0] == "firework"  # «tim» trong chữ khác không tính
    assert gift_fx("Doughnut", 30)[0] == "lixi" and gift_fx("Hand Hearts", 100)[0] == "lantern"
    e = Engine(0.0)
    e.handle({"type": "gift", "name": "An", "diamonds": 3, "gift": "Rose ×3"}, 1)
    ev = next(x for x in e.drain() if x["type"] == "gift")
    assert ev["fx"] == "petals" and ev["fx_n"] == 3


def test_parser_understands_natural_booking_and_typos_but_not_chat():
    """Rà soát 02/11: câu đặt vé tự nhiên, tên viết liền, gõ sai một chữ đều lên xe; câu tán gẫu vẫn là tán gẫu."""
    from xe_tet.server.game.parser import parse
    ok = {"cho em 1 vé về Thanh Hóa": "Thanh Hóa", "1 vé Huế": "Huế", "đặt vé đi Đà Nẵng": "Đà Nẵng", "Hanoi": "Hà Nội",
          "nghệan": "Nghệ An", "Nghe Ann": "Nghệ An", "nge an": "Nghệ An", "dac lak": "Đắk Lắk"}
    for text, prov in ok.items():
        cmd = parse(text)
        assert cmd.kind == "province" and cmd.province.name == prov, text
    for text in ("lên xe", "cho lên xe với", "về quê", "đăng ký"):
        assert parse(text).kind == "board", text
    for text in ("Hà Nội lạnh quá", "chị Huệ ơi", "anh vinh ơi đẹp quá", "mẹ chưa về à", "đường về Hà Nội xa quá", "hello",
                 "cảm ơn", "Nghe nói", "nam ơi", "xin chao", "đi"):
        assert parse(text).kind == "chat", text


def test_every_booking_comment_gets_a_visible_answer():
    """Rà soát 02/11: gõ lại đúng tỉnh, đổi tỉnh lần hai, đang trên xe chạy gõ tỉnh → thẻ vé (trước đây im lặng); «lên xe»
    không nói tỉnh → khách quen về quê cũ, người mới được lơ xe chỉ cách gõ."""
    e = Engine(0.0)
    comment(e, "An", "Nghệ An", 1)
    e.drain()
    comment(e, "An", "Nghệ An", 30)
    assert [ev["type"] for ev in e.drain()] == ["where"]
    comment(e, "An", "Huế", 50)
    e.drain()
    comment(e, "An", "Quảng Bình", 70)  # đổi lần hai: không đổi nữa nhưng vẫn thấy vé
    assert [ev["type"] for ev in e.drain()] == ["where"]
    comment(e, "Bình", "lên xe", 71)
    assert any(ev["type"] == "loxe" and "Bình" in ev["text"] for ev in e.drain())
    e.viewer("chi", "Chi").home = "hue"
    comment(e, "Chi", "về quê", 90)
    assert e.viewers["chi"].province == "hue"
    e.skip()
    e.tick(100)
    e.drain()
    comment(e, "An", "Huế", 120)  # đang trên xe chạy
    assert [ev["type"] for ev in e.drain()] == ["where"]


def test_queued_rider_is_told_when_moved_onto_a_bus():
    """Live 02/11: 45 người giữ chỗ chuyến sau được xếp lên xe trong im lặng — thẻ vẫn ghi «chuyến sau». Giờ: xếp lên xe chính
    hay xe tăng cường đều có vé mới (promoted) cho đúng người."""
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    e.skip()
    e.tick(3)
    assert e.phase == "DRIVING"
    e.drain()
    comment(e, "Bình", "Cà Mau", 4)  # xe đang chạy hướng khác: giữ chỗ chuyến sau
    (held,) = [ev for ev in e.drain() if ev["type"] == "ticket"]
    assert held["next"] is True
    relief = e.add_relief("south")
    (moved,) = [ev for ev in e.drain() if ev["type"] == "ticket" and ev["name"] == "Bình"]
    assert moved["relief"] and moved["promoted"] and not moved["next"] and moved["bus_no"] == relief.no
    comment(e, "Chi", "Bạc Liêu", 5)  # khác hướng, không có xe tăng cường: chờ chuyến sau thật
    e.drain()
    run_until(e, "BOARDING", 6)  # chuyến sau vào bến (làn có người chờ) → Chi được xếp giường
    boarded = [ev for ev in e.drain() if ev["type"] == "ticket" and ev["name"] == "Chi"]
    assert e.bus.seat_of("chi") is not None
    assert boarded and boarded[-1]["promoted"] and boarded[-1]["seat"] == e.bus.seat_of("chi") and not boarded[-1]["next"]


def test_this_trip_reminder_skips_provinces_already_on_a_bus():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)  # khác hướng: vào danh sách nhắc
    e.add_relief("south")  # Út lên xe tăng cường
    e.drain()
    e.tick(60)
    assert not [ev for ev in e.drain() if ev["type"] == "loxe" and "Cà Mau" in ev["text"]]


def test_manifest_shows_who_is_on_which_bus_and_queue():
    """Rà soát 02/11: anh không biết người xem nào ở xe nào — /control đọc danh sách này."""
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Út", "Cà Mau", 2)
    comment(e, "Ba", "Bạc Liêu", 3)
    relief = e.add_relief("south")
    comment(e, "Tư", "Cà Mau", 4)
    m = e.manifest()
    main, rel = m["buses"]
    assert main["main"] and [r["name"] for r in main["riders"]] == ["An"] and main["riders"][0]["seat"] == 1
    assert rel["no"] == relief.no and {r["name"] for r in rel["riders"]} == {"Út", "Ba"}
    (q,) = m["queues"]
    assert q["people"] == [{"name": "Tư", "province": "Cà Mau", "pos": 1}]


def test_waiting_gifter_jumps_to_front_once_until_boarding():
    """PLAN-144 (anh chọn «quà giúp chính mình»): đang chờ chuyến sau mà tặng quà → lên đầu hàng làn mình, sau người tặng
    trước; tặng thêm không nhảy nữa; đã có giường mà tặng → VIP (giường vàng)."""
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    for i, name in enumerate(("Ba", "Bốn", "Năm")):
        comment(e, name, "Cà Mau", 2 + i)
    q = e.queues["south"]
    assert q == ["ba", "bốn", "năm"]
    e.handle({"type": "gift", "name": "Năm", "diamonds": 1}, 6)
    assert q == ["năm", "ba", "bốn"]
    gift = [ev for ev in e.drain() if ev["type"] == "gift"][-1]
    assert "lên đầu hàng" in gift["perk"] and "thứ 1" in gift["perk"]
    e.handle({"type": "gift", "name": "Bốn", "diamonds": 1}, 7)
    assert q == ["năm", "bốn", "ba"]  # sau người tặng trước
    e.handle({"type": "gift", "name": "Bốn", "diamonds": 5}, 8)
    assert q == ["năm", "bốn", "ba"]  # một lần tới khi lên xe
    e.handle({"type": "gift", "name": "An", "diamonds": 1}, 9)
    assert e.viewers["an"].vip


# ---- PLAN-134 B: người xem biết mình ở xe nào --------------------------------

def test_where_question_is_not_a_booking():
    """«vé» bỏ dấu trùng «về»: «về Huế» / «vé Huế» vẫn là đặt vé; «vé», «xe nào», «tới đâu rồi» là hỏi vé."""
    from xe_tet.server.game.parser import parse
    for text in ("xe nào", "Xe số mấy vậy", "vé", "vé của tôi", "tới đâu rồi", "bao giờ tới Huế", "còn bao lâu nữa", "xe"):
        assert parse(text).kind == "where", text
    for text in ("về Huế", "ve Hue", "Huế", "vé Huế"):
        assert parse(text).kind == "province", text
    assert parse("xe đẹp quá").kind == "chat" and parse("không về").kind == "stay"


def test_where_answers_seat_queue_and_none():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    comment(e, "Bình", "Cà Mau", 2)  # khác hướng: giữ chỗ xe sau
    e.drain()
    comment(e, "An", "xe nào", 3)
    comment(e, "Bình", "tới đâu rồi", 3)
    comment(e, "Chi", "vé", 3)
    answers = {ev["name"]: ev for ev in e.drain() if ev["type"] == "where"}
    assert answers["An"]["status"] == "seat" and answers["An"]["bus_no"] == e.bus.no and answers["An"]["phase"] == "BOARDING"
    assert answers["An"]["depart_in"] > 0 and answers["An"]["province"] == "Hà Nội"
    assert answers["Bình"]["status"] == "queue" and answers["Bình"]["position"] == 1 and answers["Bình"]["eta_min"] >= 1
    assert answers["Bình"]["bus_no"] > e.bus.no
    assert answers["Chi"]["status"] == "none"
    comment(e, "An", "xe nào", 10)  # hỏi lại trong 15 giây: không chiếm thêm thẻ trên màn hình
    assert not [ev for ev in e.drain() if ev["type"] == "where"]
    t = run_until(e, "DRIVING", 10)
    comment(e, "An", "còn bao lâu", t + 1)
    ans = next(ev for ev in e.drain() if ev["type"] == "where")
    assert ans["status"] == "seat" and ans["in_s"] > 0 and ans["stops_before"] >= 0


def test_bus_greets_provinces_it_passes(real_routes):
    """Xe chạy qua tỉnh không ai xuống: lơ xe gọi bà con tỉnh đó, cách nhau ≥ VIA_TALK_GAP giây (PLAN-134)."""
    from xe_tet.server.game.engine import VIA_TALK_GAP
    from xe_tet.server.game.network import Network
    e = Engine(0.0, network=Network(real_routes, "hcm_miendong"))
    comment(e, "An", "Hà Nội", 1)
    t = run_until(e, "DRIVING", 1)
    seen = []
    while e.phase == "DRIVING" and t < 3000:
        t += 0.5
        e.tick(t)
        seen += [(t, ev) for ev in e.drain() if ev["type"] == "via"]
    via = {BY_KEY[k].name for k, _ in e.trip.via}
    assert len(seen) >= 2 and all(ev["province"] in via for _, ev in seen)
    assert all(b - a >= VIA_TALK_GAP for (a, _), (b, _) in itertools.pairwise(seen))


def test_bus_picks_up_provinces_on_its_way(real_routes):
    """PLAN-134 C: khách Huế (làn «Hướng Đà Nẵng») lên được xe «Hướng Hà Nội» còn giường — xe đi ngang Huế; người đã giữ chỗ
    làn khác mà xe đi ngang quê họ cũng được xếp lên; tỉnh ngược đường (Cà Mau) vẫn chờ xe làn mình."""
    from xe_tet.server.game.network import Network
    net = Network(real_routes, "hcm_miendong")
    assert net.lane_of("hue") != net.lane_of("hanoi") and "hue" in net.serves(net.lane_of("hanoi"))
    assert "camau" not in net.serves(net.lane_of("hanoi"))
    e = Engine(0.0, network=net)
    comment(e, "Cà", "Cà Mau", 1)  # xe quay đầu hướng Cà Mau
    comment(e, "Huệ", "Huế", 2)  # khác đường: giữ chỗ
    assert e.lane_of_uid("huệ") == net.lane_of("hue")
    e.bus.lane = net.lane_of("hanoi")  # chuyến sau chạy hướng Hà Nội: người Huế đang giữ chỗ được xếp lên luôn
    e._fill_from_queue()
    assert e.bus.seat_of("huệ") is not None and e.lane_of_uid("huệ") is None
    e2 = Engine(0.0, network=net)
    comment(e2, "An", "Hà Nội", 1)
    comment(e2, "Huệ", "Huế", 2)
    comment(e2, "Út", "Cà Mau", 3)
    seated = {e2.viewers[u].province for u in e2.bus.riders()}
    assert seated == {"hanoi", "hue"} and e2.lane_of_uid("út") == net.lane_of("camau")
    ticket = next(ev for ev in e2.drain() if ev["type"] == "ticket" and ev["province"] == "Huế")
    assert ticket["lane"] == "Hướng Hà Nội" and not ticket["next"]


def test_season_calendar_2027():
    """Tết Đinh Mùi: mùng 1 = 6/2/2027, tháng Chạp thiếu (giao thừa 29 Chạp = 5/2); cao điểm 23–28 Chạp; chiều ra mùng 4–10."""
    from xe_tet.server.game import season
    assert season.lunar_label(date(2027, 2, 5)) == "Giao thừa" and season.phase(date(2027, 2, 5)) == season.EVE
    assert season.lunar_label(date(2027, 2, 1)) == "25 Chạp" and season.phase(date(2027, 2, 1)) == season.PEAK
    assert season.chap(23) == date(2027, 1, 30) and season.phase(date(2027, 1, 29)) == season.EARLY
    assert season.lunar_label(date(2027, 2, 7)) == "Mùng 2 Tết" and season.phase(date(2027, 2, 9)) == season.RETURN
    assert season.lunar_label(date(2026, 12, 15)) is None and season.phase(date(2027, 2, 16)) == season.AFTER
    e = Engine(0.0, today=date(2027, 2, 1))
    assert e.snapshot()["season"] == {"phase": "peak", "lunar": "25 Chạp", "days_to_tet": 5}
    e.drain()
    e._enter_boarding(1.0)
    assert any("25 Chạp" in ev.get("text", "") or "Cao điểm" in ev.get("text", "") or "Bến đông" in ev.get("text", "")
               for ev in e.drain() if ev["type"] == "loxe")


def test_gift_parcels_ride_with_ticket_and_reach_the_gate():
    """PLAN-134 C: tặng quà lúc có vé → thùng quà mang tên lên gầm xe (tối đa PARCELS_MAX), tới quê ôm vào cổng + lơ xe gọi
    tên; chưa có vé thì không có thùng (quyền lợi quà cũ giữ nguyên)."""
    from xe_tet.server.game.engine import PARCELS_MAX
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    for i in range(PARCELS_MAX + 2):
        e.handle({"type": "gift", "name": "An", "diamonds": 1}, 2 + i)
    e.handle({"type": "gift", "name": "Khách", "diamonds": 1}, 9)
    gifts = [ev for ev in e.drain() if ev["type"] == "gift"]
    assert [g["parcel"] for g in gifts] == [True] * PARCELS_MAX + [False, False, False]
    assert e.snapshot()["bus"]["parcels"] == PARCELS_MAX
    run_until(e, "DROPOFF", 10)
    events = e.drain()
    drop = next(ev for ev in events if ev["type"] == "dropoff")
    assert drop["people"][0]["parcels"] == PARCELS_MAX and e.viewers["an"].parcels == 0
    assert any(ev["type"] == "loxe" and "An" in ev["text"] for ev in events)


def test_returning_viewer_is_remembered_and_greeted(tmp_path):
    """PLAN-134 D: hồ sơ ghi SQLite theo lô; buổi sau gặp lại → lơ xe chào «đã về … N chuyến» (một lần, cách WELCOME_GAP)."""
    from xe_tet.server.store import ViewerStore
    db = ViewerStore(tmp_path / "x.db")
    e = Engine(0.0, today=date(2026, 12, 20))
    e.recall = db.load
    comment(e, "An", "Hà Nội", 1)
    e.handle({"type": "like", "name": "An", "count": 7}, 2)
    run_until(e, "DROPOFF", 2)
    db.save_many(e.take_dirty())
    assert e.take_dirty() == []
    row = db.load("an")
    assert row["home"] == "hanoi" and row["trips"] == 1 and row["likes"] == 7 and row["comments"] == 1 and row["days"] == 1
    later = Engine(0.0, today=date(2026, 12, 22))  # buổi live khác
    later.recall = db.load
    later.handle({"type": "join", "name": "An"}, 1)  # vào phòng chưa tính
    assert not [ev for ev in later.drain() if ev["type"] == "welcome"]
    later.handle({"type": "like", "name": "An", "count": 1}, 2)
    later.handle({"type": "like", "name": "An", "count": 1}, 3)
    events = later.drain()
    welcome = [ev for ev in events if ev["type"] == "welcome"]
    assert len(welcome) == 1 and welcome[0]["trips"] == 1 and welcome[0]["home"] == "Hà Nội" and welcome[0]["days"] == 2
    assert any(ev["type"] == "loxe" and "An" in ev["text"] for ev in events)
    db.save_many(later.take_dirty())
    assert db.load("an")["likes"] == 9 and db.load("an")["days"] == 2


def test_same_hometown_riders_are_paired():
    e = Engine(0.0)
    comment(e, "An", "Nghệ An", 1)
    e.drain()
    comment(e, "Bình", "Nghệ An", 2)
    assert any(ev["type"] == "loxe" and "An" in ev["text"] and "Bình" in ev["text"] for ev in e.drain())
    comment(e, "Chi", "Nghệ An", 3)  # trong SAME_HOME_GAP: không ghép tiếp (lơ xe không nói liên tục)
    assert not any(ev["type"] == "loxe" and "Chi" in ev["text"] for ev in e.drain())


def test_silent_liker_is_invited_once():
    """Thả tim đều mà chưa có vé → lơ xe gọi tên mời một lần mỗi buổi; người có vé / chọn «không về» không bị mời; biết quê
    từ buổi trước thì mời đúng tỉnh."""
    from xe_tet.server.game.engine import INVITE_GAP, INVITE_LIKES
    e = Engine(0.0)
    e.last_now = 1
    comment(e, "An", "Hà Nội", 1)
    e.drain()
    e.handle({"type": "like", "name": "Bình", "count": INVITE_LIKES - 1}, 1)
    e.handle({"type": "like", "name": "An", "count": INVITE_LIKES}, 1)
    assert not any(ev["type"] == "loxe" for ev in e.drain())  # Bình chưa đủ tim, An có vé rồi
    e.handle({"type": "like", "name": "Bình", "count": 1}, 2)
    assert [ev for ev in e.drain() if ev["type"] == "loxe" and "Bình" in ev["text"]]
    e.last_now = 2 + INVITE_GAP
    e.handle({"type": "like", "name": "Bình", "count": 5}, e.last_now)
    assert not any(ev["type"] == "loxe" for ev in e.drain())  # mỗi người một lần
    e.viewer("chi", "Chi").home = "nghean"
    e.handle({"type": "like", "name": "Chi", "count": INVITE_LIKES}, e.last_now)
    assert any(ev["type"] == "loxe" and "Nghệ An" in ev["text"] for ev in e.drain())
    e.last_now += INVITE_GAP
    comment(e, "Dũng", "không về", e.last_now)
    e.drain()
    e.handle({"type": "like", "name": "Dũng", "count": INVITE_LIKES}, e.last_now)
    assert not any(ev["type"] == "loxe" and "Dũng" in ev["text"] for ev in e.drain())


def test_no_gift_hint_past_top_tier():
    """Đã tới 1000 xu thì không gợi ý «tặng thêm N xu» nữa (không mở vòng tặng không đáy)."""
    e = Engine(0.0)
    e.handle({"type": "gift", "name": "An", "diamonds": 1200}, 1)
    gift = next(ev for ev in e.drain() if ev["type"] == "gift")
    assert gift["next_tier"] == ""


# ---- PLAN-136: bắt xe dọc đường ------------------------------------------------

def _driving_to_hanoi():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    t = run_until(e, "DRIVING", 1)
    e.drain()
    return e, t


def test_roadside_pickup_for_province_still_ahead():
    """Quê còn ở phía trước trên đường xe đi, còn giường → đặt giường, hẹn ra điểm đón (~PICKUP_LEAD giây trước mặt xe),
    xe tới thì «tấp vô đón», tới quê thì trả khách như mọi người."""
    from xe_tet.server.game.engine import PICKUP_LEAD
    e, t = _driving_to_hanoi()
    key, odo = max(e.trip.via, key=lambda pv: pv[1])  # tỉnh đi qua xa nhất trước Hà Nội
    comment(e, "Bình", BY_KEY[key].name, t)
    ticket = next(ev for ev in e.drain() if ev["type"] == "ticket")
    assert ticket["next"] is False and ticket["bus_no"] == e.bus.no and ticket["pickup"] and ticket["pickup_in"] >= PICKUP_LEAD - 1
    assert e.bus.seat_of("bình") is not None and "bình" in e.pickups
    assert any(leg.kind == "stop" and leg.target == key for leg in e.legs) and key not in [k for k, _ in e.trip.via]
    where = e.ticket_of(e.viewers["bình"])
    assert where["status"] == "seat" and where["pickup"] == ticket["pickup"]
    picked = dropped = None
    halted = False
    while e.phase != "FINISH" and t < 5000:
        t += 0.5
        e.tick(t)
        if e.snapshot()["halt"]:
            halted = True
        for ev in e.drain():
            if ev["type"] == "pickup_stop" and any(p["name"] == "Bình" for p in ev["people"]):
                picked = t
            if ev["type"] == "dropoff" and any(p["name"] == "Bình" for p in ev["people"]):
                dropped = (t, ev["province"])
    assert picked and dropped and picked < dropped[0] and dropped[1] == BY_KEY[key].name
    assert halted  # PLAN-145: xe dừng hẳn bên lề lúc đón (snapshot có «halt», tốc độ 0)


def test_province_already_passed_waits_for_next_bus():
    e, t = _driving_to_hanoi()
    while e.trip_km() < e.trip.via[0][1] + 1 and t < 5000:
        t += 0.5
        e.tick(t)
    key = e.trip.via[0][0]  # tỉnh xe vừa chạy qua
    e.drain()
    comment(e, "Chi", BY_KEY[key].name, t)
    events = e.drain()
    ticket = next(ev for ev in events if ev["type"] == "ticket")
    assert ticket["next"] is True and ticket["passed"] == BY_KEY[key].name and e.lane_of_uid("chi")
    assert "chi" not in e.pickups and any(ev["type"] == "loxe" and "Chi" in ev["text"] for ev in events)


def test_pickup_at_rest_stop_boards_right_there():
    e, t = _driving_to_hanoi()
    t = run_until(e, "REST", t)
    ahead = [k for k, odo in e.trip.via if odo > e.trip_km()]
    e.drain()
    comment(e, "Dũng", BY_KEY[ahead[-1]].name, t)
    events = e.drain()
    assert any(ev["type"] == "pickup_stop" and ev["people"][0]["name"] == "Dũng" for ev in events) and not e.halt
    assert e.bus.seat_of("dũng") is not None and "dũng" not in e.pickups


def test_detailed_address_still_books_the_province():
    """Live 02/11: «qua hải phòng ngõ 174 phường Lê Thanh Nghị» gõ mãi không lên xe (bị coi là tán gẫu)."""
    from xe_tet.server.game.parser import parse
    for text, prov in (("qua hải phòng ngõ 174 phường Lê Thanh Nghị", "Hải Phòng"), ("ở Bình Dương", "Bình Dương"),
                       ("Nghệ An, xã Diễn Châu huyện Diễn Châu", "Nghệ An"), ("về quê Thanh Hoá thôn 3", "Thanh Hóa")):
        assert parse(text).kind == "province" and parse(text).province.name == prov, text
    for text in ("đường về hà nội xa quá", "hải phòng đẹp quá"):
        assert parse(text).kind == "chat", text
    e = Engine(0.0)
    comment(e, "Mimaro", "qua hải phòng ngõ 174 phường Lê Thanh Nghị", 1)
    ticket = next(ev for ev in e.drain() if ev["type"] == "ticket")
    assert ticket["province"] == "Hải Phòng" and "174" not in str(ticket)  # không hiện lại địa chỉ


def test_viewers_call_the_bus_to_another_station():
    """Live 02/11 «cho xe ra bến khác»: đủ STATION_VOTES người gọi «từ Hà Nội» / «bến Giáp Bát» → lần tới bến trống, xe ra
    bến đó; chưa đủ phiếu / bến còn khách thì chưa đổi; phiếu hết hạn sau 15 phút."""
    from xe_tet.server.game.engine import STATION_VOTE_TTL, STATION_VOTES
    e = Engine(0.0)
    assert e.network.departure.key == "hcm_miendong"
    comment(e, "An", "Hà Nội", 1)  # xe đang có khách: chưa đổi được
    for i, text in enumerate(["từ Hà Nội", "bến Giáp Bát", "cho xe ra bến Hà Nội"][:STATION_VOTES]):
        comment(e, f"Người {i}", text, 2 + i)
    votes = [ev for ev in e.drain() if ev["type"] == "station_vote"]
    assert [v["votes"] for v in votes] == list(range(1, STATION_VOTES + 1)) and votes[-1]["station"] == "Bến xe Giáp Bát"
    e.tick(10)
    assert e.network.departure.key == "hcm_miendong" and e.snapshot()["stations"][0]["votes"] == STATION_VOTES
    fresh = Engine(0.0)
    for i in range(STATION_VOTES):
        comment(fresh, f"Người {i}", "từ Hà Nội", 1 + i)
    fresh.tick(5)
    assert fresh.network.departure.key == "hn_giapbat"
    assert any(ev["type"] == "station_switch" for ev in fresh.drain())
    late = Engine(0.0)
    for i in range(STATION_VOTES - 1):
        comment(late, f"Người {i}", "từ Đà Nẵng", 1)
    comment(late, "Muộn", "từ Đà Nẵng", 2 + STATION_VOTE_TTL)  # hai phiếu đầu đã hết hạn
    late.tick(3 + STATION_VOTE_TTL)
    assert late.network.departure.key == "hcm_miendong"
    both = Engine(0.0)
    comment(both, "Chi", "từ Hà Nội về Nghệ An", 1)  # gọi bến + đặt vé
    assert both.viewers["chi"].province == "nghean" and both.station_votes["chi"][0] == "hn_giapbat"


def test_just_home_and_back_at_the_station_gets_teased():
    """Live 02/11: vừa được thả về quê, comment tiếp lại lên xe ở bến — vẫn cho đi (giữ người chơi), lơ xe trêu một lần,
    vé ghi chuyến thứ 2."""
    e = Engine(0.0)
    comment(e, "An", "Nghệ An", 1)
    t = run_until(e, "DROPOFF", 1)
    t = run_until(e, "BOARDING", t)
    e.drain()
    comment(e, "An", "Hà Nội", t + 1)
    events = e.drain()
    ticket = next(ev for ev in events if ev["type"] == "ticket")
    assert ticket["trip_no"] == 2 and any(ev["type"] == "loxe" and "An" in ev["text"] and "Nghệ An" in ev["text"] for ev in events)
    comment(e, "An", "Huế", t + 30)  # đổi tỉnh: không trêu lại
    assert not [ev for ev in e.drain() if ev["type"] == "loxe" and "Nghệ An" in ev.get("text", "")]


def test_loxe_reminds_other_directions_to_wait():
    """Anh dặn 02/11: xe đi Hà Nội mà người Cà Mau / Đồng Tháp / Bến Tre comment liên tục → lơ xe gom lại nói «đây là chuyến
    đi …, ai đi … đợi chuyến sau» (tối đa OTHER_DIR_GAP giây / câu)."""
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    for i, prov in enumerate(["Cà Mau", "Đồng Tháp", "Bến Tre đi"]):
        comment(e, f"Người {i}", prov, 2 + i)
    e.drain()
    e.tick(10)
    said = [ev["text"] for ev in e.drain() if ev["type"] == "loxe"]
    assert len(said) == 1 and all(p in said[0] for p in ("Cà Mau", "Đồng Tháp", "Bến Tre"))
    comment(e, "Muộn", "Kiên Giang", 11)
    e.tick(12)
    assert not [ev for ev in e.drain() if ev["type"] == "loxe" and "Kiên Giang" in ev["text"]]


def test_city_names_book_their_province():
    """Đủ 63 tỉnh: gõ tên thành phố tỉnh lỵ / nơi quen gọi cũng lên xe (Vinh → Nghệ An, BMT → Đắk Lắk…)."""
    from xe_tet.server.game.parser import parse
    from xe_tet.server.game.provinces import CITY_ALIASES
    assert len(CITY_ALIASES) == 59  # 63 tỉnh trừ Hà Nội, Hải Phòng, TP.HCM, Đà Nẵng (tên tỉnh = tên thành phố)
    for text, prov in (("Vinh", "Nghệ An"), ("về Đồng Hới", "Quảng Bình"), ("Đông Hà", "Quảng Trị"), ("BMT", "Đắk Lắk"),
                       ("Phủ Lý", "Hà Nam"), ("TT Huế", "Huế"), ("Phố Hiến", "Hưng Yên"), ("Rạch Giá", "Kiên Giang")):
        assert parse(text).kind == "province" and parse(text).province.name == prov, text
    assert parse("anh Vinh ơi đẹp quá").kind == "chat"


def test_moderation_blocks_tricks_and_regional_slurs_but_not_innocent_text():
    """Anh dặn 02/11: TikTok quét chữ trên live + giọng đọc — chặn từ tục (kể cả lách: không dấu, chấm giữa, chữ lặp, số thay
    chữ), tên đặt tầm bậy, phân biệt vùng miền; không chặn nhầm chữ thường trùng khi bỏ dấu."""
    import random
    from xe_tet.server.game.moderation import clean_name, is_bad
    from xe_tet.server.game.provinces import CITY_ALIASES
    from xe_tet.server.game.talk import LINES, STYLES, line
    for text in ("đm thằng này", "dit me", "đ.m", "d m", "dmmmm", "vcl", "v c l", "vãi lồn", "l0z", "Đéo Biết", "dkm xe chậm",
                 "bắc kỳ", "bac ky ngu", "parky", "nam kì", "3 que", "tàu khựa", "óc chó", "súc vật", "đụ má", "djt", "c.c"):
        assert is_bad(text), text
    fields = dict(dest="Hà Nội", n=5, hours="chừng 3 tiếng", place="Phú Yên", specialty="cá ngừ", prov="Nghệ An",
                  station="Bến xe Giáp Bát", total="1.000", name="Út", names="An và Bình", lunar="26 Chạp", other="Bình",
                  need=3, others="Cà Mau, Đồng Tháp", no=3, next="Huế", km="120", pos=2, xu=20, secs=30,
                  goal=20, reason="quên bằng lái", label="mưa lì xì", left=5, what="qua trạm", missing=5, title="Video Tết")
    talk = [line(k, random.Random(i), st, **fields) for st in STYLES for k in LINES[st] for i in range(len(LINES[st][k]))]
    places = [p.name for p in PROVINCES] + [a for al in CITY_ALIASES.values() for a in al]
    innocent = ["đi về các bạn ơi", "lớn rồi", "đeo khẩu trang", "con chó nhà mình dễ thương", "đồ cho mẹ", "bộ máy",
                "cái lon bia", "còn các bạn", "giờ mới rõ", "đủ mà", "mẹ may áo", "Bắc Cực", "bộ đội cụ Hồ", "xoạc chân",
                "đường Nam Kỳ Khởi Nghĩa", "chích ngừa", "buổi tối", "du lịch", "Vinh", "dân mới", "Đỗ Lăng", "Hà Nội 29"]
    assert not [t for t in innocent + talk + places if is_bad(t)]
    assert clean_name("Đéo Biết").startswith("Khách ") and clean_name("bắc kỳ 123").startswith("Khách ")
    assert clean_name("Lan Anh") == "Lan Anh"
    e = Engine(0.0)
    comment(e, "Đéo Biết", "Huế", 1)
    ticket = next(ev for ev in e.drain() if ev["type"] == "ticket")
    assert ticket["name"].startswith("Khách ") and "Đéo" not in str(ticket)  # tên bậy không hiện, không đọc lên sóng


def test_fuel_and_wash_while_waiting_give_small_bonus():
    """PLAN-137 (anh 02/11 «khúc đợi khách thêm đổ xăng rửa xe»): xe chạy hết xăng + bẩn dần; ở bến người xem «đổ xăng» /
    «rửa xe» (mỗi người 10 giây); đầy bình + sạch lúc xuất bến chạy nhanh hơn chút; thiếu thì vẫn chạy, không chặn ai;
    đang chạy gõ thì không có tác dụng."""
    from xe_tet.server.game.engine import CARE_COOLDOWN, CLEAN_BONUS, FUEL_BONUS
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    t = run_until(e, "DRIVING", 1)
    full, clean = e.fuel, e.dirt
    assert e.trip_bonus == 1 + FUEL_BONUS + CLEAN_BONUS  # xe mới: đầy bình, sạch
    comment(e, "Bình", "đổ xăng", t + 1)  # đang chạy: không đổ được
    t = run_until(e, "BOARDING", t + 2, limit=6000)
    assert e.fuel < full and e.dirt > clean
    e.drain()
    low_fuel, dirty = e.fuel, e.dirt
    comment(e, "Bình", "đổ xăng", t + 1)
    comment(e, "Bình", "đổ xăng", t + 2)  # trong 10 giây: không tính
    comment(e, "Chi", "rửa xe đi anh tư", t + 3)
    events = e.drain()
    assert e.fuel == min(1.0, low_fuel + 0.2) and e.dirt == max(0.0, dirty - 0.25)
    assert [ev["type"] for ev in events if ev["type"] in ("fuel", "wash")] == ["fuel", "wash"]
    comment(e, "Bình", "đổ xăng", t + 3 + CARE_COOLDOWN)
    assert e.fuel == min(1.0, low_fuel + 0.4)
    e.fuel, e.dirt = 0.1, 0.9
    comment(e, "Dũng", "Huế", t + 20)
    run_until(e, "DRIVING", t + 20)
    assert e.trip_bonus == 1.0  # thiếu xăng, bẩn: vẫn chạy, chỉ không có thưởng


def test_gift_makes_bus_run_twice_as_fast_for_seconds_per_xu():
    """Anh 03/11 «tặng quà để xe trước đi nhanh hơn», chọn «mỗi xu cộng giây»: mỗi xu thêm 3 giây chạy x2, cộng dồn tối đa
    3 phút, chỉ trừ lúc xe chạy; thẻ quà ghi rõ."""
    from xe_tet.server.game.engine import TURBO_MAX, TURBO_PER_XU
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    base = e.speed()
    e.handle({"type": "gift", "name": "Bé", "diamonds": 5}, 2)
    gift = [ev for ev in e.drain() if ev["type"] == "gift"][-1]
    assert e.turbo == 5 * TURBO_PER_XU and "x2 thêm 15 giây" in gift["perk"]
    assert e.speed() == base * 2 and e.snapshot()["turbo"] == {"left": 15, "by": "Bé"}
    e.tick(3)  # đang ở bến: không trừ
    assert e.turbo == 15
    e.handle({"type": "gift", "name": "Bé", "diamonds": 900}, 4)
    assert e.turbo == TURBO_MAX
    e.tick(5)
    assert e.turbo == TURBO_MAX  # vẫn ở bến
    e._depart(5)
    e.tick(15)
    assert e.turbo == TURBO_MAX - 10


def _driving(e, t=1.0):
    comment(e, "An", "Hà Nội", t)
    e.tick(t + 0.1)
    e._depart(t + 0.2)
    e.tick(t + 0.3)
    e.drain()


def test_toll_stops_bus_until_gifts_cover_fee_only_gifts_count():
    """Anh 03/11: qua trạm thu phí / bị công an → xe đứng, chỉ QUÀ góp mới tính, chờ tới khi đủ thì đi tiếp."""
    e = Engine(0.0)
    e.blocks_on, e.toll_xu, e.fee_auto = True, 20, False
    _driving(e)
    e.block_now("toll")
    (ev,) = [x for x in e.drain() if x["type"] == "block"]
    assert ev["kind"] == "toll" and ev["goal"] == 20 and e.snapshot()["speed"] == 0.0
    km = e.trip_km()
    e.handle({"type": "like", "name": "Tim", "count": 500}, 2)
    comment(e, "Bình", "góp", 3)
    e.tick(400)  # chờ bao lâu cũng đứng
    assert e.block and e.trip_km() == km
    e.handle({"type": "gift", "name": "Cô Ba", "diamonds": 15}, 401)
    gift = [x for x in e.drain() if x["type"] == "gift"][-1]
    assert "15/20" in gift["perk"] and e.snapshot()["block"]["top"] == [{"name": "Cô Ba", "xu": 15}]
    e.handle({"type": "gift", "name": "Út", "diamonds": 5}, 402)
    (end,) = [x for x in e.drain() if x["type"] == "block_end"]
    assert end["by"] == "gifts" and end["name"] == "Cô Ba" and e.block is None
    e.tick(410)
    assert e.trip_km() > km


def test_police_speeding_fine_and_anh_tu_covers_the_loss():
    """Đang chạy nhanh nhờ quà mà gặp công an → «quá tốc độ», phạt gấp 3, hết chạy nhanh; phòng ít quà admin bấm bù lỗ
    (hoặc tự bù lỗ sau N giây)."""
    import pytest
    from xe_tet.server.game.engine import Refused, SPEEDING_FACTOR
    e = Engine(0.0)
    e.blocks_on, e.fine_xu, e.fee_auto = True, 10, False
    _driving(e)
    with pytest.raises(Refused):
        e.cover()
    e.handle({"type": "gift", "name": "Bé", "diamonds": 5}, 2)
    e.block_now("police")
    assert e.block["speeding"] and e.block["goal"] == 10 * SPEEDING_FACTOR and e.turbo == 15  # giây chạy nhanh giữ lại
    e.cover()
    (end,) = [x for x in e.drain() if x["type"] == "block_end"]
    assert end["by"] == "cover" and e.block is None
    e.cover_seconds, e.turbo = 30, 0.0
    e.block_now("police")
    assert not e.block["speeding"] and e.block["goal"] == 10
    e.tick(20)
    assert e.block
    e.tick(40)
    assert e.block is None


def test_blocks_planned_on_long_trips_away_from_stops():
    from xe_tet.server.game.engine import BLOCK_CLEAR_KM
    e = Engine(0.0)
    e.blocks_on = True
    e.block_rng.seed(1)
    for i, prov in enumerate(("Hà Nội", "Nghệ An", "Huế")):
        comment(e, f"K{i}", prov, 1 + i)
    e._depart(5)
    plan = e.block_plan
    assert any(k == "toll" for _, k in plan)
    assert all(abs(odo - leg.km) > BLOCK_CLEAR_KM for odo, _ in plan for leg in e.legs)
    short = Engine(0.0)
    comment(short, "A", "Hà Nội", 1)
    short._depart(2)
    assert short.block_plan == []  # engine trần (blocks_on tắt): không chặn


def test_fee_follows_room_gift_rate_low_gift_room_pays_one_xu():
    """Rà soát 03/11 (buổi live thật ~0,3 xu / phút): phí cố định 20 xu thì xe đứng ~1 giờ. Phí theo phòng: lượng xu phòng hay
    tặng trong 1,5 phút, ít nhất 1, nhiều nhất bằng mức admin đặt; một đại gia không đẩy phí cả phòng."""
    e = Engine(0.0)
    e.blocks_on, e.toll_xu = True, 20
    _driving(e)
    e.block_now("toll")
    assert e.block["goal"] == 1  # chưa ai tặng: 1 xu là qua
    e.handle({"type": "gift", "name": "A", "diamonds": 1}, 2)
    assert e.block is None
    for i in range(30):  # phòng tặng đều ~30 xu / phút
        e.last_now = 10 + i * 10
        e.handle({"type": "gift", "name": f"G{i}", "diamonds": 5}, e.last_now)
    e.block_now("toll")
    assert e.block["goal"] == 20  # chạm trần admin đặt
    e.cover()
    e.last_now, e.turbo = 2000, 0.0  # 10 phút sau không ai tặng: phí về lại 1
    e.block_now("police")
    assert e.block["goal"] == 1


def test_block_edge_cases_turn_off_pause_and_gift_credit_once():
    e = Engine(0.0)
    e.blocks_on, e.cover_seconds = True, 30
    _driving(e)
    e.block_now("toll")
    e.paused = True
    e.tick(100)  # tạm dừng 100 giây
    e.paused = False
    e.tick(101)
    assert e.block  # không tự bù lỗ ngay khi bỏ tạm dừng
    e.blocks_on = False
    e.tick(102)
    assert e.block is None and [x for x in e.drain() if x["type"] == "block_end"][-1]["by"] == "off"
    # tặng quà lúc chưa có vé: lần giữ chỗ kế tiếp lên đầu hàng, MỘT lần
    f = Engine(0.0)
    comment(f, "An", "Hà Nội", 1)
    fill_lane(f, "Cà Mau", 3, 2)
    f.handle({"type": "gift", "name": "Lạ", "diamonds": 1}, 3)
    comment(f, "Lạ", "Cà Mau", 4)
    assert f.queues["south"][0] == "lạ"
    comment(f, "Lạ", "không về", 5)
    comment(f, "Lạ", "Cà Mau", 6)
    assert f.queues["south"][-1] == "lạ"


def test_session_goal_steps_unlock_fun_for_everyone_and_money_panel():
    """Anh 03/11 «1 giờ 100k»: thanh mục tiêu buổi (1000 xu) — mốc 10 / 30 / 60 / 100 % mở cảnh vui cho cả phòng, đủ thì
    chúc Tết + vòng mới; /control thấy doanh thu giờ này."""
    e = Engine(0.0)
    e.goal_xu = 100
    e.handle({"type": "gift", "name": "A", "diamonds": 35}, 1)
    steps = [x for x in e.drain() if x["type"] == "goal_step"]
    assert [s["fx"] for s in steps] == ["lixi", "lantern"]
    assert e.snapshot()["goal"] == {"xu": 35, "goal": 100, "round": 1, "next_xu": 60, "next": "🎆 pháo hoa lớn"}
    e.handle({"type": "gift", "name": "B", "diamonds": 70}, 2)
    steps = [x for x in e.drain() if x["type"] == "goal_step"]
    assert [s["fx"] for s in steps] == ["firework", "party"] and e.specials == ["cả phòng"]
    assert e.snapshot()["goal"]["xu"] == 5 and e.snapshot()["goal"]["round"] == 2
    m = e.money()
    assert m["hour_xu"] == 105 and m["gifters"] == 2 and m["top"][0] == {"name": "B", "xu": 70}


def test_province_race_decides_next_trip_and_resets_each_trip(monkeypatch):
    """Đua tỉnh (anh 03/11): bình luận (1 điểm / 15 giây / người) + tim (20 tim = 1) + quà (1 xu = 5) cộng cho tỉnh quê; tỉnh
    nhiều điểm nhất có người chờ thì chuyến mới đi hướng đó; mỗi chuyến một vòng."""
    monkeypatch.setattr("xe_tet.server.game.engine.LANE_MAX_WAIT", 1e9)  # chuyến Hà Nội dài: tắt luật «chờ quá 10 phút»
    e = Engine(0.0)
    fill_lane(e, "Cà Mau", SEATS, 1)  # chuyến 1 hướng nam, đầy
    comment(e, "Tây1", "Bạc Liêu", 2)  # hướng nam: hết giường → chờ
    fill_lane(e, "Hà Nội", 3, 3, prefix="B")  # hướng bắc đông người chờ hơn
    e.drain()
    tay = e.viewers["tây1"].province
    for t in (4, 5, 6):  # bình luận dồn: chỉ 1 điểm / 15 giây (lúc gõ tên tỉnh đã được 1)
        comment(e, "Tây1", "chào cả nhà", t)
    assert e.race[tay] == 1
    e.handle({"type": "like", "name": "Tây1", "count": 45}, 7)
    e.handle({"type": "like", "name": "Tây1", "count": 100}, 8)  # chỉ tim (không quà): vẫn kéo tỉnh mình lên được
    assert {"province": "Bạc Liêu", "points": 8} in e.snapshot()["race"]  # Cà Mau nhiều điểm hơn nhưng đã ngồi hết trên xe
    t = 9.0
    while e.bus.no == 1:  # chạy hết chuyến 1 → chuyến 2: Bạc Liêu thắng dù hướng bắc đông người chờ hơn
        t += 1
        e.tick(t)
    wins = [x for x in e.drain() if x["type"] == "race_win"]
    assert wins and wins[-1]["province"] == "Bạc Liêu" and e.bus.seat_of("tây1") is not None
    assert not e.race  # vòng mới


def test_billboard_video_stops_bus_then_continues():
    """Bảng quảng cáo (anh 03/11): xe đang chạy dừng lại xem video anh tải lên rồi chạy tiếp; tự chiếu theo lịch."""
    import pytest
    from xe_tet.server.game.engine import Refused
    e = Engine(0.0)
    with pytest.raises(Refused):
        e.show_now()
    e.videos = [{"name": "a.mp4", "title": "Video A", "url": "/videos/a.mp4", "seconds": 20.0}]
    _driving(e)
    e.show_now("a.mp4")
    (ev,) = [x for x in e.drain() if x["type"] == "show"]
    assert ev["url"] == "/videos/a.mp4" and e.snapshot()["speed"] == 0.0 and e.snapshot()["show"]["title"] == "Video A"
    km = e.trip_km()
    e.tick(15)
    assert e.show and e.trip_km() == km
    e.tick(22)
    assert e.show is None and [x for x in e.drain() if x["type"] == "show_end"]
    e.tick(25)
    assert e.trip_km() > km
    # tự chiếu: tới giờ, giữa chặng
    e.shows_on, e.next_show = True, 0.0
    e.progress = 0.5
    e.tick(26)
    assert e.show and e.show["title"] == "Video A"
