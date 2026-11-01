"""Mạng tuyến thật (BRD-tuyen-xe.md): bến đi, làn theo hướng, km đường bộ, độ quanh co, đèo / hầm, tỉnh dọc đường.

Đọc `data/routes.json` do `tools/build_routes.py` sinh (OSRM, chạy một lần) — game không gọi mạng.

Km có hai nghĩa:
- km tuyến của một tỉnh: bến đi → tỉnh đó theo đường của chính nó (ghi trên vé, lúc thả khách);
- km xe chạy (odometer) của một chuyến: xe chở nhiều tỉnh cùng làn, tỉnh nằm ngoài trục thì xe rẽ nhánh rồi quay ra
  (`Trip`) — dùng cho tiến độ, trạm nghỉ, cảnh dọc đường.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .geo import DEFAULT_DEPARTURE, DEPARTURES, Departure

DATA = Path(__file__).resolve().parent / "data" / "routes.json"
BUS_KMH = 52  # tốc độ trung bình xe khách đường dài kể cả dừng nghỉ (Đà Lạt – Hà Nội ~1.400 km ≈ 26–27 giờ)
PASS_SPAN_KM = 8  # quanh km của đỉnh đèo ± 8 km tính là «đang qua đèo» (đường đèo thật dài 10–30 km)
TUNNEL_SPAN_KM = 3  # hầm ngắn hơn nhiều (Hải Vân 6,3 km, Đèo Cả 4,1 km)


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
    step: int  # +1 đi ra xa bến, −1 quay về chỗ rẽ


@dataclass(frozen=True)
class Trip:
    stops: tuple[tuple[str, float], ...]  # (tỉnh, odometer lúc tới) theo thứ tự xe ghé
    segments: tuple[Segment, ...]

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
        """+1 xe đang chạy ra xa bến theo đường của tỉnh, −1 đang quay về chỗ rẽ."""
        return self._segment(odo).step


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
        self.routes = {
            k: Route(r["km"], r["lane"], tuple(r["wind"]),
                     tuple(Pass(km, name, kind == "ham") for km, name, kind in r["passes"]),
                     tuple((km, p) for km, p in r["places"]))
            for k, r in block["routes"].items()
        }
        self.shared_km = {key: km for ln in block["lanes"] for key, km in ln.get("shared", {}).items()}
        self.lane_by_key = {ln.key: ln for ln in self.lanes}

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

    def plan(self, provinces: list[str]) -> Trip:
        """Thứ tự ghé + km xe chạy (BR-3): luôn ghé tỉnh gần vị trí xe nhất tính theo đường thật — tỉnh cùng ngả liền
        nhau đi tiếp; tỉnh rẽ nhánh thì xe chạy ngược về chỗ rẽ rồi vào nhánh (km rẽ tính đủ, không đi tắt)."""
        left = set(provinces)
        cur, odo = None, 0.0
        stops, segments = [], []
        while left:
            def hop(b: str) -> tuple[float, float]:
                fork = self.shared(cur, b) if cur else 0.0
                return (self.km(cur) - fork if cur else 0.0) + self.km(b) - fork, self.km(b)

            nxt = min(left, key=hop)
            fork = self.shared(cur, nxt) if cur else 0.0
            if cur and self.km(cur) - fork > 0:
                back = self.km(cur) - fork
                segments.append(Segment(odo, odo + back, cur, float(self.km(cur)), -1))
                odo += back
            out = self.km(nxt) - fork
            segments.append(Segment(odo, odo + out, nxt, fork, 1))
            odo += out
            stops.append((nxt, odo))
            left.remove(nxt)
            cur = nxt
        return Trip(tuple(stops), tuple(segments))

    def wind_at(self, province: str, km: float) -> float:
        wind = self.routes[province].wind
        return wind[min(len(wind) - 1, max(0, int(km // self.bin_km)))] if wind else 0.0

    def pass_at(self, province: str, km: float) -> Pass | None:
        return next((p for p in self.routes[province].passes
                     if abs(p.km - km) <= (TUNNEL_SPAN_KM if p.tunnel else PASS_SPAN_KM)), None)

    def place_at(self, province: str, km: float) -> str:
        """Tỉnh xe đang đi qua (tỉnh lỵ gần nhất của đoạn 10 km)."""
        places = self.routes[province].places
        return next((p for start, p in reversed(places) if km >= start), places[0][1] if places else province)

    @staticmethod
    def hours(km: float) -> float:
        return km / BUS_KMH


def available(data: dict | None = None) -> list[str]:
    """Bến đi có trong cả bảng code lẫn dữ liệu tuyến (thêm bến vào geo.py mà chưa dựng lại dữ liệu thì không hiện)."""
    data = data if data is not None else _read()
    return [d.key for d in DEPARTURES if d.key in data["departures"]]


@lru_cache(maxsize=1)
def _read() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))
