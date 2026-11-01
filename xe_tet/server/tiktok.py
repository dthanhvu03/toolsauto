"""Cầu nối TikTok LIVE → luật chơi (thư viện TikTokLive 7, không chính thức, ký qua Euler Stream).

- Chỉ đọc sự kiện công khai của phòng live: không cookie, không mật khẩu TikTok. Khoá Euler (nếu có) đặt `SIGN_API_KEY`.
- Thư viện chỉ nạp khi bấm kết nối → server vẫn chạy ở venv không cài TikTokLive (thử bằng /control, giả lập).
- Học từ 2 repo cùng ngách (README mục 5b): không phát lại tin cũ khi nối (`process_connect_events=False`),
  khoá người xem = userId, quà combo chỉ cộng phần tăng, follow / share lấy từ sự kiện riêng của thư viện.
- Cả 2 repo đó không tự nối lại; ở đây rớt mạng thì thử lại 5 → 10 → 20 → 40 → 60 s, live kết thúc thì dừng,
  tài khoản chưa live thì chờ và tự vào khi live bắt đầu.
"""

import asyncio
import logging
import re
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .game.engine import VN

log = logging.getLogger("xe_tet")

BACKOFF = (5, 10, 20, 40, 60)
OFFLINE_RETRY = 30  # tài khoản chưa live: hỏi lại mỗi 30 s
STABLE_SECONDS = 60  # kết nối giữ được ≥ 60 s mới đưa bậc chờ về đầu (vào-rớt liên tục không được đốt lượt ký Euler)
GONE_AFTER = 10 * 60  # đã từng vào live rồi «chưa live» suốt 10 phút → coi như live đã kết thúc (lỡ mất LiveEndEvent)
COMBO_MEMORY = 500
LIKES_PER_EVENT_MAX = 50
_USERNAME = re.compile(r"^[A-Za-z0-9._]{2,24}$")


def parse_username(raw: str) -> str:
    """«@abc», «tiktok.com/@abc/live?…», «abc» → «abc»; sai dạng thì chuỗi rỗng."""
    text = str(raw or "").strip()
    match = re.search(r"tiktok\.com/@([^/?#\s]+)", text, re.IGNORECASE)
    name = match.group(1) if match else text.lstrip("@").split("/")[0].split("?")[0]
    return name if _USERNAME.match(name) else ""


def _user(user: Any) -> tuple[str, str, str]:
    """(uid cố định, tên hiện, ảnh đại diện) — uid = userId vì @handle đổi được."""
    if user is None:
        return "", "", ""
    uid = str(getattr(user, "id", 0) or getattr(user, "id_str", "") or getattr(user, "display_id", "") or "")
    name = getattr(user, "nickname", "") or getattr(user, "display_id", "") or ""
    thumb = getattr(user, "avatar_thumb", None)
    urls = getattr(thumb, "url_list", None) or []
    return uid, name, (urls[0] if urls else "")


def _base(event: Any) -> dict:
    uid, name, avatar = _user(getattr(event, "user", None))
    return {"uid": f"tt:{uid}" if uid else "", "name": name, "avatar": avatar}


class GiftCombos:
    """Quà loại combo: TikTok gửi nhiều sự kiện cho một lượt bấm liên tục (repeat_count tăng dần).
    Chỉ trả về phần tăng so với lần trước → phản hồi ngay từng lần bấm mà không đếm trùng."""

    def __init__(self) -> None:
        self._seen: OrderedDict[str, int] = OrderedDict()

    def delta(self, key: str, repeat: int, streakable: bool, ended: bool) -> int:
        repeat = max(1, repeat)
        if not streakable:
            return repeat
        before = self._seen.pop(key, 0)
        if not ended:
            self._seen[key] = max(before, repeat)
            while len(self._seen) > COMBO_MEMORY:
                self._seen.popitem(last=False)
        return max(0, repeat - before)


def map_event(kind: str, event: Any, combos: GiftCombos) -> dict | None:
    """Đổi sự kiện TikTokLive sang sự kiện của luật chơi (xem engine.handle). Trả None nếu bỏ qua."""
    base = _base(event)
    if not base["uid"]:
        return None
    if kind == "comment":
        text = str(getattr(event, "content", "") or "")
        return {"type": "comment", "text": text[:200], **base} if text.strip() else None
    if kind == "like":
        count = int(getattr(event, "count", 0) or 1)
        return {"type": "like", "count": max(1, min(LIKES_PER_EVENT_MAX, count)), **base}
    if kind == "gift":
        gift = getattr(event, "gift", None)
        streakable = bool(getattr(gift, "streakable", False)) if gift is not None else False
        group = getattr(event, "group_id", 0) or getattr(event, "gift_id", 0)
        n = combos.delta(f"{base['uid']}:{group}", int(getattr(event, "repeat_count", 1) or 1),
                         streakable, bool(getattr(event, "repeat_end", 0)))
        if n <= 0:
            return None
        diamonds = int(getattr(gift, "diamond_count", 0) or 1) * n
        name = str(getattr(gift, "name", "") or "quà")
        return {"type": "gift", "diamonds": diamonds, "gift": f"{name} ×{n}" if n > 1 else name, **base}
    if kind in ("follow", "share", "join"):
        return {"type": kind, **base}
    return None


def _event_classes() -> dict[str, type]:
    from TikTokLive.events import (CommentEvent, FollowEvent, GiftEvent, JoinEvent, LikeEvent, LiveEndEvent,
                                   RoomUserSeqEvent, ShareEvent)
    return {"comment": CommentEvent, "gift": GiftEvent, "like": LikeEvent, "follow": FollowEvent,
            "share": ShareEvent, "join": JoinEvent, "viewers": RoomUserSeqEvent, "end": LiveEndEvent}


def _default_client(username: str) -> Any:
    from TikTokLive import TikTokLiveClient
    return TikTokLiveClient(unique_id=username)


class TikTokBridge:
    """Giữ một kết nối tới phòng live; mọi sự kiện đã đổi đi qua `emit` (Hub → Engine)."""

    def __init__(self, emit: Callable[[dict], None], client_factory: Callable[[str], Any] = _default_client,
                 event_classes: Callable[[], dict[str, Any]] = _event_classes,
                 sleep: Callable[[float], Any] = asyncio.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._emit = emit
        self._clock = clock
        self._factory = client_factory
        self._classes = event_classes
        self._sleep = sleep
        self._task: asyncio.Task | None = None
        self._client: Any = None
        self._stop = False
        self._ended = False
        self.combos = GiftCombos()
        self.logs: deque[str] = deque(maxlen=40)
        self.status: dict = {"state": "idle", "username": "", "room_id": None, "viewers": 0,
                             "events": 0, "error": "", "retry_in": 0, "since": None}

    # ---- trạng thái ----------------------------------------------------

    def _set(self, state: str, **extra) -> None:
        self.status.update(state=state, **extra)

    def _log(self, line: str) -> None:
        self.logs.append(f"{datetime.now(VN):%H:%M:%S} {line}")
        log.info("tiktok: %s", line)

    def public(self) -> dict:
        return {**self.status, "logs": list(self.logs)[-12:]}

    @property
    def active(self) -> bool:
        return self._task is not None and not self._task.done()

    # ---- điều khiển ----------------------------------------------------

    async def connect(self, raw: str) -> str:
        username = parse_username(raw)
        if not username:
            raise ValueError("cần @username hoặc link tiktok.com/@…")
        await self.disconnect()
        self._stop = False
        self._ended = False
        self.combos = GiftCombos()
        self._set("connecting", username=username, error="", retry_in=0, room_id=None, viewers=0, events=0)
        self._log(f"Kết nối @{username}…")
        self._task = asyncio.create_task(self._run(username))
        return username

    async def disconnect(self) -> None:
        self._stop = True
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                log.debug("ngắt TikTok lỗi", exc_info=True)
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self.status["state"] != "idle":
            self._log("Đã ngắt kết nối")
        self._set("idle", retry_in=0, since=None)

    # ---- vòng kết nối --------------------------------------------------

    def _wire(self, client: Any) -> None:
        classes = self._classes()

        def handler(kind: str):
            async def on_event(event: Any) -> None:
                try:
                    if kind == "viewers":
                        self.status["viewers"] = int(getattr(event, "total", 0) or 0)
                        return
                    if kind == "end":
                        self._ended = True
                        self._log("Live đã kết thúc")
                        return
                    mapped = map_event(kind, event, self.combos)
                    if mapped:
                        self.status["events"] += 1
                        self._emit(mapped)
                except Exception:
                    log.exception("xử lý sự kiện TikTok %s lỗi", kind)
            return on_event

        for kind, cls in classes.items():
            client.add_listener(cls, handler(kind))

    async def _run(self, username: str) -> None:
        clock = self._clock
        attempt = 0
        was_live = False
        offline_since: float | None = None
        while not self._stop:
            client = self._factory(username)
            self._client = client
            self._wire(client)
            reason = ""
            try:
                task = await client.start(process_connect_events=False, fetch_live_check=True)
                was_live, offline_since = True, None
                started = clock()
                self._set("connected", room_id=getattr(client, "room_id", None), error="", retry_in=0,
                          since=time.time())
                self._log(f"✅ Đã vào phòng live @{username}")
                await task
                if clock() - started >= STABLE_SECONDS:
                    attempt = 0
                reason = "mất kết nối"
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # phân loại theo tên lớp lỗi của thư viện
                name = type(exc).__name__
                if name == "UserNotFoundError":
                    self._set("error", error=f"Không tìm thấy @{username}")
                    self._log(f"❌ Không tìm thấy @{username}")
                    return
                if name == "AgeRestrictedError":
                    self._set("error", error="Phòng live giới hạn tuổi, thư viện không đọc được")
                    self._log("❌ Phòng live giới hạn tuổi")
                    return
                reason = {"UserOfflineError": "chưa live",
                          "SignatureRateLimitError": "Euler giới hạn lượt ký (gói miễn phí)"}.get(name, f"{name}: {exc}")
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            if self._stop:
                return
            if self._ended:
                self._set("ended", retry_in=0)
                return
            if reason == "chưa live" and was_live:
                offline_since = offline_since if offline_since is not None else clock()
                if clock() - offline_since >= GONE_AFTER:
                    self._set("ended", retry_in=0)
                    self._log("Live đã tắt hơn 10 phút — dừng chờ")
                    return
            if reason == "chưa live":
                delay, state = OFFLINE_RETRY, "offline"
            else:
                delay, state = BACKOFF[min(attempt, len(BACKOFF) - 1)], "reconnecting"
                attempt += 1
            self._set(state, error=reason, retry_in=delay)
            self._log(f"⚠ {reason} — thử lại sau {delay} s")
            await self._sleep(delay)
