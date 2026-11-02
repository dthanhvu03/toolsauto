"""Giọng Anh Tư lơ xe (PLAN-128): đọc câu lơ xe, tên người xuống xe / lên xe, cảm ơn quà.

- Đọc bằng VieNeu-TTS chạy trên máy (PM2 `VieNeu_TTS`, cổng 8790); VieNeu tắt / lỗi thì dùng edge-tts (Microsoft online).
- Câu đã đọc lưu file (`storage/media/xe_tet/voice/`, tên theo băm giọng + câu) → câu lặp lại phát ngay.
- Một hàng đợi theo mức ưu tiên, phát lần lượt (đợi hết câu trước): đông quá thì bỏ bớt câu ít quan trọng (đọc tên lên
  xe) chứ không đọc chồng nhau; câu admin gõ luôn được đọc.
"""

import asyncio
import hashlib
import io
import logging
import os
import re
import time
import wave
from collections.abc import Awaitable, Callable
from pathlib import Path

import edge_tts
import httpx

from .game.talk import line

log = logging.getLogger("xe_tet")

ROOT = Path(__file__).resolve().parents[2]
VOICE_DIR = Path(os.getenv("XE_TET_VOICE_DIR") or ROOT / "storage" / "media" / "xe_tet" / "voice")
VIENEU_URL = os.getenv("XE_TET_VIENEU", "http://127.0.0.1:8790")
VIENEU_TIMEOUT = 15.0
EDGE_VOICE = "vi-VN-NamMinhNeural"  # dự phòng: giọng nam Microsoft
# Giọng Microsoft chọn được trên /control (tiền tố «ms:»): neural, thường tự nhiên hơn — cần Internet, câu (có tên người xem)
# gửi lên Microsoft. Giọng VieNeu là tên trơn.
MS_VOICES = ({"name": "ms:vi-VN-NamMinhNeural", "label": "Nam Minh", "gender": "male", "region": "Microsoft"},
             {"name": "ms:vi-VN-HoaiMyNeural", "label": "Hoài My", "gender": "female", "region": "Microsoft"})
CACHE_KEEP = 600  # giữ 600 câu gần nhất (~ vài chục MB)
VOICES_REFRESH = 60.0

# mức ưu tiên: số nhỏ đọc trước; hàng đợi dài quá QUEUE_SOFT thì bỏ câu từ mức LOW trở đi
ADMIN, DROPOFF, GIFT, LOXE, BOARD = range(5)
LOW = LOXE
QUEUE_SOFT = 3
BOARD_WINDOW = 3.0  # gom tên người lên xe trong 3 giây thành một câu
BOARD_GAP = 8.0  # hai câu đọc tên lên xe cách nhau tối thiểu 8 giây
GIFT_COOLDOWN = 30.0  # mỗi người được cảm ơn quà tối đa một lần / 30 giây
NAMES_READ = 3  # đọc tối đa 3 tên, còn lại «và N người nữa»

# chữ viết tắt / ký hiệu đọc sai → chữ đọc được
SAY_AS = (("TP.HCM", "Thành phố Hồ Chí Minh"), ("km", "ki-lô-mét"), ("BR-VT", "Bà Rịa Vũng Tàu"))
# đọc đều, không nhấn nhá (anh dặn 01/11): «!» đọc như dấu chấm, kể cả câu admin gõ
_EXCLAIM = re.compile(r"!+")
_NOT_NAME = re.compile(r"[^\w\s'-]", re.UNICODE)  # tên TikTok: bỏ emoji / ký tự trang trí


def speakable(text: str) -> str:
    for short, full in SAY_AS:
        text = re.sub(rf"\b{re.escape(short)}\b", full, text)
    text = _EXCLAIM.sub(".", text)
    return re.sub(r"\s+", " ", text).strip()


def spoken_name(name: str) -> str:
    clean = re.sub(r"\s+", " ", _NOT_NAME.sub(" ", name).replace("_", " ")).strip()
    return clean[:24] or "bạn"


def names_phrase(names: list[str]) -> str:
    """«Minh Anh, Thu Hà và Bé Na» / «Minh Anh, Thu Hà, Bé Na và 5 người nữa»."""
    named = [spoken_name(n) for n in names[:NAMES_READ]]
    more = len(names) - len(named)
    if more > 0:
        return f"{', '.join(named)} và {more} người nữa"
    return named[0] if len(named) == 1 else f"{', '.join(named[:-1])} và {named[-1]}"


class Announcer:
    """Nhận sự kiện game → soạn câu → đọc (VieNeu / edge-tts) → phát cho overlay qua `emit` (sự kiện `speak`)."""

    def __init__(self, emit: Callable[[dict], Awaitable[None]], settings: Callable[[], dict]):
        self.emit = emit
        self.settings = settings
        self.queue: list[tuple[int, int, str]] = []  # (ưu tiên, thứ tự, câu)
        self.wake = asyncio.Event()
        self.seq = 0
        self.boarding: list[tuple[str, str]] = []  # (tên, tỉnh) chờ gom
        self.board_started = 0.0
        self.last_board = -1e9
        self.thanked: dict[str, float] = {}
        self.voice_list: list[dict] = []  # giọng VieNeu cho /control (refresh_voices cập nhật)
        self._voices_at = -1e9

    # ---- soạn câu từ sự kiện ----------------------------------------------------------------------

    def observe(self, event: dict, now: float, featured: int | None = None) -> None:
        kind = event.get("type")
        if kind == "loxe" and event.get("speak", True):
            self.offer(event.get("text", ""), LOXE)
        elif kind == "dropoff" or (kind == "relief_dropoff" and event.get("bus_no") == featured):
            names = [p["name"] for p in event.get("people", [])]
            if names:
                self.offer(line("dropoff", style=self.style(), prov=event["province"], names=names_phrase(names)),
                           DROPOFF)
        # chỉ đọc «lên xe» cho người có giường ngay trên xe đang đón — giữ chỗ chuyến sau (next) / hẹn bắt xe dọc đường (pickup)
        # đã có câu riêng của lơ xe; đọc chung thì vừa «đợi chuyến sau» lại «lên xe» (anh báo 02/11)
        elif kind == "ticket" and not event.get("changed") and not event.get("next") and not event.get("pickup"):
            if not self.boarding:
                self.board_started = now
            self.boarding.append((event.get("name", ""), event.get("province", "")))
        elif kind == "gift" and event.get("tier_up") and "xe tăng cường" not in (event.get("perk") or ""):
            name = event.get("name", "")
            if now - self.thanked.get(name, -1e9) >= GIFT_COOLDOWN:  # quà bao xe tăng cường: lơ xe đã nói rồi
                self.thanked[name] = now
                who = spoken_name(name)
                if event.get("first_gift"):
                    text = line("first_gift", style=self.style(), name=who, n=event.get("bus_no") or 1)
                elif event.get("province"):
                    text = line("gift_prov", style=self.style(), name=who, prov=event["province"])
                else:
                    text = line("gift", style=self.style(), name=who)
                self.offer(text, GIFT)

    def tick(self, now: float) -> None:
        """Gom xong tên người lên xe (sau BOARD_WINDOW giây) thì soạn một câu."""
        if not self.boarding or now - self.board_started < BOARD_WINDOW:
            return
        people, self.boarding = self.boarding, []
        if now - self.last_board < BOARD_GAP:
            return  # phòng đông: bỏ lượt này, thẻ trên màn hình vẫn hiện tên
        self.last_board = now
        provinces = {p for _, p in people}
        names = names_phrase([n for n, _ in people])
        self.offer(line("board", style=self.style(), prov=provinces.pop(), names=names) if len(provinces) == 1
                   else line("board_mixed", style=self.style(), names=names), BOARD)

    def style(self) -> str:
        return self.settings().get("talk_style") or "mix"

    def offer(self, text: str, priority: int) -> None:
        text = speakable(text)
        if not text or not self.settings().get("voice_on", True):
            return
        if priority >= LOW and len(self.queue) >= QUEUE_SOFT:
            return  # đang dồn: bỏ câu ít quan trọng
        self.seq += 1
        self.queue.append((priority, self.seq, text))
        self.queue.sort()
        self.wake.set()

    # ---- đọc + phát ---------------------------------------------------------------------------------

    async def run(self) -> None:
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=VIENEU_TIMEOUT) as client:
            self.client = client
            while True:
                if not self.queue:
                    self.wake.clear()
                    await self.wake.wait()
                    continue
                _, _, text = self.queue.pop(0)
                try:
                    name, seconds = await self.render(text)
                except Exception:
                    log.exception("lơ xe đọc lỗi: %s", text)
                    continue
                rate = float(self.settings().get("voice_rate") or 1.0)  # overlay phát nhanh / chậm theo tốc độ này
                await self.emit({"kind": "event", "type": "speak", "url": f"/voice/{name}", "text": text,
                                 "seconds": round(seconds / rate, 2)})
                await asyncio.sleep(seconds / rate + 0.3)  # đọc hết câu mới sang câu sau

    async def render(self, text: str) -> tuple[str, float]:
        voice = self.settings().get("voice_name") or "Adam"
        key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:20]
        for ext in (".wav", ".mp3"):
            path = VOICE_DIR / f"{key}{ext}"
            if path.exists():
                path.touch()
                return path.name, duration(path)
        if voice.startswith("ms:"):  # anh chọn giọng Microsoft
            path = VOICE_DIR / f"{key}.mp3"
            await edge_tts.Communicate(text, voice[3:]).save(str(path))
            self.prune()
            return path.name, duration(path)
        try:
            res = await self.client.post(f"{VIENEU_URL}/tts", json={"text": text, "voice": voice})
            res.raise_for_status()
            path = VOICE_DIR / f"{key}.wav"
            path.write_bytes(res.content)
        except Exception as exc:  # VieNeu tắt / quá tải → giọng Microsoft
            log.warning("VieNeu không đọc được (%s), dùng edge-tts", exc)
            path = VOICE_DIR / f"{key}.mp3"
            await edge_tts.Communicate(text, EDGE_VOICE).save(str(path))
        self.prune()
        return path.name, duration(path)

    @staticmethod
    def prune() -> None:
        files = sorted(VOICE_DIR.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[CACHE_KEEP:]:
            old.unlink(missing_ok=True)

    async def watch_voices(self) -> None:
        """Chạy nền suốt buổi: hỏi lại danh sách giọng mỗi phút (tách khỏi vòng game — VieNeu đang bận đọc thì /health chậm)."""
        while True:
            await self.refresh_voices()
            await asyncio.sleep(VOICES_REFRESH)

    async def refresh_voices(self) -> None:
        """Hỏi VieNeu danh sách giọng (tên, nam / nữ, miền) cho /control — mỗi phút một lần; VieNeu tắt thì danh sách rỗng."""
        if time.monotonic() - self._voices_at < VOICES_REFRESH:
            return
        self._voices_at = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                res = await client.get(f"{VIENEU_URL}/health")
            vieneu = [{k: v.get(k) for k in ("name", "gender", "region")} for v in res.json().get("voices", [])]
        except Exception:
            vieneu = []
        self.voice_list = vieneu + list(MS_VOICES)


def duration(path: Path) -> float:
    if path.suffix == ".wav":
        with wave.open(io.BytesIO(path.read_bytes())) as w:
            return w.getnframes() / w.getframerate()
    return path.stat().st_size / 6000  # mp3 edge-tts 48 kbps ≈ 6 KB / giây
