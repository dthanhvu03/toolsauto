"""Giọng lơ xe (PLAN-128): soạn câu từ sự kiện, gom tên lên xe, hàng đợi ưu tiên, đọc + lưu sẵn (không gọi mạng thật)."""

import asyncio
import io
import wave

import httpx

from xe_tet.server import voice
from xe_tet.server.voice import ADMIN, BOARD, Announcer, names_phrase, speakable, spoken_name


def announcer(settings=None):
    async def emit(_msg):
        return None
    return Announcer(emit=emit, settings=lambda: settings or {"voice_on": True, "voice_name": "Adam"})


def texts(a):
    return [t for _, _, t in a.queue]


def test_text_is_made_speakable():
    assert speakable("Xe số 3 xuất bến, 1676 km!") == "Xe số 3 xuất bến, 1676 ki-lô-mét."
    assert speakable("TP.HCM → Hà Nội") == "Thành phố Hồ Chí Minh → Hà Nội"
    assert spoken_name("🌸Bé Na🌸 ✨") == "Bé Na" and spoken_name("✨✨") == "bạn"
    assert names_phrase(["An"]) == "An"
    assert names_phrase(["An", "Bình"]) == "An và Bình"
    assert names_phrase(["A", "B", "C", "D", "E"]) == "A, B, C và 2 người nữa"


def test_dropoff_reads_names_and_engine_line_is_silent():
    a = announcer()
    a.observe({"type": "loxe", "text": "Nghệ An tới rồi bà con ơi!", "speak": False}, 0)
    a.observe({"type": "dropoff", "province": "Nghệ An", "people": [{"name": "Minh Anh"}, {"name": "Thu Hà"}]}, 0)
    (said,) = texts(a)
    assert "Nghệ An" in said and "Minh Anh và Thu Hà" in said  # câu bốc ngẫu nhiên, đủ tỉnh + tên


def test_relief_dropoff_read_only_when_on_screen():
    a = announcer()
    event = {"type": "relief_dropoff", "bus_no": 5, "province": "Cà Mau", "people": [{"name": "Út"}]}
    a.observe(event, 0, featured=None)
    assert not a.queue
    a.observe(event, 0, featured=5)
    (said,) = texts(a)
    assert "Cà Mau" in said and "Út" in said


def test_boarding_names_are_batched_and_rate_limited():
    a = announcer()
    for name in ("An", "Bình", "Chi", "Dũng"):
        a.observe({"type": "ticket", "name": name, "province": "Huế"}, 0)
    a.tick(1)
    assert not a.queue  # còn đang gom
    a.tick(3.5)
    (said,) = texts(a)
    assert "An, Bình, Chi và 1 người nữa" in said and "Huế" in said
    a.queue.clear()
    a.observe({"type": "ticket", "name": "Em", "province": "Huế"}, 5)
    a.tick(9)  # chưa đủ 8 giây từ câu trước
    assert not a.queue


def test_queued_and_pickup_tickets_are_not_read_as_boarding():
    """Anh báo 02/11: lơ xe vừa «ai đi Cà Mau đợi chuyến sau» thì giọng đọc lại «… về Cà Mau, lên xe» — vé giữ chỗ chuyến
    sau / hẹn bắt xe dọc đường không được đọc như lên xe."""
    a = announcer()
    a.observe({"type": "ticket", "name": "Út", "province": "Cà Mau", "next": True}, 0)
    a.observe({"type": "ticket", "name": "Ba", "province": "Huế", "next": False, "pickup": "Quảng Nam"}, 0)
    a.tick(4)
    assert not a.queue
    a.observe({"type": "ticket", "name": "An", "province": "Hà Nội", "next": False}, 5)
    a.tick(9)
    (said,) = texts(a)
    assert "An" in said and "Út" not in said and "Ba" not in said


def test_gift_thanks_once_per_cooldown_and_not_for_relief_gift():
    a = announcer()
    gift = {"type": "gift", "name": "Ba", "tier_up": True, "perk": "pháo hoa ngay"}
    a.observe(gift, 0)
    a.observe(gift, 10)
    a.observe({**gift, "name": "Út", "perk": "🚌 xe tăng cường chạy ngay cho bà con…"}, 0)
    (said,) = texts(a)
    assert "Ba" in said  # cảm ơn đúng một lần, quà gọi xe tăng cường không cảm ơn trùng


def test_queue_keeps_important_lines_and_admin_first():
    a = announcer()
    for i in range(3):
        a.offer(f"câu lơ xe {i}", voice.LOXE)
    a.offer("tên lên xe", BOARD)  # hàng đã dồn 3 câu: bỏ
    a.offer("Chào bà con!", ADMIN)  # admin luôn vào, đọc trước
    assert texts(a)[0] == "Chào bà con." and "tên lên xe" not in texts(a)
    off = announcer({"voice_on": False})
    off.offer("không đọc", ADMIN)
    assert not off.queue


def wav_bytes(seconds=1.0, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return buf.getvalue()


def test_render_uses_vieneu_then_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "VOICE_DIR", tmp_path)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=wav_bytes(2.0))

    async def scenario():
        a = announcer()
        a.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        first = await a.render("Xin chào bà con")
        second = await a.render("Xin chào bà con")
        await a.client.aclose()
        return first, second

    first, second = asyncio.run(scenario())
    assert first == second and first[0].endswith(".wav") and abs(first[1] - 2.0) < 0.01
    assert len(calls) == 1  # lần hai lấy từ file đã lưu


def test_render_falls_back_to_edge_when_vieneu_down(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "VOICE_DIR", tmp_path)

    class FakeEdge:
        def __init__(self, text, voice_name):
            self.voice = voice_name

        async def save(self, path):
            open(path, "wb").write(b"\0" * 12000)

    monkeypatch.setattr(voice.edge_tts, "Communicate", FakeEdge)

    async def scenario():
        a = announcer()
        a.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
        result = await a.render("Xe chạy rồi")
        await a.client.aclose()
        return result

    name, seconds = asyncio.run(scenario())
    assert name.endswith(".mp3") and seconds == 2.0



def test_microsoft_voice_choice_and_rate_pacing(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "VOICE_DIR", tmp_path)
    used = []

    class FakeEdge:
        def __init__(self, text, voice_name):
            used.append(voice_name)

        async def save(self, path):
            open(path, "wb").write(b"\0" * 12000)  # ≈ 2 giây

    monkeypatch.setattr(voice.edge_tts, "Communicate", FakeEdge)
    sent = []

    async def emit(msg):
        sent.append(msg)

    async def scenario():
        a = Announcer(emit=emit, settings=lambda: {"voice_on": True, "voice_name": "ms:vi-VN-HoaiMyNeural", "voice_rate": 1.25})
        a.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
        name, seconds = await a.render("Chào bà con")
        await a.client.aclose()
        return name, seconds

    name, seconds = asyncio.run(scenario())
    assert used == ["vi-VN-HoaiMyNeural"] and name.endswith(".mp3")  # chọn giọng Microsoft: không hỏi VieNeu
    from xe_tet.server import settings as settings_module
    assert settings_module.clean({"voice_rate": 9})["voice_rate"] == 1.6
    assert settings_module.clean({"voice_rate": "0.1"})["voice_rate"] == 0.8



def test_every_talk_line_fills_its_fields():
    """Mọi câu ở mọi kiểu nói điền đủ chỗ trống (gõ sai {tên} là lỗi giữa live); đọc đều: không «!», không đuôi «nha»."""
    import random
    import re
    from xe_tet.server.game.talk import LINES, STYLES, TALK_STYLES, hours_phrase, line, options
    fields = dict(dest="Hà Nội", n=5, hours=hours_phrase(26.4), place="Phú Yên", specialty="cá ngừ, bánh hỏi",
                  prov="Nghệ An", station="Bến xe Giáp Bát", total="1.000", name="Út", names="An và Bình",
                  lunar="26 Chạp", other="Bình", need=3, others="Cà Mau, Đồng Tháp", no=3, next="Huế", km="120", pos=2, label="Taxi", xu=20)
    kinds = set(LINES[STYLES[0]])
    assert all(set(LINES[style]) == kinds for style in STYLES)  # kiểu nào cũng đủ mọi tình huống
    for style in TALK_STYLES:
        for kind in kinds:
            texts = options(kind, style)
            assert texts
            for i in range(len(texts)):
                text = line(kind, random.Random(i), style, **fields)
                assert "{" not in text and text.strip() and "!" not in text, (style, kind, text)
                assert not re.search(r"\bnha\b", text, re.IGNORECASE), (style, kind, text)
    assert len(options("boarding", "mix")) == sum(len(LINES[s]["boarding"]) for s in STYLES)
    assert hours_phrase(26.4) == "chừng 26 tiếng" and hours_phrase(0.4) == "chừng 20 phút"
    assert speakable("Chào bà con tối nay!!") == "Chào bà con tối nay."  # câu admin gõ cũng đọc đều
