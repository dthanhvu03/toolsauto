"""Dựng bảng tuyến thật cho Xe Tết (BRD-tuyen-xe.md, anh duyệt gọi OSRM 31/10): chạy MỘT LẦN, có mạng.

    venv/bin/python -m xe_tet.tools.build_routes        → xe_tet/server/game/data/routes.json

Với mỗi bến đi × 63 tỉnh: km đường bộ, độ quanh co theo từng đoạn 10 km (từ hướng đi thật của con đường),
đèo đi qua; rồi gom tỉnh thành «làn» theo trục đường (lộ trình đi theo trục đó suốt phần lớn quãng đường).
Nguồn: OSRM router.project-osrm.org (dữ liệu OpenStreetMap) — gọi tối đa 1 lượt / giây theo quy định máy chủ demo.
Phản hồi OSRM lưu ở `tools/osrm_cache.json.gz` (không commit): chỉnh thuật toán rồi chạy lại không phải gọi mạng.

OSRM chỉ tìm đường nhanh nhất, không biết xe khách Việt Nam không chạy qua nước bạn: Nam ↔ Bắc nó hay vòng qua
Campuchia – Lào (có tuyến qua cả Thái Lan). Lộ trình nào có điểm xa mọi tỉnh lỵ quá 130 km (đất Việt Nam hẹp, đường
quốc lộ luôn gần một tỉnh lỵ) bị coi là «ra nước ngoài» và được dẫn lại qua các điểm trên Quốc lộ 1.
"""

import gzip
import json
import math
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

from xe_tet.server.game.geo import CAPITALS, DEPARTURES, PASSES, QL1_VIAS, TUNNELS
from xe_tet.server.game.provinces import BY_KEY, PROVINCES

OSRM = "https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=polyline"
OUT = Path(__file__).resolve().parents[1] / "server" / "game" / "data" / "routes.json"
CACHE = Path(__file__).resolve().parent / "osrm_cache.json.gz"
PAUSE = 1.1  # máy chủ demo OSRM: ≤ 1 lượt / giây
BIN_KM = 10
STEP_KM = 0.2  # lấy mẫu lại lộ trình mỗi 200 m trước khi đo hướng — điểm dày ở phố (vòng xuyến, rẽ ngõ) không còn là «cua»
PASS_NEAR_KM = 4
TRACK_KM = 2.0  # điểm mẫu thưa (mỗi 2 km) để so hai lộ trình
SAME_ROAD_KM = 3.0  # điểm cách lộ trình kia ≤ 3 km ⇒ vẫn chung đường
FOLLOW_SHARE = 0.7  # chung đường ít nhất 70 % quãng (tối thiểu 150 km) ⇒ chung làn với trục
FOLLOW_MIN_KM = 150
OFF_TRUNK_KM = 15  # tỉnh lỵ cách trục ≤ 15 km (rẽ vào thị xã) vẫn tính là trên trục
LANE_MIN = 3  # làn ít hơn 3 tỉnh gộp vào làn chung đường dài nhất
WIND_SMOOTH = 3  # trung vị 3 đoạn liền nhau: một đoạn qua phố (rẽ liên tục) không thành «đèo»
HUBS = ("hanoi", "hcm", "danang")  # làn có thành phố lớn thì đặt tên theo đó («Hướng Hà Nội») thay vì tỉnh xa nhất
ABROAD_KM = 130  # điểm lộ trình xa mọi tỉnh lỵ hơn 130 km ⇒ đang ở nước ngoài (đường trong nước xa nhất ~90 km)
VIA_TRIES = 3
TUNNEL_WIND = 50  # quanh đèo ±2 km: hầm / đường tránh đo 0–34 °/km, đường đèo thật 61–240 (đo 01/11 trên 310 tuyến)
PASS_SPAN = 10  # ±10 điểm mẫu 200 m = ±2 km quanh đỉnh đèo
MERGE_SHARE = 0.4  # làn lẻ chỉ gộp vào làn chung đường ≥ 40 % quãng của nó; không thì giữ làn riêng
MAX_LANES = 6  # bến quá nhiều làn thì người chờ phân tán — vượt thì gộp làn nhỏ nhất
# Chuyển làn tay (anh 03/11 «kiểm tra nghiệp vụ đi qua các tỉnh»): gom theo trục còn sót tỉnh lệch đường. Mỗi mục: bến →
# {tỉnh: một tỉnh của làn đích}. Số trong ngoặc = km xe phải chạy thêm (km bến → tỉnh → điểm cuối làn − km thẳng tới điểm
# cuối, đo bằng engine) ở làn cũ → làn mới. Chỉ chuyển khi đỡ vòng rõ ràng (≥ 45 km) và làn mới đi ngang (≤ 100 km).
LANE_MOVES: dict[str, dict[str, str]] = {
    "hcm_miendong": {"hue": "hanoi"},  # xe Tây Nguyên +178 → xe QL1 +31
    "hn_giapbat": {"binhdinh": "binhthuan",  # +107 → +53
                   "haiduong": "quangninh"},  # xe Lạng Sơn +88 → xe Quảng Ninh +5
    # Đà Lạt: miền Tây đi xe TP.HCM phải vòng 150–600 km (điểm cuối là TP.HCM) → gom về xe miền Tây (Kiên Giang)
    "dalat": {k: "kiengiang" for k in ("tiengiang", "bentre", "travinh", "vinhlong", "cantho", "haugiang", "soctrang",
                                       "baclieu", "camau")},
    "danang": {"quangngai": "binhdinh"},  # xe Tây Nguyên +128 → xe QL1 +73
    "cantho": {"hue": "hanoi",  # xe Tây Nguyên +178 → xe QL1 +42
               "angiang": "kiengiang",  # xe Hà Nội +122 → +30
               "dongthap": "kiengiang"},  # +144 → +98
}


def decode(polyline: str) -> list[tuple[float, float]]:
    """Giải mã polyline (độ chính xác 5) → [(vĩ độ, kinh độ)]."""
    points, index, lat, lon = [], 0, 0, 0
    while index < len(polyline):
        for coord in (0, 1):
            shift = result = 0
            while True:
                b = ord(polyline[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if coord == 0:
                lat += delta
            else:
                lon += delta
        points.append((lat / 1e5, lon / 1e5))
    return points


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return math.degrees(math.atan2(y, x)) % 360


def fetch(points: list[tuple[float, float]]) -> dict:
    """Một lượt OSRM qua các điểm (đi, [ghé], đến) → {"km", "geometry"} (polyline chưa giải mã, để lưu cache gọn)."""
    url = OSRM.format(coords=";".join(f"{lon},{lat}" for lat, lon in points))
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "xe-tet-sum-vay/1 (one-off build)"}),
                                        timeout=60) as r:
                route = json.load(r)["routes"][0]
            time.sleep(PAUSE)
            return {"km": route["distance"] / 1000, "geometry": route["geometry"]}
        except Exception as exc:  # mạng chập chờn / bị giới hạn: chờ rồi thử lại
            print(f"  thử lại {attempt + 1}: {exc}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"OSRM không trả lời: {url}")


def load_cache() -> dict:
    return json.loads(gzip.decompress(CACHE.read_bytes())) if CACHE.exists() else {}


def save_cache(cache: dict) -> None:
    CACHE.write_bytes(gzip.compress(json.dumps(cache, separators=(",", ":")).encode()))


def abroad(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Điểm xa tỉnh lỵ nhất nếu xa quá ABROAD_KM (lộ trình đã ra nước ngoài), ngược lại None."""
    capitals = list(CAPITALS.values())
    worst = max(resample(points, 5.0), key=lambda p: min(km_between(p, c) for c in capitals))
    return worst if min(km_between(worst, c) for c in capitals) > ABROAD_KM else None


def domestic(a: tuple[float, float], b: tuple[float, float], route: dict | None = None) -> dict:
    """Đường trong nước: đường nhanh nhất của OSRM (`route` nếu đã có); ra nước ngoài thì ghé các điểm QL1 nằm giữa
    hai đầu (theo vĩ độ), vẫn ra thì ghé thêm tỉnh lỵ gần điểm lạc nhất."""
    route = route or fetch([a, b])
    lo, hi = sorted((a[0], b[0]))
    vias = [(lat, lon) for _, lat, lon in QL1_VIAS if lo + 0.3 < lat < hi - 0.3]
    for attempt in range(VIA_TRIES + 1):
        stray = abroad(decode(route["geometry"]))
        if stray is None:
            return route
        if attempt == VIA_TRIES:
            break
        if not vias or route.get("via") == vias:
            vias = vias + [min(CAPITALS.values(), key=lambda c: km_between(c, stray))]
        vias.sort(key=lambda v: abs(v[0] - a[0]))  # ghé theo thứ tự từ bến đi ra
        route = {**fetch([a, *vias, b]), "via": list(vias)}
    raise RuntimeError(f"vẫn ra nước ngoài sau {VIA_TRIES} lần dẫn lại: {a} → {b}")


def resample(points: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    """Điểm cách đều `step` km dọc lộ trình (nội suy tuyến tính)."""
    out, carry = [points[0]], 0.0
    for p, q in zip(points, points[1:]):
        seg = km_between(p, q)
        t = step - carry
        while t <= seg:
            f = t / seg
            out.append((p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f))
            t += step
        carry = (carry + seg) % step if seg else carry
    return out


def median(values: list[float], window: int) -> list[float]:
    half = window // 2
    out = []
    for i in range(len(values)):
        window = sorted(values[max(0, i - half): i + half + 1])
        out.append(window[(len(window) - 1) // 2])  # đầu / cuối tuyến cửa sổ hụt: lấy trung vị dưới (bỏ đoạn phố)
    return out


def analyse(points: list[tuple[float, float]]) -> dict:
    """Lộ trình lấy mẫu 200 m → độ quanh co từng đoạn 10 km (độ đổi hướng / km), đèo đi qua (km), điểm mẫu mỗi 2 km."""
    even = resample(points, STEP_KM)
    heads = [bearing(p, q) for p, q in zip(even, even[1:])]
    bins = [0.0] * (int(len(even) * STEP_KM // BIN_KM) + 1)
    for i in range(1, len(heads)):
        bins[int(i * STEP_KM // BIN_KM)] += abs((heads[i] - heads[i - 1] + 180) % 360 - 180)
    wind = [round(b / BIN_KM, 1) for b in median(bins, WIND_SMOOTH)]
    passes = []
    for name, lat, lon in PASSES:
        best = min(range(len(even)), key=lambda i: km_between(even[i], (lat, lon)))
        if km_between(even[best], (lat, lon)) > PASS_NEAR_KM:
            continue
        lo, hi = max(1, best - PASS_SPAN), min(len(heads) - 1, best + PASS_SPAN)
        local = sum(abs((heads[i] - heads[i - 1] + 180) % 360 - 180) for i in range(lo, hi)) / max(STEP_KM, (hi - lo) * STEP_KM)
        if local >= TUNNEL_WIND:
            passes.append([round(best * STEP_KM), name, "deo"])
        elif name in TUNNELS:  # thẳng tắp ngay đỉnh đèo: đi hầm
            passes.append([round(best * STEP_KM), TUNNELS[name], "ham"])
        # thẳng mà đèo không có hầm: đường tránh chạy gần đỉnh đèo, không qua đèo
    places = []  # [km bắt đầu, tỉnh gần nhất] mỗi đoạn 10 km (gộp đoạn liền nhau cùng tỉnh) → cảnh vùng, trạm nghỉ
    for b in range(len(bins)):
        p = even[min(len(even) - 1, round((b + 0.5) * BIN_KM / STEP_KM))]
        near = min(CAPITALS, key=lambda k: km_between(p, CAPITALS[k]))
        if not places or places[-1][1] != near:
            places.append([b * BIN_KM, near])
    return {"wind": wind, "passes": sorted(passes), "places": places, "track": even[:: round(TRACK_KM / STEP_KM)]}


def shared_km(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Hai lộ trình cùng xuất phát đi chung đường bao nhiêu km tính từ bến (dừng ở chỗ rẽ khác ngả đầu tiên).

    Dò song song: mỗi điểm của `a` tìm điểm gần nhất của `b` quanh vị trí khớp trước đó — một bên vòng qua phố, bên kia
    đi tránh thì chiều dài lệch nhau nhưng vẫn bám được.
    """
    j = 0
    for i, p in enumerate(a):
        window = range(max(0, j - 2), min(len(b), j + 6))
        if not window:
            return i * TRACK_KM
        j = min(window, key=lambda k: km_between(p, b[k]))
        if km_between(p, b[j]) > SAME_ROAD_KM:
            return i * TRACK_KM
    return len(a) * TRACK_KM


def lanes_for(dep, routes: dict) -> list[dict]:
    """Gom tỉnh thành làn quanh vài trục đường.

    Tỉnh P «đi theo» trục T khi P chung đường với T suốt 70 % quãng (tối thiểu 150 km; tỉnh gần thì gần trọn quãng).
    Lần lượt lấy lộ trình được nhiều tỉnh còn lại đi theo nhất làm trục. Làn lẻ (< 3 tỉnh) gộp vào làn có trục chung
    đường dài nhất với nó (kể cả làn lẻ khác) khi chung ≥ 40 % quãng của nó; làn 2 tỉnh rẽ hẳn ngả khác (Lào Cai so với
    Điện Biên) giữ làn riêng. Làn 1 tỉnh luôn gộp (xe rẽ nhánh, engine cộng km rẽ). Quá MAX_LANES thì gộp làn nhỏ nhất.
    Trả về làn kèm trục và km chung đường từng cặp tỉnh trong làn (engine tính km xe chạy khi rẽ nhánh).
    """
    shared: dict[tuple[str, str], float] = {}

    def common(p: str, t: str) -> float:
        if (p, t) not in shared:
            shared[p, t] = shared_km(routes[p]["track"], routes[t]["track"])
        return shared[p, t]

    def follows(p: str, t: str) -> bool:
        km = routes[p]["km"]
        return p == t or common(p, t) >= min(km - OFF_TRUNK_KM, max(FOLLOW_MIN_KM, FOLLOW_SHARE * km))

    left, lanes = set(routes), []
    while left:
        trunk = max(left, key=lambda t: (sum(follows(p, t) for p in left), routes[t]["km"]))
        lanes.append({"trunk": trunk, "provinces": {p for p in left if follows(p, trunk)}})
        left -= lanes[-1]["provinces"]
    def fit(small: dict, ln: dict) -> float:
        return max(common(p, ln["trunk"]) / routes[p]["km"] for p in small["provinces"])

    def merge(small: dict) -> None:
        lanes.remove(small)
        max(lanes, key=lambda ln: fit(small, ln))["provinces"] |= small["provinces"]

    while len(lanes) > 1:
        small = next((ln for ln in sorted(lanes, key=lambda ln: len(ln["provinces"]))
                      if len(ln["provinces"]) < LANE_MIN
                      and (len(ln["provinces"]) == 1  # một tỉnh không đáng một làn: hàng chờ phân tán, chờ lâu
                           or max(fit(ln, other) for other in lanes if other is not ln) >= MERGE_SHARE)), None)
        if small is None:
            break
        merge(small)
    while len(lanes) > MAX_LANES:
        merge(min(lanes, key=lambda ln: len(ln["provinces"])))
    for p, mate in LANE_MOVES.get(dep.key, {}).items():
        for ln in lanes:
            ln["provinces"].discard(p)
        next(ln for ln in lanes if mate in ln["provinces"])["provinces"].add(p)
    out = []
    for i, ln in enumerate(sorted(lanes, key=lambda ln: -len(ln["provinces"]))):
        members = sorted(ln["provinces"], key=lambda k: routes[k]["km"])
        to = next((h for h in HUBS if h in ln["provinces"]), members[-1])
        b = bearing((dep.lat, dep.lon), CAPITALS[to])  # mũi tên theo hướng chung tới đích, không theo khúc đầu đường
        arrow = "⬆" if b < 60 or b > 300 else "⬇" if 120 < b < 240 else "➡" if b <= 120 else "⬅"
        pairs = {f"{a}|{b}": round(min(common(a, b), routes[a]["km"], routes[b]["km"]))
                 for j, a in enumerate(members) for b in members[j + 1:]}
        out.append({"key": f"lane{i}", "to": to, "label": f"Hướng {BY_KEY[to].name}", "arrow": arrow,
                    "trunk": ln["trunk"], "provinces": members, "shared": pairs})
    return out


def main() -> None:
    result = {"generated": date.today().isoformat(), "source": "OSRM router.project-osrm.org (OpenStreetMap)",
              "bin_km": BIN_KM, "departures": {}}
    cache = load_cache()
    for dep in DEPARTURES:
        print(f"== {dep.name}", flush=True)
        routes = {}
        for p in PROVINCES:
            if p.key == dep.province:
                continue
            key = f"{dep.key}/{p.key}"
            if key not in cache or ("via" not in cache[key] and abroad(decode(cache[key]["geometry"]))):
                cache[key] = domestic((dep.lat, dep.lon), CAPITALS[p.key], cache.get(key))
                save_cache(cache)
                print(f"  {p.name}: dẫn lại trong nước qua {len(cache[key].get('via', []))} điểm", flush=True)
            info = analyse(decode(cache[key]["geometry"]))
            routes[p.key] = {"km": round(cache[key]["km"]), **info}
            print(f"  {p.name:22} {routes[p.key]['km']:5} km  đèo / hầm: {', '.join(n for _, n, _ in info['passes']) or '-'}",
                  flush=True)
        lanes = lanes_for(dep, routes)
        lane_of = {k: ln["key"] for ln in lanes for k in ln["provinces"]}
        result["departures"][dep.key] = {
            "lanes": lanes,
            "routes": {k: {"km": r["km"], "lane": lane_of[k], "wind": r["wind"], "passes": r["passes"], "places": r["places"]}
                       for k, r in routes.items()},
        }
        print("  làn:", "; ".join(f"{ln['arrow']} {ln['label']} ({len(ln['provinces'])} tỉnh)" for ln in lanes), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"→ {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
