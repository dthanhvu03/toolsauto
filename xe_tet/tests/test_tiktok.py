"""Cầu nối TikTok với client / sự kiện giả — không gọi mạng."""

import asyncio
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from xe_tet.server import app as app_module
from xe_tet.server import settings
from xe_tet.server.tiktok import BACKOFF, OFFLINE_RETRY, GiftCombos, TikTokBridge, map_event, parse_username


def user(uid=123, nick="Minh Anh", handle="minhanh"):
    return NS(id=uid, id_str=str(uid), display_id=handle, nickname=nick,
              avatar_thumb=NS(url_list=["https://p16.tiktokcdn.com/a.jpg"]))


def gift_event(repeat, end, streakable=True, diamonds=1, group=7):
    return NS(user=user(), gift=NS(streakable=streakable, diamond_count=diamonds, name="Hoa hồng"),
              group_id=group, gift_id=5655, repeat_count=repeat, repeat_end=end)


def test_parse_username():
    assert parse_username("@abc.def") == "abc.def"
    assert parse_username("https://www.tiktok.com/@lavie3398/live?enter_from=x") == "lavie3398"
    assert parse_username("tiktok.com/@xe_tet") == "xe_tet"
    assert parse_username("abc") == "abc"
    assert parse_username("<script>") == "" and parse_username("") == ""


def test_map_comment_like_social():
    c = GiftCombos()
    m = map_event("comment", NS(user=user(), content="Nghệ An"), c)
    assert m == {"type": "comment", "text": "Nghệ An", "uid": "tt:123", "name": "Minh Anh",
                 "avatar": "https://p16.tiktokcdn.com/a.jpg"}
    assert map_event("comment", NS(user=user(), content="  "), c) is None
    assert map_event("like", NS(user=user(), count=999), c)["count"] == 50
    assert map_event("follow", NS(user=user()), c)["type"] == "follow"
    assert map_event("comment", NS(user=None, content="hi"), c) is None


def test_gift_combo_counts_each_tap_once():
    c = GiftCombos()
    got = [map_event("gift", gift_event(r, e), c) for r, e in ((1, 0), (2, 0), (5, 0), (5, 1))]
    assert [g and g["diamonds"] for g in got] == [1, 1, 3, None]  # tổng 5 hoa hồng, sự kiện kết thúc không cộng lại
    assert got[2]["gift"] == "Hoa hồng ×3"
    one = map_event("gift", gift_event(1, 1, streakable=False, diamonds=199, group=0), c)
    assert one["diamonds"] == 199


class FakeClient:
    """Mô phỏng TikTokLiveClient: start() trả task; kịch bản quyết định task kết thúc / ném lỗi."""

    def __init__(self, script):
        self.script = script
        self.listeners = {}
        self.room_id = 777
        self.disconnected = False

    def add_listener(self, cls, fn):
        self.listeners[cls] = fn

    async def start(self, **kwargs):
        assert kwargs["process_connect_events"] is False  # không phát lại tin cũ
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return asyncio.ensure_future(step(self))

    async def disconnect(self):
        self.disconnected = True


def make_bridge(script, clock=None):
    emitted, sleeps, clients = [], [], []

    def factory(_name):
        clients.append(FakeClient(script))
        return clients[-1]

    async def fake_sleep(s):
        sleeps.append(s)

    bridge = TikTokBridge(emit=emitted.append, client_factory=factory,
                          event_classes=lambda: {k: k for k in ("comment", "gift", "like", "follow",
                                                                  "share", "join", "viewers", "end")},
                          sleep=fake_sleep, **({"clock": clock} if clock else {}))
    return bridge, emitted, sleeps, clients


async def chat_then_drop(client):
    await client.listeners["viewers"](NS(user=None, total=321))
    await client.listeners["comment"](NS(user=user(), content="Huế"))


async def chat_then_end(client):
    await client.listeners["comment"](NS(user=user(), content="37"))
    await client.listeners["end"](NS())


class UserOfflineError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


async def run_bridge(bridge):
    await bridge.connect("@xe_tet")
    for _ in range(50):
        await asyncio.sleep(0)
        if not bridge.active:
            break


def test_reconnects_with_backoff_then_stops_when_live_ends():
    async def go():
        bridge, emitted, sleeps, clients = make_bridge([chat_then_drop, chat_then_drop, chat_then_end])
        await run_bridge(bridge)
        return bridge, emitted, sleeps, clients
    bridge, emitted, sleeps, clients = asyncio.run(go())
    assert [e["text"] for e in emitted] == ["Huế", "Huế", "37"]
    assert sleeps == [BACKOFF[0], BACKOFF[1]]  # vào rồi rớt ngay (< 60 s) thì bậc chờ vẫn tăng
    assert bridge.status["state"] == "ended" and bridge.status["viewers"] == 321
    assert all(c.disconnected for c in clients)


def test_offline_waits_then_joins_when_live_starts():
    async def go():
        bridge, emitted, sleeps, _ = make_bridge([UserOfflineError(), UserOfflineError(), chat_then_end])
        await run_bridge(bridge)
        return bridge, sleeps
    bridge, sleeps = asyncio.run(go())
    assert sleeps == [OFFLINE_RETRY, OFFLINE_RETRY] and bridge.status["state"] == "ended"


def test_unknown_user_stops_with_error():
    async def go():
        bridge, _, sleeps, _ = make_bridge([UserNotFoundError()])
        await run_bridge(bridge)
        return bridge, sleeps
    bridge, sleeps = asyncio.run(go())
    assert bridge.status["state"] == "error" and "Không tìm thấy" in bridge.status["error"] and sleeps == []


def test_bad_username_rejected():
    bridge, *_ = make_bridge([])
    with pytest.raises(ValueError):
        asyncio.run(bridge.connect("<b>x</b>"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PATH", tmp_path / "xe_tet.json")
    monkeypatch.setattr(app_module, "hub", app_module.Hub())
    with TestClient(app_module.app) as c:
        yield c


def test_tiktok_events_reach_engine_and_block_simulator(client):
    async def forever(c):
        await c.listeners["comment"](NS(user=user(), content="Nghệ An"))
        await asyncio.sleep(3600)
    hub = app_module.hub
    hub.bridge = TikTokBridge(emit=hub.handle, client_factory=lambda _n: FakeClient([forever]),
                              event_classes=lambda: {k: k for k in ("comment", "gift", "like", "follow",
                                                                      "share", "join", "viewers", "end")})
    assert client.post("/api/admin", json={"action": "tiktok_connect", "username": "@xe_tet"}).json()["ok"]
    state = client.get("/api/state").json()
    assert state["tiktok"]["state"] == "connected" and state["control"]["tiktok_user"] == "xe_tet"
    assert any(s and s["name"] == "Minh Anh" for s in state["bus"]["seats"])
    assert client.post("/api/admin", json={"action": "sim", "rate": 6}).status_code == 409
    client.post("/api/admin", json={"action": "tiktok_disconnect"})
    assert client.get("/api/state").json()["tiktok"]["state"] == "idle"
    assert client.post("/api/admin", json={"action": "tiktok_connect", "username": "<x>"}).status_code == 400


def test_token_protects_control_but_not_overlay(client, monkeypatch):
    monkeypatch.setattr(app_module, "TOKEN", "bi-mat")
    assert client.get("/api/state").status_code == 401
    assert client.get("/control").status_code == 401
    assert client.get("/api/state", headers={"x-token": "bi-mat"}).status_code == 200
    assert client.get("/control?token=bi-mat").status_code == 200
    with client.websocket_connect("/ws") as ws:  # màn hình live vẫn xem được
        assert ws.receive_json()["kind"] == "state"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_flapping_connection_backs_off_but_stable_one_resets():
    clock = Clock()

    async def stable(c):  # giữ được 2 phút rồi mới rớt
        clock.t += 120

    async def flap(c):
        clock.t += 1

    async def go(script):
        bridge, _, sleeps, _ = make_bridge(script, clock)

        async def record(s):  # dừng sau 5 lần chờ
            sleeps.append(s)
            bridge._stop = len(sleeps) >= 5
        bridge._sleep = record
        await run_bridge(bridge)
        return sleeps
    assert asyncio.run(go([flap] * 6)) == [5, 10, 20, 40, 60]
    assert asyncio.run(go([flap, flap, stable, flap, flap, flap])) == [5, 10, 5, 10, 20]


def test_offline_long_after_live_counts_as_ended():
    clock = Clock()

    async def live(c):
        clock.t += 300

    async def go():
        bridge, _, sleeps, _ = make_bridge([live] + [UserOfflineError()] * 40, clock)

        async def tick(s):
            sleeps.append(s)
            clock.t += s
        bridge._sleep = tick
        await run_bridge(bridge)
        return bridge, sleeps
    bridge, sleeps = asyncio.run(go())
    assert bridge.status["state"] == "ended" and len(sleeps) <= 22  # ~10 phút hỏi mỗi 30 s rồi dừng


def test_auto_resume_flag_follows_connect_and_disconnect(client):
    async def forever(c):
        await asyncio.sleep(3600)
    hub = app_module.hub
    hub.bridge = TikTokBridge(emit=hub.handle, client_factory=lambda _n: FakeClient([forever]),
                              event_classes=lambda: {})
    client.post("/api/admin", json={"action": "tiktok_connect", "username": "xe_tet"})
    assert settings.load()["tiktok_auto"] is True  # PM2 bật lại server giữa live → tự nối lại
    client.post("/api/admin", json={"action": "tiktok_disconnect"})
    assert settings.load()["tiktok_auto"] is False


def test_server_start_resumes_live_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PATH", tmp_path / "xe_tet.json")
    settings.save(settings.clean({"tiktok_user": "xe_tet", "tiktok_auto": True}))
    hub = app_module.Hub()
    calls = []

    async def fake_connect(name):
        calls.append(name)
        return name
    hub.bridge.connect = fake_connect
    monkeypatch.setattr(app_module, "hub", hub)
    with TestClient(app_module.app):
        pass
    assert calls == ["xe_tet"]
