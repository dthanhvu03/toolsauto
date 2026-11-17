"""Store chat AI: tin chữ → Xingchi/9Router; tắt / cooldown / SKIP → trang chủ."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from store_bot import chat_ai
from store_bot.bot import StoreBot
from tests.test_store_bot import BUYER, FakeTelegram, _private, _settings, product, repo  # noqa: F401


def _bot(repo, answer="Shop có Gemini/ChatGPT á, bạn bấm 🛒 Mua sản phẩm xem giá từng món nha"):
    tg = FakeTelegram()
    bot = StoreBot(_settings(), repo, tg, "test_shop_bot")
    bot.chat_ai_enabled = True
    prompts = []
    bot.chat_generate = lambda p: (prompts.append(p), (answer, {"provider": "fake"}))[1]
    # Chạy AI đồng bộ trong test (không chờ thread pool).
    bot.executor = type("E", (), {"submit": staticmethod(lambda fn, *a, **k: fn(*a, **k))})()
    return bot, tg, prompts


def test_question_gets_ai_answer(repo, product):
    bot, tg, prompts = _bot(repo)
    bot.handle_update(_private(BUYER, "shop có ChatGPT Plus không"))
    texts = tg.texts_to(BUYER)
    assert chat_ai.WORKING in texts
    assert any("Gemini/ChatGPT" in t for t in texts)
    assert "ChatGPT Plus" in prompts[0] and "Không bịa giá" in prompts[0]


def test_ack_keeps_home(repo, product):
    bot, tg, prompts = _bot(repo)
    bot.handle_update(_private(BUYER, "cảm ơn"))
    assert prompts == []
    assert any("Số dư" in t for t in tg.texts_to(BUYER))


def test_skip_or_error_falls_back_home(repo, product):
    bot, tg, _ = _bot(repo, answer="SKIP")
    bot.handle_update(_private(BUYER, "mua nick game free fire không"))
    assert any("Số dư" in t for t in tg.texts_to(BUYER))

    broken, tg2, _ = _bot(repo)
    broken.chat_generate = lambda p: (_ for _ in ()).throw(RuntimeError("gateway down"))
    broken.handle_update(_private(BUYER, "bảo hành thế nào vậy"))
    assert any("Số dư" in t for t in tg2.texts_to(BUYER))


def test_cooldown_and_off_switch(repo, product):
    bot, tg, prompts = _bot(repo)
    bot.handle_update(_private(BUYER, "có CapCut Pro không"))
    assert len(prompts) == 1
    # Cùng cooldown → trang chủ, không gọi AI
    bot.handle_update(_private(BUYER, "giá bao nhiêu"))
    assert len(prompts) == 1
    assert any("Số dư" in t for t in tg.texts_to(BUYER))
    # Giả lập hết cooldown
    past = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    bot.repo.set_state(chat_ai.LAST_PREFIX + str(BUYER), past)
    bot.handle_update(_private(BUYER, "còn Canva không"))
    assert len(prompts) == 2
    bot.repo.set_state(chat_ai.OFF_KEY, "1")
    past2 = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    bot.repo.set_state(chat_ai.LAST_PREFIX + str(BUYER), past2)
    bot.handle_update(_private(BUYER, "còn Adobe không"))
    assert len(prompts) == 2


def test_answer_strips_links_and_html():
    out = chat_ai.answer(
        "hi",
        shop_name="Test",
        catalog=["Gemini"],
        generate=lambda p: ("Xem <b>tại</b> https://evil.example nha & mua", {}),
    )
    assert out == "Xem tại nha &amp; mua"
    assert "Không bịa giá" in chat_ai.build_prompt("x", "Shop", ["A"], None)


def test_off_by_default(repo, product):
    """StoreBot trong test: chat_ai tắt → tin chữ mở trang chủ, không gọi AI."""
    tg = FakeTelegram()
    bot = StoreBot(_settings(), repo, tg, "test_shop_bot")
    assert bot.chat_ai_enabled is False
    bot.handle_update(_private(BUYER, "shop có ChatGPT không"))
    assert any("Số dư" in t for t in tg.texts_to(BUYER))
