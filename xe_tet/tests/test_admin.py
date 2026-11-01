import pytest
from fastapi.testclient import TestClient

from xe_tet.server import app as app_module
from xe_tet.server import settings
from xe_tet.server.game.engine import Engine


def test_pause_freezes_phase_clock_and_driving():
    e = Engine(0.0, board_seconds=60)
    e.handle({"type": "comment", "name": "An", "text": "Huế"}, 1)
    e.paused = True
    e.tick(500)
    assert e.phase == "BOARDING" and e.phase_until - e.last_now == pytest.approx(60)
    e.paused = False
    e.tick(560)
    assert e.phase == "DRIVING"
    e.paused = True
    e.tick(600)
    assert e.progress == 0.0


def test_extend_and_skip():
    e = Engine(0.0, board_seconds=60)
    e.extend(30)
    assert e.phase_until == 90
    e.extend(-500)
    assert e.phase_until == 1.0  # không lùi về quá khứ
    e.handle({"type": "comment", "name": "An", "text": "Huế"}, 0.5)
    e.skip()
    e.tick(0.6)
    assert e.phase == "DRIVING"


def test_settings_clean_clamps_and_ignores_unknown():
    s = settings.clean({"view": "inside", "cam": "nope", "zoom": 9, "board_seconds": 5,
                        "rest_seconds": "45", "show_board": 0, "hack": 1})
    assert s["view"] == "inside" and s["cam"] == "wide" and s["zoom"] == 1.6
    assert s["board_seconds"] == 20 and s["rest_seconds"] == 45 and s["show_board"] is False
    assert "hack" not in s


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PATH", tmp_path / "xe_tet.json")
    monkeypatch.setattr(app_module, "hub", app_module.Hub())
    with TestClient(app_module.app) as c:
        yield c


def test_admin_settings_persist_and_apply(client, tmp_path):
    r = client.post("/api/admin", json={"action": "settings",
                                        "changes": {"view": "inside", "cam": "close", "rest_seconds": 40}})
    assert r.json()["ok"]
    state = client.get("/api/state").json()
    assert state["control"]["view"] == "inside" and state["control"]["cam"] == "close"
    assert app_module.hub.engine.rest_seconds == 40
    assert '"cam": "close"' in (tmp_path / "xe_tet.json").read_text(encoding="utf-8")
    assert settings.load()["view"] == "inside"


def test_admin_pause_and_unknown_action(client):
    client.post("/api/admin", json={"action": "pause", "paused": True})
    assert client.get("/api/state").json()["paused"] is True
    assert client.post("/api/admin", json={"action": "nope"}).status_code == 400


def test_custom_line_and_banner_reach_overlay(client):
    with client.websocket_connect("/ws") as ws:
        client.post("/api/admin", json={"action": "say", "text": "Chào cả nhà!"})
        client.post("/api/admin", json={"action": "announce", "title": "Giờ vàng", "text": "x2 tim", "seconds": 99})
        seen = []
        for _ in range(20):
            m = ws.receive_json()
            if m["kind"] == "event":
                seen.append(m)
            if len(seen) == 2:
                break
    assert seen[0] == {"kind": "event", "type": "loxe", "text": "Chào cả nhà!"}
    assert seen[1]["type"] == "announce" and seen[1]["seconds"] == 30


def test_auto_loxe_off_drops_engine_lines(client):
    client.post("/api/admin", json={"action": "settings", "changes": {"auto_loxe": False}})
    with client.websocket_connect("/ws") as ws:
        client.post("/api/event", json={"type": "comment", "name": "An", "text": "Huế"})
        client.post("/api/admin", json={"action": "skip"})
        types = []
        for _ in range(25):
            m = ws.receive_json()
            if m["kind"] == "event":
                types.append(m["type"])
            if "depart" in types:
                break
    assert "depart" in types and "loxe" not in types


def test_bad_input_is_400_not_500(client):
    assert client.post("/api/admin", json={"action": "extend", "seconds": "x"}).status_code == 400
    assert client.post("/api/admin", json={"action": "settings", "changes": {"zoom": "x"}}).status_code == 400
    assert client.post("/api/event", json={"type": "like", "name": "a", "count": "abc"}).status_code == 200


def test_foreign_host_rejected(client):
    """Trang web lạ trỏ tên miền về 127.0.0.1 (DNS rebinding) không điều khiển được."""
    assert client.post("/api/admin", json={"action": "pause", "paused": True},
                       headers={"host": "evil.example:8810"}).status_code == 400
    assert client.get("/api/state").json()["paused"] is False


def test_likes_are_batched_for_hearts(client):
    with client.websocket_connect("/ws") as ws:
        for _ in range(3):
            client.post("/api/event", json={"type": "like", "name": "An", "count": 5})
        for _ in range(40):
            m = ws.receive_json()
            if m["kind"] == "event" and m["type"] == "likes":
                break
    assert m["type"] == "likes" and m["count"] == 15


def test_quality_setting_validated():
    assert settings.clean({"quality": "low"})["quality"] == "low"
    assert settings.clean({"quality": "ultra"})["quality"] == "medium"  # mặc định «Vừa»
    assert settings.clean({"quality": "medium"})["quality"] == "medium"


def test_departure_switch_via_admin(client):
    r = client.post("/api/admin", json={"action": "departure", "key": "dalat"})
    assert r.json()["ok"] and client.get("/api/state").json()["departure"]["short"] == "Đà Lạt"
    assert settings.load()["departure"] == "dalat"
    client.post("/api/event", json={"type": "comment", "name": "An", "text": "Huế"})
    r = client.post("/api/admin", json={"action": "departure", "key": "hcm_miendong"})
    assert r.status_code == 409 and r.json()["error"].startswith("Chỉ đổi bến khi")  # lời báo nguyên văn cho admin


def test_admin_controls_every_bus(client):
    """Admin: gọi xe tăng cường cho một làn, chiếu xe đó lên màn hình, cho tới điểm kế, quay về xe chính."""
    client.post("/api/admin", json={"action": "reset"})
    client.post("/api/event", json={"type": "comment", "name": "An", "text": "Hà Nội"})
    client.post("/api/event", json={"type": "comment", "name": "Út", "text": "Cà Mau"})
    state = client.get("/api/state").json()
    south = next(ln["key"] for ln in state["lanes"] if ln["waiting"])
    assert client.post("/api/admin", json={"action": "relief", "lane": south}).json()["ok"]
    no = client.get("/api/state").json()["reliefs"][0]["no"]
    assert client.post("/api/admin", json={"action": "feature", "bus_no": no}).json()["ok"]
    state = client.get("/api/state").json()
    assert state["featured"] == no and state["bus"]["no"] == no and state["phase"] == "DRIVING"
    assert state["main"]["phase"] == "BOARDING" and state["main"]["riders"] == 1  # admin vẫn thấy xe chính
    assert client.post("/api/admin", json={"action": "relief_next", "bus_no": no}).json()["ok"]
    assert client.post("/api/admin", json={"action": "feature", "bus_no": 0}).json()["ok"]
    assert client.get("/api/state").json()["featured"] is None
    assert client.post("/api/admin", json={"action": "feature", "bus_no": 999}).status_code == 409
    assert client.post("/api/admin", json={"action": "relief", "lane": "nope"}).status_code == 409
    empty = next(ln["key"] for ln in client.get("/api/state").json()["lanes"] if not ln["waiting"])
    r = client.post("/api/admin", json={"action": "relief", "lane": empty})
    assert r.status_code == 409 and "không có ai chờ" in r.json()["error"]
    r = client.post("/api/admin", json={"action": "settings", "changes": {"relief_auto": False}})
    assert r.json()["ok"] and app_module.hub.engine.relief_auto is False
    client.post("/api/admin", json={"action": "settings", "changes": {"relief_auto": True}})


def test_music_tracks_and_admin_controls(client, tmp_path, monkeypatch):
    from xe_tet.server import music
    monkeypatch.setattr(music, "MUSIC_DIR", tmp_path)
    monkeypatch.setattr(music, "_cache", (-1.0, []))
    (tmp_path / "Xuan_que_toi.mp3").write_bytes(b"x")
    (tmp_path / "ghi chu.txt").write_text("không phải nhạc")
    client.post("/api/admin", json={"action": "reset"})
    state = client.get("/api/state").json()
    ids = [t["id"] for t in state["music_tracks"]]
    assert ids[:len(music.GENERATED)] == [f"gen:{i}" for i in range(len(music.GENERATED))]
    assert ids[-1] == "file:Xuan_que_toi.mp3" and state["music_tracks"][-1]["url"] == "/music/Xuan_que_toi.mp3"
    assert len(ids) == len(music.GENERATED) + 1  # file .txt không vào danh sách
    assert client.post("/api/admin", json={"action": "music_next", "bus_no": 0}).json()["ok"]
    assert client.post("/api/admin", json={"action": "music_toggle", "bus_no": 0}).json()["ok"]
    music_now = client.get("/api/state").json()["music"]
    assert (music_now["index"], music_now["on"]) == (1, False)
    assert client.post("/api/admin", json={"action": "music_set", "bus_no": 0, "index": len(ids) - 1}).json()["ok"]
    assert client.get("/api/state").json()["music"]["index"] == len(ids) - 1  # chọn đúng bài vừa tải lên
    assert client.post("/api/admin", json={"action": "music_set", "bus_no": 0, "index": -3}).status_code == 409
    r = client.post("/api/admin", json={"action": "settings", "changes": {"music_volume": 3, "sfx_volume": "0.25"}})
    assert r.json()["ok"]
    control = client.get("/api/state").json()["control"]
    assert control["music_volume"] == 1.0 and control["sfx_volume"] == 0.25
    client.post("/api/admin", json={"action": "settings", "changes": {"music_volume": 0.5, "sfx_volume": 0.6}})


def test_music_upload_and_delete_from_control(client, tmp_path, monkeypatch):
    from xe_tet.server import music
    monkeypatch.setattr(music, "MUSIC_DIR", tmp_path)
    monkeypatch.setattr(music, "_cache", (-1.0, []))
    r = client.post("/api/music", params={"name": "Xuân quê tôi.mp3"}, content=b"ID3 fake mp3")
    assert r.json() == {"ok": True, "name": "Xuân quê tôi.mp3"}
    r = client.post("/api/music", params={"name": "Xuân quê tôi.mp3"}, content=b"lan 2")  # trùng tên: không ghi đè
    assert r.json()["name"] == "Xuân quê tôi (2).mp3"
    r = client.post("/api/music", params={"name": "../../etc/hack.mp3"}, content=b"x")  # không thoát khỏi thư mục
    assert r.json()["name"] == "hack.mp3" and (tmp_path / "hack.mp3").exists()
    assert client.post("/api/music", params={"name": "virus.exe"}, content=b"x").status_code == 400
    assert client.post("/api/music", params={"name": "rong.mp3"}, content=b"").status_code == 400
    monkeypatch.setattr(music, "MAX_BYTES", 10)
    assert client.post("/api/music", params={"name": "to.mp3"}, content=b"x" * 50).status_code == 413
    assert not (tmp_path / "to.mp3").exists() and not list(tmp_path.glob("*.part"))
    titles = [t["title"] for t in client.get("/api/state").json()["music_tracks"]]
    assert "Xuân quê tôi" in titles and "Xuân quê tôi (2)" in titles
    assert client.delete("/api/music/hack.mp3").json()["ok"] and not (tmp_path / "hack.mp3").exists()
    assert client.delete("/api/music/khong-co.mp3").status_code == 404



def test_song_length_measured_once_and_falls_back(tmp_path, monkeypatch):
    from xe_tet.server import music
    calls = []

    class Done:
        def __init__(self, out):
            self.stdout = out

    def fake_run(cmd, **_kw):
        calls.append(cmd[-1])
        return Done("" if cmd[-1].endswith("hong.mp3") else "212.5\n")

    monkeypatch.setattr(music.subprocess, "run", fake_run)
    good, bad = tmp_path / "bai.mp3", tmp_path / "hong.mp3"
    good.write_bytes(b"x")
    bad.write_bytes(b"x")
    assert music.length_of(good) == 212.5 and music.length_of(good) == 212.5
    assert music.length_of(bad) == music.UNKNOWN_SECONDS
    assert calls.count(str(good)) == 1  # đo một lần


def test_trip_director_and_mix_settings_clamped_and_applied(client):
    from xe_tet.server import settings as settings_module
    out = settings_module.clean({"trip_minutes": 99, "auto_feature": "nope", "rotate_seconds": 1, "mix": "voice",
                                 "talk_style": "genz"})
    assert out["trip_minutes"] == 15 and out["auto_feature"] == "events" and out["rotate_seconds"] == 20
    assert out["talk_style"] == "genz" and settings_module.clean({"talk_style": "xx"})["talk_style"] == "mix"
    assert out["mix"] == "voice"
    assert client.post("/api/admin", json={"action": "settings", "changes": {"trip_minutes": 5}}).json()["ok"]
    state = client.get("/api/state").json()
    assert state["trip_minutes"] == 5 and state["control"]["trip_minutes"] == 5 and state["fleet"][0]["main"]


def test_talk_style_reaches_engine(client):
    from xe_tet.server.app import hub
    assert client.post("/api/admin", json={"action": "settings", "changes": {"talk_style": "geny"}}).json()["ok"]
    assert hub.engine.talk_style == "geny" and hub.voice.style() == "geny"


def test_track_list_never_runs_ffprobe_on_game_loop(tmp_path, monkeypatch):
    """tracks() gọi mỗi nhịp game: bài mới đo ở luồng riêng (tạm 3 phút), đo xong tự có độ dài thật."""
    import threading
    import time
    from xe_tet.server import music
    threads = []

    class Done:
        stdout = "95.0\n"

    def fake_run(cmd, **_kw):
        threads.append(threading.current_thread() is threading.main_thread())
        return Done()

    monkeypatch.setattr(music.subprocess, "run", fake_run)
    monkeypatch.setattr(music, "MUSIC_DIR", tmp_path)
    monkeypatch.setattr(music, "_cache", (-1.0, []))
    (tmp_path / "moi.mp3").write_bytes(b"x")
    first = [t["seconds"] for t in music.tracks() if t["id"] == "file:moi.mp3"]
    assert first in ([music.UNKNOWN_SECONDS], [95.0])  # chưa đo xong thì tạm 3 phút (luồng đo có thể xong rất nhanh)
    for _ in range(100):
        if [t["seconds"] for t in music.tracks() if t["id"] == "file:moi.mp3"] == [95.0]:
            break
        time.sleep(0.01)
    assert [t["seconds"] for t in music.tracks() if t["id"] == "file:moi.mp3"] == [95.0]
    assert threads == [False]  # đo đúng một lần, không phải ở luồng chính
