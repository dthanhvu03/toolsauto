"""Mạng tuyến giả lập cho test: km = khoảng cách chim bay × 1,25; làn Bắc / Nam theo vĩ độ so với bến đi; mọi tỉnh cùng
làn nằm trên một trục (km chung đường = km tỉnh gần hơn) nên thứ tự ghé = thứ tự km.

Kết quả test không phụ thuộc dữ liệu OSRM (data/routes.json); test cần dữ liệu thật dùng fixture `real_routes`.
"""

import asyncio
import math
import os
import tempfile

import pytest

from xe_tet.server import voice as voice_module
from xe_tet.server.game import network as network_module
from xe_tet.server.game.geo import CAPITALS, DEFAULT_DEPARTURE, DEPARTURES


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h)) * 1.25


def synthetic_routes() -> dict:
    departures = {}
    for dep in DEPARTURES:
        routes = {}
        for key, at in CAPITALS.items():
            if key == dep.province:
                continue
            km = round(_km((dep.lat, dep.lon), at))
            lane = "north" if at[0] >= dep.lat else "south"
            passes = {"hanoi": [[max(1, km - 120), "Đèo Thử", "deo"]], "nghean": [[max(1, km - 60), "Hầm Thử", "ham"]]}
            routes[key] = {"km": km, "lane": lane, "wind": [12.0 if i % 3 == 0 else 2.0 for i in range(km // 10 + 1)],
                           "passes": passes.get(key, [])}
        for key, r in routes.items():
            # bến mặc định: đi qua mọi tỉnh cùng làn gần bến hơn (một trục) → đồ thị đường bộ thẳng, thứ tự ghé = thứ tự km;
            # bến khác: nối thẳng bến → tỉnh (trục giả của nhiều bến ghép lại sẽ tạo đường tắt không có thật)
            # (địa phận mỗi tỉnh bắt đầu ở giữa tỉnh lỵ trước và tỉnh lỵ của nó — như dữ liệu thật chia theo tỉnh lỵ gần nhất)
            before = sorted((o["km"], k) for k, o in routes.items() if o["lane"] == r["lane"] and o["km"] < r["km"])
            line = ([*before, (r["km"], key)] if dep.key == DEFAULT_DEPARTURE else [(r["km"], key)])
            r["places"] = [[0, dep.province], *[[(prev + km) / 2, k] for prev, (km, k) in zip([0, *(km for km, _ in line)], line)]]
        lanes = []
        for lane, label, arrow in (("north", "Hướng Bắc", "⬆"), ("south", "Hướng Nam", "⬇")):
            members = sorted((k for k, r in routes.items() if r["lane"] == lane), key=lambda k: routes[k]["km"])
            if members:
                shared = {f"{a}|{b}": routes[a]["km"] for i, a in enumerate(members) for b in members[i + 1:]}
                lanes.append({"key": lane, "label": label, "arrow": arrow, "to": members[-1], "provinces": members,
                              "shared": shared})
        departures[dep.key] = {"lanes": lanes, "routes": routes}
    return {"bin_km": 10, "departures": departures}


SYNTHETIC = synthetic_routes()

# Hồ sơ khách (PLAN-134 D): test không ghi vào storage/db/xe_tet.db thật (store.py đọc biến này lúc app nạp)
os.environ["XE_TET_DB"] = os.path.join(tempfile.mkdtemp(prefix="xe_tet_test_"), "xe_tet.db")

# Thay ngay khi nạp conftest (trước khi import test): app.py dựng `hub` (và Engine) lúc import.
REAL_READ = network_module._read
network_module._read = lambda: SYNTHETIC


# Giọng lơ xe: test không gọi VieNeu / Microsoft thật — bộ đọc nền im lặng (test_voice.py thử render bằng máy giả).
async def _silent(_self) -> None:
    await asyncio.Event().wait()


async def _no_voices(_self) -> None:
    return None


voice_module.Announcer.run = _silent
voice_module.Announcer.refresh_voices = _no_voices


@pytest.fixture
def real_routes():
    """Dữ liệu thật data/routes.json (OSRM); bỏ qua nếu chưa dựng."""
    if not network_module.DATA.exists():
        pytest.skip("chưa có data/routes.json — chạy tools/build_routes.py")
    return REAL_READ()
