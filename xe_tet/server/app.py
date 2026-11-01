"""Server Xe Tết: nhận sự kiện (TikTok / bảng điều khiển), chạy luật chơi, đẩy trạng thái cho overlay.

Chạy: `python -m xe_tet.server` từ thư mục gốc toolsauto → http://127.0.0.1:8810 (overlay), /control.
"""

import asyncio
import contextlib
import hmac
import logging
import os
import random
import time
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import music, settings, simulator, voice
from .game.engine import LIKE_MAX, Engine, Refused, as_int
from .game.geo import DEPARTURES
from .game.network import Network, available
from .tiktok import TikTokBridge

HERE = Path(__file__).resolve().parent
OVERLAY_DIST = HERE.parent / "overlay" / "dist"
TICK = 0.1
STATE_EVERY = 0.2
JOIN_FLUSH = 2.0
LIKES_FLUSH = 0.5  # gom tim mỗi nửa giây → overlay cho tim bay lên thanh tốc độ
SEND_TIMEOUT = 1.0  # màn hình nào nhận chậm hơn thì bỏ, không để kéo cả vòng game đứng theo

log = logging.getLogger("xe_tet")
DEPARTURE_LIST = [{"key": d.key, "name": d.name} for d in DEPARTURES if d.key in available()]
LOCAL_HOSTS = ("127.0.0.1", "localhost", "testserver")


class Hub:
    def __init__(self) -> None:
        self.settings = settings.load()
        self.engine = self.new_engine()
        self.clients: set[WebSocket] = set()
        self.sim_rate = 0.0  # sự kiện giả / giây, 0 = tắt
        self.pending_joins: list[str] = []
        self.last_join_flush = 0.0
        self.pending_likes = 0
        self.last_likes_flush = 0.0
        self.bridge = TikTokBridge(emit=self.handle)
        self.voice = voice.Announcer(emit=self.broadcast, settings=lambda: self.settings)

    def new_engine(self) -> Engine:
        engine = Engine(time.monotonic(), board_seconds=self.settings["board_seconds"],
                        rest_seconds=self.settings["rest_seconds"], network=Network.load(self.settings["departure"]))
        engine.relief_auto = self.settings["relief_auto"]
        engine.trip_minutes = self.settings["trip_minutes"]
        return engine

    def handle(self, event: dict) -> None:
        accepted = self.engine.handle(event, time.monotonic())
        if accepted and event.get("type") == "like":
            self.pending_likes += max(1, min(LIKE_MAX, as_int(event.get("count"))))

    def state_message(self) -> dict:
        return {"kind": "state", **self.engine.snapshot(), "control": self.settings, "sim_rate": self.sim_rate,
                "tiktok": self.bridge.public(), "departures": DEPARTURE_LIST, "music_tracks": music.tracks(),
                "voices": self.voice.voice_list}

    def update_settings(self, changes: dict) -> None:
        self.settings = settings.clean(changes, self.settings)
        self.engine.board_seconds = self.settings["board_seconds"]
        self.engine.rest_seconds = self.settings["rest_seconds"]
        self.engine.relief_auto = self.settings["relief_auto"]
        self.engine.trip_minutes = self.settings["trip_minutes"]
        settings.save(self.settings)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in list(self.clients):  # màn hình có thể ngắt giữa chừng trong lúc await
            try:
                await asyncio.wait_for(ws.send_json(message), SEND_TIMEOUT)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def run(self) -> None:
        while True:
            try:
                await self._loop()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("vòng lặp game lỗi, chạy lại")
                await asyncio.sleep(1)

    async def _loop(self) -> None:
        last_state = 0.0
        next_sim = 0.0
        while True:
            now = time.monotonic()
            if self.sim_rate > 0 and now >= next_sim:
                self.handle(simulator.next_event(self.engine.phase))
                next_sim = now + random.expovariate(self.sim_rate)
            self.engine.tick(now)
            self.engine.auto_feature(self.settings["auto_feature"], self.settings["rotate_seconds"])
            if self.settings["tiktok_auto"] and self.bridge.status["state"] in ("ended", "error"):
                self.update_settings({"tiktok_auto": False})  # live đã hết / sai tài khoản: lần bật sau không tự nối
            for event in self.engine.drain():
                if event["type"] == "loxe" and not self.settings["auto_loxe"]:
                    continue
                self.voice.observe(event, now, featured=self.engine.featured)
                if event["type"] == "join":
                    self.pending_joins.append(event["name"])
                else:
                    await self.broadcast({**event, "kind": "event"})  # "kind" là của khung tin, không để sự kiện ghi đè
            if self.pending_joins and now - self.last_join_flush >= JOIN_FLUSH:
                names, self.pending_joins = self.pending_joins, []
                self.last_join_flush = now
                await self.broadcast({"kind": "event", "type": "join", "names": names[-6:],
                                      "count": len(names)})
            if self.pending_likes and now - self.last_likes_flush >= LIKES_FLUSH:
                count, self.pending_likes = self.pending_likes, 0
                self.last_likes_flush = now
                await self.broadcast({"kind": "event", "type": "likes", "count": count})
            self.voice.tick(now)
            self.engine.advance_music([t["seconds"] for t in music.tracks()], self.settings["music_auto"])
            await self.voice.refresh_voices()
            if now - last_state >= STATE_EVERY:
                last_state = now
                await self.broadcast(self.state_message())
            await asyncio.sleep(TICK)


hub = Hub()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(hub.run())
    reader = asyncio.create_task(hub.voice.run())  # giọng lơ xe đọc lần lượt, không chặn vòng game
    if hub.settings["tiktok_auto"] and hub.settings["tiktok_user"]:
        log.warning("server khởi động lại giữa live → tự nối lại @%s", hub.settings["tiktok_user"])
        await hub.bridge.connect(hub.settings["tiktok_user"])
    yield
    await hub.bridge.disconnect()
    task.cancel()
    reader.cancel()


app = FastAPI(title="Xe Tết Sum Vầy", lifespan=lifespan)
# Chỉ nhận Host là máy này: chặn trang web lạ dùng DNS rebinding để gọi /api/admin (học từ kentjuno/chanh-dien-online).
# Mở cho điện thoại trong mạng thì thêm IP vào XE_TET_ALLOWED_HOSTS, ví dụ "127.0.0.1,localhost,192.168.1.10".
ALLOWED_HOSTS = [h.strip() for h in os.getenv("XE_TET_ALLOWED_HOSTS", ",".join(LOCAL_HOSTS)).split(",") if h.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# Mã điều khiển (tuỳ chọn): đặt XE_TET_TOKEN thì /control và /api/* phải kèm ?token=… hoặc header X-Token.
# Màn hình live (/) và /ws chỉ đọc nên vẫn mở để LIVE Studio quay được.
TOKEN = os.getenv("XE_TET_TOKEN", "")
PROTECTED = ("/api/", "/control")
if not TOKEN and any(h not in LOCAL_HOSTS for h in ALLOWED_HOSTS):
    log.warning("XE_TET_ALLOWED_HOSTS mở ra ngoài máy nhưng chưa đặt XE_TET_TOKEN: ai trong mạng cũng điều khiển được")


@app.middleware("http")
async def require_token(request, call_next):
    if TOKEN and request.url.path.startswith(PROTECTED):
        given = request.headers.get("x-token") or request.query_params.get("token") or ""
        if not hmac.compare_digest(given.encode(), TOKEN.encode()):
            return JSONResponse({"ok": False, "error": "cần mã điều khiển (?token=…)"}, status_code=401)
    return await call_next(request)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    hub.clients.add(ws)
    try:
        await ws.send_json(hub.state_message())
        while True:
            await ws.receive_text()  # overlay không gửi gì; giữ kết nối
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


@app.post("/api/event")
async def post_event(event: dict) -> dict:
    try:
        hub.handle(event)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return JSONResponse({"ok": False, "error": f"sự kiện không hợp lệ: {exc}"}, status_code=400)
    return {"ok": True}


@app.post("/api/admin")
async def admin(body: dict) -> dict:
    try:
        return await _admin(body)
    except Refused as exc:  # luật chơi không cho lúc này: báo nguyên văn, không gọi là «giá trị sai»
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"ok": False, "error": f"giá trị không hợp lệ: {exc}"}, status_code=400)


async def _admin(body: dict) -> dict:
    action = body.get("action")
    engine = hub.engine
    if action == "skip":
        engine.skip()
    elif action == "reset":
        hub.engine = hub.new_engine()
    elif action == "pause":
        engine.paused = bool(body.get("paused"))
    elif action == "extend":
        engine.extend(float(body.get("seconds") or 30))
    elif action == "sim":
        rate = max(0.0, min(20.0, float(body.get("rate") or 0)))
        if rate and hub.bridge.active:
            return JSONResponse({"ok": False, "error": "đang nối TikTok thật: không bật giả lập (tương tác giả)"},
                                status_code=409)
        hub.sim_rate = rate
    elif action == "feature":  # chiếu xe nào lên màn hình (0 = xe chính); góc máy dùng chung phần Camera
        engine.feature(as_int(body.get("bus_no"), 0))
    elif action == "relief":  # gọi thêm xe tăng cường cho một làn
        engine.add_relief(str(body.get("lane") or ""))
    elif action == "music_next":  # qua / lùi bài nhạc của một xe (0 = xe chính)
        engine.music_step(as_int(body.get("bus_no"), 0), 1 if as_int(body.get("step"), 1) >= 0 else -1)
    elif action == "music_set":  # chọn đúng một bài cho một xe (danh sách thả xuống trên /control)
        engine.music_set(as_int(body.get("bus_no"), 0), as_int(body.get("index"), -1))
    elif action == "music_toggle":
        engine.music_toggle(as_int(body.get("bus_no"), 0))
    elif action == "relief_next":  # xe tăng cường tới ngay điểm thả khách kế tiếp
        engine.relief_next_stop(as_int(body.get("bus_no"), 0))
    elif action == "departure":
        hub.engine.set_departure(str(body.get("key") or ""))  # BR-8: bến chưa trống → ValueError → 400
        hub.update_settings({"departure": hub.engine.network.departure.key})
    elif action == "tiktok_connect":
        username = await hub.bridge.connect(str(body.get("username") or ""))
        hub.sim_rate = 0.0  # live thật thì tắt hẳn giả lập
        hub.update_settings({"tiktok_user": username, "tiktok_auto": True})
    elif action == "tiktok_disconnect":
        await hub.bridge.disconnect()
        hub.update_settings({"tiktok_auto": False})
    elif action == "settings":
        hub.update_settings(body.get("changes") or {})
    elif action == "say":
        text = str(body.get("text") or "").strip()[:120]
        if text:
            await hub.broadcast({"kind": "event", "type": "loxe", "text": text})
            hub.voice.offer(text, voice.ADMIN)  # câu admin gõ: luôn đọc, đọc trước
    elif action == "announce":
        title = str(body.get("title") or "").strip()[:60]
        if title:
            await hub.broadcast({"kind": "event", "type": "announce", "title": title,
                                 "text": str(body.get("text") or "").strip()[:160],
                                 "seconds": max(3, min(30, int(body.get("seconds") or 8)))})
    else:
        return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
    await hub.broadcast(hub.state_message())  # màn hình đổi ngay, không chờ nhịp 0,2 s
    return {"ok": True}


@app.get("/api/state")
async def state() -> dict:
    message = hub.state_message()
    message.pop("kind")
    return message


@app.post("/api/music")
async def upload_music(request: Request, name: str = "") -> dict:
    """Tải một bài nhạc lên (thân request là nội dung file, `?name=` là tên file) — bảng điều khiển gửi từng file."""
    try:
        target = music.upload_target(name)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    part = target.with_name(target.name + ".part")  # ghi xong mới đổi tên: danh sách không thấy file dở dang
    size = 0
    try:
        with part.open("wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > music.MAX_BYTES:
                    raise ValueError(f"File quá lớn (tối đa {music.MAX_BYTES // 1024 // 1024} MB)")
                fh.write(chunk)
        if not size:
            raise ValueError("File rỗng")
        part.rename(target)
    except ValueError as exc:
        part.unlink(missing_ok=True)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=413 if size else 400)
    await hub.broadcast(hub.state_message())
    return {"ok": True, "name": target.name}


@app.delete("/api/music/{name}")
async def delete_music(name: str) -> dict:
    try:
        music.remove(name)
    except FileNotFoundError:
        return JSONResponse({"ok": False, "error": "Không có bài này"}, status_code=404)
    await hub.broadcast(hub.state_message())
    return {"ok": True}


@app.get("/control")
async def control() -> FileResponse:
    return FileResponse(HERE / "control.html")


music.MUSIC_DIR.mkdir(parents=True, exist_ok=True)  # thư mục nhạc của anh (thả file vào là có trong danh sách)
app.mount("/music", StaticFiles(directory=music.MUSIC_DIR), name="music")
voice.VOICE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/voice", StaticFiles(directory=voice.VOICE_DIR), name="voice")
if OVERLAY_DIST.exists():
    app.mount("/", StaticFiles(directory=OVERLAY_DIST, html=True), name="overlay")
