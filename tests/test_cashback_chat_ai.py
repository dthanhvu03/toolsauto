"""PLAN-172 T2: tin chữ của khách → AI trả lời qua hàng đợi; lỗi / tin «ok» / tắt → câu mẫu cũ."""

from __future__ import annotations

from datetime import timedelta

from cashback_bot import chat_ai
from cashback_bot.messages import CHAT_TEXT
from tests.test_cashback_bot import NOW, FakeClient, payload, service

BUYER = 111


def _bot(tmp_path, answer="Bot không thu phí đâu bạn, dán link món Shopee vào là thấy số hoàn nha 😊"):
    bot = service(tmp_path, FakeClient(payload()))
    bot.tiktok_runner = lambda job: job()
    bot.chat_ai_enabled = True
    prompts = []
    bot.chat_generate = lambda p: (prompts.append(p), (answer, {"provider": "fake"}))[1]
    return bot, prompts


def _queued(bot):
    with bot.repo.connect() as conn:
        return [r["message_html"] for r in conn.execute(
            "SELECT message_html FROM admin_notifications WHERE event_type = 'CHAT_AI_ANSWER' AND chat_id = ? ORDER BY id",
            (BUYER,))]


def test_question_gets_ai_answer_via_queue(tmp_path):
    bot, prompts = _bot(tmp_path)
    reply = bot.handle_text(BUYER, "u", "bot này có thu phí không vậy", update_id=1, now=NOW)
    assert reply.text == chat_ai.WORKING
    assert _queued(bot) == ["Bot không thu phí đâu bạn, dán link món Shopee vào là thấy số hoàn nha 😊"]
    assert "có thu phí không" in prompts[0] and "Không gửi link" in prompts[0]
    with bot.repo.connect() as conn:  # không lưu nội dung tin (PLAN-077)
        assert conn.execute("SELECT original_url FROM link_requests").fetchone()[0].startswith("[không phải link")


def test_ack_and_link_like_text_keep_template(tmp_path):
    bot, prompts = _bot(tmp_path)
    assert bot.handle_text(BUYER, "u", "cảm ơn", update_id=1, now=NOW).text == CHAT_TEXT
    assert bot.handle_text(BUYER, "u", "lazada.vn/abc", update_id=2, now=NOW).text != chat_ai.WORKING
    assert prompts == []


def test_ai_failure_or_skip_falls_back_to_template(tmp_path):
    bot, _ = _bot(tmp_path, answer="SKIP")
    bot.handle_text(BUYER, "u", "mua bán acc game không", update_id=1, now=NOW)
    assert _queued(bot) == [CHAT_TEXT]

    (tmp_path / "b").mkdir()
    broken, _ = _bot(tmp_path / "b")
    broken.chat_generate = lambda p: (_ for _ in ()).throw(RuntimeError("9router down"))
    broken.handle_text(BUYER, "u", "hoàn tiền bao lâu thì về", update_id=1, now=NOW)
    assert _queued(broken) == [CHAT_TEXT]


def test_cooldown_and_off_switch(tmp_path):
    bot, prompts = _bot(tmp_path)
    bot.handle_text(BUYER, "u", "hoàn tiền bao lâu thì về", update_id=1, now=NOW)
    assert bot.handle_text(BUYER, "u", "sao lâu vậy bạn", update_id=2, now=NOW + timedelta(seconds=10)).text == CHAT_TEXT
    bot.handle_text(BUYER, "u", "sao lâu vậy bạn", update_id=3, now=NOW + timedelta(seconds=60))
    assert len(prompts) == 2
    bot.repo.set_state(chat_ai.OFF_KEY, "1")
    assert bot.handle_text(BUYER, "u", "còn ai không", update_id=4, now=NOW + timedelta(minutes=5)).text == CHAT_TEXT


def test_answer_strips_links_and_html():
    out = chat_ai.answer("hi", False, generate=lambda p: ("Xem <b>tại</b> https://evil.example nha & dán link", {}))
    assert out == "Xem tại nha &amp; dán link"
    assert "CHƯA mở rút tiền" in chat_ai.build_prompt("x", wallet_open=False)


def test_off_by_default_in_service(tmp_path):
    """Service dựng trong test / script: không bật AI → câu mẫu, không gọi 9Router."""
    bot = service(tmp_path, FakeClient(payload()))
    assert bot.handle_text(BUYER, "u", "bot này có thu phí không", update_id=1, now=NOW).text == CHAT_TEXT
