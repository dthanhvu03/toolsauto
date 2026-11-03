"""PLAN-135: lơ xe trả lời câu hỏi trong comment — câu sẵn + AI Gemini (client giả, không gọi mạng)."""
import asyncio

from xe_tet.server import ai_reply
from xe_tet.server import app as app_module
from xe_tet.server.game.answers import faq, is_question
from xe_tet.server.game.engine import ASK_GAP, ASK_PER_VIEWER, Engine


def comment(engine, name, text, t):
    engine.handle({"type": "comment", "name": name, "text": text}, t)


def loxe(engine):
    return [ev["text"] for ev in engine.drain() if ev["type"] == "loxe"]


def test_questions_are_recognised_without_eating_game_commands():
    assert faq("có ghé dọc đường hông bác tài") == "via" and faq("sao xe chưa chạy") == "depart"
    assert faq("khi nào xe chạy") == "depart" and faq("bao giờ xe chạy vậy") == "depart"
    assert faq("chơi sao vậy") == "how" and faq("tặng quà được gì vậy") == "gift" and faq("quê sáp nhập rồi gõ sao") == "newname"
    for text in ("anh tư ơi", "xe đi đâu vậy", "bao giờ tới Tết?"):
        assert is_question(text), text
    for text in ("đẹp quá", "đi nào", "hihi", "ok", "về quê thôi"):
        assert not is_question(text), text
    e = Engine(0.0)
    comment(e, "Phú", "Phú thọ", 1)  # lệnh game vẫn là lệnh game
    assert e.bus.riders() and not e.questions


def test_common_questions_get_ready_answers_spaced_out():
    e = Engine(0.0)
    e.drain()
    comment(e, "H Dziii", "có ghé dọc đường hông bác tài", 1)
    said = loxe(e)
    assert len(said) == 1 and "H Dziii" in said[0] and "dọc đường" in said[0] and "!" not in said[0]
    comment(e, "Vịt", "chơi sao vậy", 1 + ASK_GAP / 2)  # cả phòng: chưa đủ giãn cách
    assert not loxe(e)
    comment(e, "Vịt", "chơi sao vậy", 1 + ASK_GAP + 1)
    assert "gõ tên tỉnh" in loxe(e)[0]
    comment(e, "H Dziii", "khi nào xe chạy", 2 + ASK_GAP * 2)  # cùng người hỏi lại trong 30 giây
    assert not loxe(e)
    comment(e, "H Dziii", "khi nào xe chạy", 2 + ASK_PER_VIEWER + ASK_GAP)
    assert "xuất bến sau" in loxe(e)[0]


def test_other_questions_wait_for_ai_only_when_enabled():
    e = Engine(0.0)
    comment(e, "An", "anh tư ơi xe có wifi không", 1)
    assert not e.questions  # AI tắt: không xếp hàng
    e.ai_reply = True
    comment(e, "Bình", "anh tư ơi xe có wifi không", 2)
    comment(e, "Chi", "xe có chỗ để xe máy không", 50)
    assert [q["name"] for q in e.questions] == ["Bình", "Chi"]
    assert e.next_question(55, max_age=40)["name"] == "Chi"  # câu của Bình chờ 53 giây: bỏ
    ctx = e.ai_context("chi")
    assert ctx["phase"] == "BOARDING" and ctx["ticket"]["status"] == "none" and ctx["bus_no"] == e.bus.no


def test_ai_answers_are_cleaned_to_the_loxe_voice():
    assert ai_reply.clean("Có chứ nha!") == "Có chứ."
    assert ai_reply.clean("Anh Tư trả lời: «Xe có wifi miễn phí đó Bình ơi»") == "Xe có wifi miễn phí đó Bình ơi"
    assert ai_reply.clean("vào link www.abc.com mà xem") is None and ai_reply.clean("đm xe chậm") is None
    long = ai_reply.clean("chữ " * 100)
    assert len(long) <= ai_reply.MAX_CHARS + 1 and long.endswith(".")
    assert ai_reply.clean("") is None and ai_reply.clean(None) is None


def test_hub_answers_in_background_and_survives_ai_failure(monkeypatch):
    hub = app_module.hub
    hub.engine = hub.new_engine()
    hub.ai_cache.clear()
    hub.engine.ai_reply = True
    monkeypatch.setitem(hub.settings, "ai_reply", True)
    q = {"uid": "bình", "name": "Bình", "text": "xe có wifi không", "at": 0.0}
    seen = {}

    async def fake_ask(client, key, name, question, ctx):
        seen["ctx"] = ctx
        return "Xe có wifi đó Bình ơi, cứ gõ tên tỉnh lên xe."

    async def broken_ask(*args):
        raise RuntimeError("mạng rớt")

    monkeypatch.setattr(ai_reply, "api_key", lambda: "khoa-gia")
    monkeypatch.setattr(ai_reply, "ask", fake_ask)
    hub.engine.drain()
    asyncio.run(hub._answer(q))
    assert any(ev["type"] == "loxe" and "wifi" in ev["text"] for ev in hub.engine.drain()) and seen["ctx"]["bus_no"]
    assert not hub.ai_busy and hub.ai_answered >= 1
    monkeypatch.setattr(ai_reply, "ask", broken_ask)
    hub.ai_cache.clear()  # câu vừa trả lời đã được nhớ — xoá để lần này phải gọi AI (đang hỏng)
    asyncio.run(hub._answer(q))
    assert hub.ai_error and not hub.ai_busy  # AI lỗi: bỏ câu đó, game chạy tiếp
    monkeypatch.setattr(ai_reply, "api_key", lambda: "")
    asyncio.run(hub._answer(q))
    assert "GEMINI_API_KEY" in hub.ai_error and hub.ai_key is False


def test_same_question_reuses_answer_without_calling_ai(monkeypatch):
    """Anh hỏi 02/11: comment giống vậy nữa thì có cần gọi lại không → không: dùng lại câu trả lời (đổi tên người hỏi);
    câu có số (xe số mấy, còn bao lâu) thì không dùng lại cho người khác."""
    hub = app_module.hub
    hub.engine = hub.new_engine()
    hub.ai_cache.clear()
    calls = []

    async def fake_ask(client, key, name, question, ctx):
        calls.append(question)
        return f"Xe có wifi đó {name} ơi, cứ gõ tên tỉnh lên xe." if "wifi" in question else f"Xe số 2 đó {name}."

    monkeypatch.setattr(ai_reply, "api_key", lambda: "khoa-gia")
    monkeypatch.setattr(ai_reply, "ask", fake_ask)
    hub.engine.drain()
    asyncio.run(hub._answer({"uid": "bình", "name": "Bình", "text": "Anh Tư ơi xe có wifi không vậy", "at": 0.0}))
    asyncio.run(hub._answer({"uid": "chi", "name": "Chi", "text": "xe có wifi không", "at": 0.0}))
    said = [ev["text"] for ev in hub.engine.drain() if ev["type"] == "loxe"]
    assert len(calls) == 1 and said == ["Xe có wifi đó Bình ơi, cứ gõ tên tỉnh lên xe.", "Xe có wifi đó Chi ơi, cứ gõ tên tỉnh lên xe."]
    asyncio.run(hub._answer({"uid": "an", "name": "An", "text": "xe này xe số mấy", "at": 0.0}))
    asyncio.run(hub._answer({"uid": "dung", "name": "Dũng", "text": "xe này xe số mấy", "at": 0.0}))
    assert len(calls) == 3  # có số: hỏi lại AI


def test_gemini_request_uses_thinking_level_and_retries_without_it():
    """02/11: Gemini 3 trả 400 «invalid argument» cho thinkingBudget=0 (AI im lặng cả buổi live) → gửi thinkingLevel; vẫn 400
    thì gửi lại không kèm thinkingConfig; model dự phòng không còn là 2.5-flash (đã ngừng)."""
    import asyncio

    class Res:
        def __init__(self, code, text=""):
            self.status_code, self.text = code, text

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Xe có wifi đó Lan"}]}}]}

    sent = []

    class Client:
        async def post(self, url, json, headers, timeout):
            sent.append(json["generationConfig"])
            return Res(400, '{"error": {"message": "Request contains an invalid argument."}}') if len(sent) == 1 else Res(200)

    out = asyncio.run(ai_reply.ask(Client(), "khoa", "Lan", "xe có wifi không", {}))
    assert out == "Xe có wifi đó Lan"
    assert sent[0]["thinkingConfig"] == {"thinkingLevel": "minimal"} and "thinkingConfig" not in sent[1]
    assert "gemini-2.5-flash" not in ai_reply.MODELS
