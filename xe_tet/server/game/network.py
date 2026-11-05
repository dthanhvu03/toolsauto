"""Mạng tuyến thật (BRD-tuyen-xe.md): bến đi, làn theo hướng, km đường bộ, độ quanh co, đèo / hầm, tỉnh dọc đường.

Đọc `data/routes.json` do `tools/build_routes.py` sinh (OSRM, chạy một lần) — game không gọi mạng.

Km có hai nghĩa:
- km tuyến của một tỉnh: bến đi → tỉnh đó theo đường của chính nó (ghi trên vé, lúc thả khách);
- km xe chạy (odometer) của một chuyến: xe chở nhiều tỉnh cùng làn, đi từ tỉnh này sang tỉnh kia theo đồ thị đường bộ
  giữa các tỉnh (`RoadGraph`) — dùng cho tiến độ, trạm nghỉ, cảnh dọc đường.

Hồ sơ đường (độ quanh co, đèo / hầm, tỉnh dọc đường) gọi bằng khoá «bến:tỉnh» (`Network.profiles`) hoặc tên tỉnh trơn (tuyến
từ bến đang chọn): mỗi khúc chuyến xe chạy nằm trên một tuyến OSRM thật nên địa hình luôn khớp đường đang đi.
"""

import itertools
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .geo import CAPITALS, DEFAULT_DEPARTURE, DEPARTURES, Departure

DATA = Path(__file__).resolve().parent / "data" / "routes.json"
BUS_KMH = 52  # tốc độ trung bình xe khách đường dài kể cả dừng nghỉ (Đà Lạt – Hà Nội ~1.400 km ≈ 26–27 giờ)
PASS_SPAN_KM = 8  # quanh km của đỉnh đèo ± 8 km tính là «đang qua đèo» (đường đèo thật dài 10–30 km)
TUNNEL_SPAN_KM = 3  # hầm ngắn hơn nhiều (Hải Vân 6,3 km, Đèo Cả 4,1 km)
# Đường bộ giữa hai tỉnh lỵ không ngắn hơn chim bay × 1,2 (hệ số quanh co tối thiểu): miền Bắc tỉnh dày, dữ liệu 10 km / ô
# đo hụt (Hà Nội – Hòa Bình ra 20 km, thật ~75; chim bay ~60 → ≥ 72)
MIN_CIRCUITY = 1.2
# Xe nhận khách dọc đường (PLAN-134 C): ghé tỉnh p trên đường tới điểm cuối của làn tốn thêm ≤ DETOUR_KM thì xe làn đó chở
# được p (Huế lên xe Hà Nội: thêm ~0 km; Lâm Đồng: thêm ~200 km → không)
DETOUR_KM = 50
# Tên tỉnh trên màn (anh 03/11 «kiểm tra logic đi qua các tỉnh»): tỉnh lỵ gần nhất mỗi 10 km nhảy qua lại ở ranh giới
# (Bắc Ninh → Bắc Giang → Bắc Ninh trong 20 km) — một đoạn ngắn hơn chừng này kẹp giữa hai đoạn cùng tỉnh thì gộp vào tỉnh đó
FLICKER_KM = 30


@dataclass(frozen=True)
class Lane:
    key: str
    label: str  # «Hướng Hà Nội»
    arrow: str
    to: str  # tỉnh đặt tên làn (thành phố lớn trong làn, không có thì tỉnh xa nhất)
    provinces: tuple[str, ...]


@dataclass(frozen=True)
class Pass:
    km: int
    name: str  # «Đèo Pha Đin» / «Hầm Hải Vân»
    tunnel: bool


@dataclass(frozen=True)
class Route:
    km: int
    lane: str
    wind: tuple[float, ...]  # độ đổi hướng / km theo từng đoạn `bin_km` km
    passes: tuple[Pass, ...]
    places: tuple[tuple[int, str], ...]  # (km bắt đầu, tỉnh gần nhất) dọc đường


@dataclass(frozen=True)
class Segment:
    """Một khúc xe chạy trên đường của một tỉnh: odometer [odo0, odo1) ứng với km tuyến km0 → km0 ± (odo1 − odo0)."""
    odo0: float
    odo1: float
    route: str
    km0: float
    step: float  # km tuyến đổi theo mỗi km xe chạy: > 0 đi ra xa bến của tuyến đó, < 0 đi về phía bến (|step| ≤ 1)


@dataclass(frozen=True)
class Trip:
    stops: tuple[tuple[str, float], ...]  # (tỉnh, odometer lúc tới) theo thứ tự xe ghé
    segments: tuple[Segment, ...]
    via: tuple[tuple[str, float], ...] = ()  # tỉnh xe đi qua mà không ai xuống (tỉnh, odometer lúc tới tỉnh lỵ)

    @property
    def total(self) -> float:
        return self.stops[-1][1] if self.stops else 0.0

    def _segment(self, odo: float) -> Segment:
        return next((s for s in self.segments if odo < s.odo1), self.segments[-1])

    def at(self, odo: float) -> tuple[str, float]:
        """(tỉnh có hồ sơ đường, km tuyến) ở odometer `odo`."""
        seg = self._segment(odo)
        return seg.route, max(0.0, seg.km0 + seg.step * (min(odo, seg.odo1) - seg.odo0))

    def direction(self, odo: float) -> int:
        """+1 xe đang chạy ra xa bến theo tuyến của khúc đang đi, −1 đang chạy về phía bến của tuyến đó."""
        step = self._segment(odo).step
        return (step > 0) - (step < 0)


class Network:
    def __init__(self, data: dict, departure: str = DEFAULT_DEPARTURE):
        if departure not in available(data):
            raise ValueError(f"không có bến đi «{departure}» trong dữ liệu tuyến")
        self.data = data
        self.bin_km = data.get("bin_km", 10)
        self.departures = {d.key: d for d in DEPARTURES}
        self.departure: Departure = self.departures[departure]
        block = data["departures"][departure]
        self.lanes = [Lane(ln["key"], ln["label"], ln["arrow"], ln["to"], tuple(ln["provinces"])) for ln in block["lanes"]]
        self.routes = {k: _route(r) for k, r in block["routes"].items()}
        self.shared_km = {key: km for ln in block["lanes"] for key, km in ln.get("shared", {}).items()}
        self.lane_by_key = {ln.key: ln for ln in self.lanes}
        self._serves: dict[str, frozenset[str]] = {}
        self._shown: dict[str, tuple[tuple[int, str], ...]] = {}
        self.profiles = {f"{dep}:{dest}": _route(r) for dep, b in data["departures"].items() for dest, r in b["routes"].items()}
        self.graph = _graph(data)

    @classmethod
    def load(cls, departure: str = DEFAULT_DEPARTURE) -> "Network":
        return cls(_read(), departure)

    def switch(self, departure: str) -> "Network":
        return Network(self.data, departure)

    def lane_of(self, province: str) -> str | None:
        """Làn của tỉnh; None khi tỉnh trùng bến đi (khách đã ở quê — BR-5)."""
        route = self.routes.get(province)
        return route.lane if route else None

    def km(self, province: str) -> int:
        return self.routes[province].km

    def shared(self, a: str, b: str) -> float:
        """Km hai tỉnh cùng làn đi chung đường tính từ bến (tới chỗ rẽ khác ngả)."""
        if a == b:
            return float(self.km(a))
        return float(self.shared_km.get(f"{a}|{b}", self.shared_km.get(f"{b}|{a}", 0)))

    def serves(self, lane: str) -> frozenset[str]:
        """Tỉnh xe làn `lane` chở được: tỉnh của làn + tỉnh nằm dọc đường tới điểm cuối của làn — chi phí chèn (km bến → p
        + km p → điểm cuối − km bến → điểm cuối) ≤ DETOUR_KM. Xe TP.HCM → Hà Nội thả khách dọc QL1 như xe thật."""
        if lane not in self._serves:
            ln = self.lane_by_key[lane]
            end = float(self.km(ln.to))
            self._serves[lane] = frozenset(ln.provinces) | {
                p for p in self.routes
                if p != ln.to and self.km(p) + self.leg_km(p, ln.to) - end <= DETOUR_KM}
        return self._serves[lane]

    def leg_km(self, a: str, b: str) -> float:
        """Km chặng a → b: từ bến thì đúng tuyến OSRM (khớp vé); giữa hai tỉnh thì đường ngắn hơn trong hai cách — quay về
        chỗ rẽ rồi vào nhánh (đúng km OSRM, thắng ở nơi tỉnh nằm dọc một trục như miền Tây) hoặc đi tắt trên đồ thị đường bộ
        (thắng ở nơi các nhánh có đường nối như miền Bắc)."""
        if a == self.departure.province:
            return float(self.km(b))
        return min(self._fork_km(a, b), self.graph.km(a, b))

    def _fork_km(self, a: str, b: str) -> float:
        fork = self.shared(a, b)
        return self.km(a) - fork + self.km(b) - fork

    def plan(self, provinces: list[str]) -> Trip:
        """Thứ tự ghé + km xe chạy (BR-3). Mỗi chặng đi đường ngắn hơn của `leg_km` — mô hình cây cũ một mình vòng xe số 2
        ngày 01/11 tới 4.441 km; đồ thị một mình thì miền Tây vòng xa (Sóc Trăng → Cà Mau 265 km). Thứ tự: `RoadGraph.order`.
        Tỉnh đi qua mà không ai xuống ghi vào `Trip.via`."""
        g = self.graph
        home = self.departure.province
        order = g.order(home, list(provinces), self.leg_km)
        stops, segments, via = [], [], []
        targets = set(order)
        odo, cur = 0.0, home
        for nxt in order:
            if cur != home and g.km(cur, nxt) < self._fork_km(cur, nxt):  # đi tắt trên đồ thị
                for a, b in itertools.pairwise(g.path(cur, nxt)):
                    e = g.edges[a, b]
                    if a != cur and a not in targets:
                        via.append((a, odo))
                    segments.append(Segment(odo, odo + e.km, e.route, e.km_a, (e.km_b - e.km_a) / e.km))
                    odo += e.km
            else:  # theo tuyến OSRM của bến: (quay về chỗ rẽ nếu cần) rồi ra tới tỉnh
                fork = self.shared(cur, nxt) if cur != home else 0.0
                if cur != home and self.km(cur) > fork:
                    back = self.km(cur) - fork
                    segments.append(Segment(odo, odo + back, cur, float(self.km(cur)), -1))
                    odo += back
                via += [(p, odo + at - fork) for p, at in self.passing(nxt) if at > fork and p not in targets]
                segments.append(Segment(odo, odo + self.km(nxt) - fork, nxt, fork, 1))
                odo += self.km(nxt) - fork
            stops.append((nxt, odo))
            cur = nxt
        once = {p: at for p, at in reversed(via)}  # đi qua một tỉnh hai lần (vào rồi ra lại): ghi lần đầu
        return Trip(tuple(stops), tuple(segments), tuple(sorted(once.items(), key=lambda pa: pa[1])))

    def passing(self, province: str) -> list[tuple[str, float]]:
        """Tỉnh nằm dọc tuyến bến đi → `province` (không kể bến và đích), km tới giữa địa phận mỗi tỉnh."""
        r = self.routes[province]
        out: list[tuple[str, float]] = []
        spans = [(start, p) for i, (start, p) in enumerate(r.places) if i == 0 or p != r.places[i - 1][1]]
        for (start, p), end in zip(spans, [*(k for k, _ in spans[1:]), r.km]):
            if p not in (self.departure.province, province) and all(p != q for q, _ in out):
                out.append((p, (start + end) / 2))
        return out

    def profile(self, route: str) -> Route:
        """Hồ sơ đường theo khoá «bến:tỉnh» (khúc chuyến xe chạy) hoặc tên tỉnh (tuyến từ bến đang chọn)."""
        return self.profiles.get(route) or self.routes[route]

    def wind_at(self, province: str, km: float) -> float:
        wind = self.profile(province).wind
        return wind[min(len(wind) - 1, max(0, int(km // self.bin_km)))] if wind else 0.0

    def pass_at(self, province: str, km: float) -> Pass | None:
        return next((p for p in self.profile(province).passes
                     if abs(p.km - km) <= (TUNNEL_SPAN_KM if p.tunnel else PASS_SPAN_KM)), None)

    def place_at(self, province: str, km: float) -> str:
        """Tỉnh xe đang đi qua (tỉnh lỵ gần nhất của đoạn 10 km, đã gộp đoạn nhảy qua lại ở ranh giới)."""
        places = self._shown.get(province)
        if places is None:
            places = self._shown[province] = steady(self.profile(province).places)
        return next((p for start, p in reversed(places) if km >= start), places[0][1] if places else province)

    @staticmethod
    def hours(km: float) -> float:
        return km / BUS_KMH


def steady(places: tuple[tuple[int, str], ...]) -> tuple[tuple[int, str], ...]:
    """Gộp đoạn tỉnh ngắn (< FLICKER_KM) kẹp giữa hai đoạn cùng một tỉnh: A, B (15 km), A → A. Chỉ dùng cho tên hiện trên
    màn / lơ xe gọi; đồ thị đường bộ vẫn dựng từ dữ liệu gốc."""
    spans = [list(x) for i, x in enumerate(places) if i == 0 or x[1] != places[i - 1][1]]
    changed = True
    while changed:
        changed = False
        for i in range(1, len(spans) - 1):
            if spans[i - 1][1] == spans[i + 1][1] and spans[i + 1][0] - spans[i][0] < FLICKER_KM:
                del spans[i:i + 2]  # bỏ đoạn kẹp + đoạn sau (cùng tỉnh với đoạn trước) → nối liền đoạn trước
                changed = True
                break
    return tuple((start, p) for start, p in spans)


def _route(r: dict) -> Route:
    return Route(r["km"], r["lane"], tuple(r["wind"]), tuple(Pass(km, name, kind == "ham") for km, name, kind in r["passes"]),
                 tuple((km, p) for km, p in r["places"]))


@dataclass(frozen=True)
class Edge:
    """Cạnh giữa hai tỉnh kề nhau trên một tuyến OSRM: dài `km`, nằm trên hồ sơ `route` từ km_a (tỉnh đầu) tới km_b."""
    km: float
    route: str
    km_a: float
    km_b: float


class RoadGraph:
    """Đồ thị đường bộ 63 tỉnh ghép từ mọi tuyến OSRM đã có (5 bến × 62 tỉnh): mỗi tuyến là một chuỗi tỉnh nối nhau
    (`places`, đổi tỉnh lỵ gần nhất mỗi 10 km) → hai tỉnh liền nhau trên chuỗi là một cạnh, dài bằng hiệu km. Cạnh đo được
    trên nhiều tuyến thì lấy lần đo gần trung vị nhất.

    Floyd–Warshall ra km ngắn nhất + đường đi giữa mọi cặp tỉnh (63³ ≈ 250 nghìn phép, một lần lúc nạp dữ liệu). Không
    gọi mạng. Đường đi giữa hai tỉnh = đúng các tỉnh xe đi qua → bảng chặng hiện được «đi qua địa phận» dù không ai xuống."""

    def __init__(self, data: dict) -> None:
        home_of = {d.key: d.province for d in DEPARTURES}
        bin_km = data.get("bin_km", 10)
        seen: dict[tuple[str, str], list[tuple[float, int, Edge]]] = {}
        for dep, block in data["departures"].items():
            if dep not in home_of:
                continue
            for dest, r in block["routes"].items():
                # Mỗi tỉnh đặt ở GIỮA đoạn đường nằm trong địa phận của nó: cùng một khúc đường dù xe đi chiều nào, nên ghép
                # chuỗi ngược chiều không đếm hụt km (đặt ở chỗ «bắt đầu vào địa phận» thì phụ thuộc chiều đi → TP.HCM – Hà Nội
                # ghép ra 650 km). Bến đi ở km 0, đích ở km cuối tuyến (tỉnh lỵ).
                spans = [[0, r["places"][0][1] if r["places"] else dest]]
                for km, p in r["places"]:
                    if p != spans[-1][1]:
                        spans.append([km, p])
                chain = [(0.0, home_of[dep])]
                for (start, p), end in zip(spans, [*(k for k, _ in spans[1:]), r["km"]]):
                    if p not in (home_of[dep], dest):
                        chain.append(((start + end) / 2, p))
                chain.append((float(r["km"]), dest))
                for (ka, a), (kb, b) in itertools.pairwise(chain):
                    if a != b:
                        seen.setdefault((a, b), []).append((max(bin_km, kb - ka), r["km"], Edge(max(bin_km, kb - ka),
                                                                                             f"{dep}:{dest}", ka, kb)))
        # Một cạnh đo được trên nhiều tuyến: lấy lần đo gần TRUNG VỊ nhất (bằng nhau thì tuyến ngắn nhất chứa nó — đèo / hầm
        # đúng của đường đó). Không lấy ngắn nhất: tỉnh là đích (đặt ở tỉnh lỵ) và là tỉnh đi qua (đặt giữa địa phận) cho
        # hai số đo lệch nhau, ngắn nhất luôn là số đếm hụt.
        self.edges: dict[tuple[str, str], Edge] = {}
        for a, b in {tuple(sorted(pair)) for pair in seen}:
            both = seen.get((a, b), []) + [(km, rk, Edge(e.km, e.route, e.km_b, e.km_a)) for km, rk, e in seen.get((b, a), [])]
            mid = sorted(km for km, _, _ in both)[len(both) // 2]
            _, _, e = min(both, key=lambda c: (abs(c[0] - mid), c[1]))
            e = Edge(max(e.km, MIN_CIRCUITY * _crow_km(a, b)), e.route, e.km_a, e.km_b)
            self.edges[a, b] = e
            self.edges[b, a] = Edge(e.km, e.route, e.km_b, e.km_a)
        nodes = sorted({a for a, _ in self.edges})
        self.index = {k: i for i, k in enumerate(nodes)}
        self.nodes = nodes
        n = len(nodes)
        dist = [[0.0 if i == j else math.inf for j in range(n)] for i in range(n)]
        nxt = [[j for j in range(n)] for _ in range(n)]
        for (a, b), e in self.edges.items():
            dist[self.index[a]][self.index[b]] = e.km
        for k in range(n):
            dk = dist[k]
            for i in range(n):
                dik = dist[i][k]
                if dik == math.inf:
                    continue
                di, ni = dist[i], nxt[i]
                for j in range(n):
                    if dik + dk[j] < di[j]:
                        di[j] = dik + dk[j]
                        ni[j] = ni[k]
        self.dist = dist
        self.next = nxt

    def km(self, a: str, b: str) -> float:
        return self.dist[self.index[a]][self.index[b]]

    def path(self, a: str, b: str) -> list[str]:
        """Các tỉnh trên đường ngắn nhất a → b (gồm cả hai đầu)."""
        i, j = self.index[a], self.index[b]
        out = [a]
        while i != j:
            i = self.next[i][j]
            out.append(self.nodes[i])
        return out

    def order(self, start: str, stops: list[str], km: Callable[[str, str], float] | None = None) -> list[str]:
        """Thứ tự ghé: tối thiểu tổng km chờ của khách (tổng odometer lúc tới từng tỉnh) — ai gần xuống trước, không để
        cả xe vòng xa vì một người. Tham lam (tỉnh gần nhất trước) rồi 2-opt: đảo một đoạn nếu tổng chờ giảm, tới khi hết
        cải thiện. ≤ 24 điểm dừng → vài nghìn phép, tức thì."""
        left = sorted(set(stops) - {start})
        route: list[str] = []
        cur = start
        while left:
            best = min(left, key=lambda s: (km(cur, s), s))
            route.append(best)
            left.remove(best)
            cur = best

        def wait(r: list[str]) -> float:
            total = odo = 0.0
            for a, b in itertools.pairwise([start, *r]):
                odo += km(a, b)
                total += odo
            return total

        best_wait = wait(route)
        improved = True
        while improved:
            improved = False
            for i, j in itertools.combinations(range(len(route)), 2):
                cand = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
                w = wait(cand)
                if w < best_wait - 1e-6:
                    route, best_wait, improved = cand, w, True
        return route


def _crow_km(a: str, b: str) -> float:
    """Khoảng cách chim bay giữa hai tỉnh lỵ (km); thiếu toạ độ thì 0 (không áp cận dưới)."""
    if a not in CAPITALS or b not in CAPITALS:
        return 0.0
    (la1, lo1), (la2, lo2) = (map(math.radians, CAPITALS[a]), map(math.radians, CAPITALS[b]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


_graphs: dict[int, tuple[dict, RoadGraph]] = {}


def _graph(data: dict) -> RoadGraph:
    """Một đồ thị cho mỗi bộ dữ liệu (đổi bến đi không dựng lại); giữ tham chiếu `data` để id không bị dùng lại."""
    hit = _graphs.get(id(data))
    if hit is None or hit[0] is not data:
        hit = _graphs[id(data)] = (data, RoadGraph(data))
    return hit[1]


def available(data: dict | None = None) -> list[str]:
    """Bến đi có trong cả bảng code lẫn dữ liệu tuyến (thêm bến vào geo.py mà chưa dựng lại dữ liệu thì không hiện)."""
    data = data if data is not None else _read()
    return [d.key for d in DEPARTURES if d.key in data["departures"]]


@lru_cache(maxsize=1)
def _read() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))
