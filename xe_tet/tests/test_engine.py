from datetime import date

from xe_tet.server.game.engine import (BOARD_SECONDS, FULL_BUS_SECONDS, NOTICE_COOLDOWN, REST_MIN_KM, SEATS,
                                       SPECIAL_SECONDS, Engine)
from xe_tet.server.game.parser import normalize, parse
from xe_tet.server.game.provinces import PROVINCES


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
    assert e.phase_until <= 1 + FULL_BUS_SECONDS
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
    assert "comment tên tỉnh" in perks[0] and "trên xe" in perks[1]


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
    from xe_tet.server.game.engine import TET_DAY, VN
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
    assert "thêm 90 xu" in gifts[-1]["next_tier"]
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
    """BR-4: ai chờ trước đi trước — làn 1 người chờ lâu hơn vẫn chạy trước làn 40 người."""
    e = Engine(0.0)
    for i in range(24):
        comment(e, f"B{i}", "Huế", 1)  # Bắc: 1 xe đầy
    comment(e, "Út", "Cà Mau", 1)  # Nam: 1 người, giữ chỗ trước
    for i in range(40):
        comment(e, f"C{i}", "Huế", 2)  # Bắc: 40 người giữ chỗ sau
    t = run_until(e, "FINISH", 1)
    run_until(e, "BOARDING", t)
    assert e.bus.lane == "south" and e.bus.seat_of("út") is not None


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


def test_switching_lane_frees_seat_for_queue():
    e = Engine(0.0)
    for i in range(SEATS):
        comment(e, f"K{i}", "Hà Nội", 1)
    comment(e, "Cho", "Hà Nội", 2)  # hàng chờ cùng làn
    comment(e, "K0", "Cà Mau", 3)  # khách đang ngồi đổi sang hướng Nam
    assert e.bus.seat_of("cho") is not None and len(e.bus.riders()) == SEATS
    assert e.lane_of_uid("k0") == "south"


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


def test_trip_plan_counts_branch_detour():
    from xe_tet.server.game import network as network_module
    from xe_tet.server.game.network import Network
    base = network_module._read()  # mạng giả lập của conftest
    data = {**base, "departures": {**base["departures"]}}
    block = data["departures"]["hcm_miendong"]
    lane = next(ln for ln in block["lanes"] if ln["key"] == "north")
    lane = {**lane, "shared": {**lane["shared"], "nghean|hanoi": 300, "hanoi|nghean": 300}}
    data["departures"]["hcm_miendong"] = {**block, "lanes": [lane if ln["key"] == "north" else ln for ln in block["lanes"]]}
    net = Network(data, "hcm_miendong")
    trip = net.plan(["nghean", "hanoi"])
    first, second = trip.stops
    detour = (net.km(first[0]) - 300) + (net.km(second[0]) - 300)
    assert round(second[1] - first[1]) == round(detour)
    assert trip.at(first[1] + 1)[0] == first[0]  # vừa rời tỉnh đầu: đang quay ra theo đường của tỉnh đó


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


def test_relief_departs_when_lane_has_a_busload_waiting():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)  # xe chính đón hướng Bắc
    fill_lane(e, "Cà Mau", SEATS, 2)  # đủ một xe hướng Nam đang chờ
    e.tick(2.5)
    departs = [ev for ev in e.drain() if ev["type"] == "relief_depart"]
    assert len(departs) == 1 and departs[0]["count"] == SEATS and departs[0]["sponsor"] is None
    assert e.waiting() == 0 and len(e.reliefs) == 1 and e.snapshot()["reliefs"][0]["riders"] == SEATS


def test_relief_drops_everyone_with_names_and_counts():
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


def test_queued_viewer_gift_100_calls_relief_and_rides_first():
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    fill_lane(e, "Cà Mau", 5, 2)
    comment(e, "Út", "Bạc Liêu", 3)  # giữ chỗ cuối hàng hướng Nam
    e.handle({"type": "gift", "name": "Út", "diamonds": 100}, 4)
    events = e.drain()
    relief = [ev for ev in events if ev["type"] == "relief_depart"][0]
    gift = [ev for ev in events if ev["type"] == "gift"][0]
    assert relief["sponsor"] == "Út" and relief["names"][0] == "Út" and relief["count"] == 6
    assert "xe tăng cường" in gift["perk"] and e.bus.banner is None  # tên nằm trên xe tăng cường, không dán xe chính
    assert e.on_trip("út")  # đã lên xe: không đổi tỉnh nữa


def test_relief_respects_limit_and_blocks_departure_switch():
    import pytest
    from xe_tet.server.game.engine import RELIEF_MAX
    e = Engine(0.0)
    comment(e, "An", "Hà Nội", 1)
    fill_lane(e, "Cà Mau", SEATS * (RELIEF_MAX + 1), 2)
    e.tick(2.5)
    assert len(e.reliefs) == RELIEF_MAX and e.waiting() == SEATS
    with pytest.raises(ValueError):
        e.set_departure("dalat")


def test_relief_rider_is_in_exactly_one_place():
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
