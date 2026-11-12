"""PLAN-170: kho tâm lý khách — đọc kho, tìm mục, khối gợi ý cho prompt Threads, lệnh admin /tamly."""

from __future__ import annotations

import asyncio

import pytest

from app.features.psych_kb import prompting, search
from app.features.psych_kb.store import BASE_DIR, KnowledgeBase, parse
from cashback_bot.admin.handlers import tamly
from cashback_bot.messages import ADMIN_COMMANDS
from tests.test_cashback_bot import NOW, FakeClient, payload, service

ADMIN = 7001


@pytest.fixture
def kb(tmp_path):
    return KnowledgeBase(BASE_DIR, tmp_path / "override")


def test_kho_goc_doc_du_moi_muc_co_dau_hieu_va_nen(kb):
    entries = kb.entries()
    assert len(entries) >= 35 and len(kb.topics()) >= 8
    assert all(e.signs and e.do and e.avoid and e.source for e in entries)
    assert len({e.id for e in entries}) == len(entries)
    assert [e.id for e in entries if e.always] == ["ranh-gioi-dao-duc/luon"]


@pytest.mark.parametrize("query, expected", [
    ("sợ ấn vào link lạ lắm", "niem-tin/so-link-la"),
    ("Tui Hối hận vì hqua k mua mà đi đợi sale 🤦", "cam-xuc-mua-sam/hoi-han-khong-mua"),
    ("có lừa đảo ko b", "niem-tin/so-lua-dao"),
    ("mình muốn dùng thử xong mới chuyển khoản =)))", "chan-chu/muon-thu-truoc"),
    ("hoàn có mấy nghìn bõ công", "gia-va-gia-tri/hoan-it"),
    ("Đang dùng tiemhoanxu.com thấy %hoàn cũng cao, muốn xem có con nào khác ok hơn ko", "gia-va-gia-tri/so-sanh-noi-khac"),
    ("bot này vô dụng spam hoài", "phan-khang-ap-luc/nguoi-che"),
])
def test_tim_dung_muc_cho_cau_cua_khach(kb, query, expected):
    hits = search.search(query, k=3, kb=kb)
    assert hits and hits[0].entry.id == expected


@pytest.mark.parametrize("query", ["mình cảm ơn ạ", "hôm nay trời đẹp quá đi chơi thôi", ""])
def test_cau_khong_lien_quan_khong_ra_muc_nao(kb, query):
    assert search.search(query, kb=kb) == []
    assert not prompting.guidance_block(query, kb=kb)


def test_bo_dau_va_cap_am_tiet():
    assert search.fold("Sợ ấn link lạ, Đừng") == "so an link la, dung"
    assert "link_la" in search.tokens("sợ ấn link lạ")


def test_khoi_goi_y_gon_co_ranh_gioi_khong_co_cau_vi_du(kb):
    g = prompting.guidance_block("sợ ấn vào link lạ, sợ lừa đảo", "threads", k=2, kb=kb)
    assert g.ids[0] == "niem-tin/so-link-la" and len(g.text) <= prompting.BLOCK_LIMIT
    assert "Luôn:" in g.text and "Bịa số liệu" in g.text
    assert "cẩn thận vậy là đúng á b" not in g.text  # câu Ví dụ không vào reply công khai (AI sẽ chép y nguyên)


def test_loc_theo_kenh(kb):
    ids = {h.entry.id for h in search.search("khách vào bot rồi nhưng chưa tạo link, chưa nạp", k=5, use_for="threads", kb=kb)}
    assert "chan-chu/quen-sau-khi-vao" not in ids  # mục chỉ dành cho tin trong bot
    ids = {h.entry.id for h in search.search("khách vào bot rồi nhưng chưa tạo link, chưa nạp", k=5, use_for="bot", kb=kb)}
    assert "chan-chu/quen-sau-khi-vao" in ids


def test_ban_sua_cua_chu_bot_de_ban_goc_va_nap_lai(tmp_path):
    base, over = tmp_path / "base", tmp_path / "over"
    base.mkdir()
    over.mkdir()
    (base / "a.md").write_text("# A\n\n## x — Gốc\nDấu hiệu: hỏi giá\nNên: trả lời\nTránh: né\nNguồn: t\n", encoding="utf-8")
    (base / "_nguon.md").write_text("## y — Không nạp\nDấu hiệu: z\n", encoding="utf-8")
    kb = KnowledgeBase(base, over)
    assert [e.title for e in kb.entries()] == ["Gốc"]
    (over / "a.md").write_text("# A\n\n## x — Đã sửa\nDấu hiệu: hỏi giá\nNên: trả lời\nTránh: né\nNguồn: t\n",
                               encoding="utf-8")
    assert [e.title for e in kb.entries()] == ["Đã sửa"]


def test_doc_truong_nhieu_dong_va_mac_dinh_kenh():
    (e,) = parse("# T\n\n## m — Mục\nDấu hiệu: a\n  nối tiếp\nNên: b\n", "f")
    assert e.signs == "a nối tiếp" and e.use_for == ("threads", "bot") and e.topic == "T"


# ── gắn vào Threads ────────────────────────────────────────────


def test_followup_prompt_co_khoi_kho_khi_khop(monkeypatch):
    from app.features.threads.growth import content
    from app.features.threads.growth.config import TargetBot

    seen = []

    async def fake_ai(prompt, min_len=20):
        seen.append(prompt)
        return "cẩn thận vậy là đúng á b"

    monkeypatch.setattr(content, "_ai", fake_ai)
    asyncio.run(content.write_followup(TargetBot.CASHBOT, "t dán link qua bot", "sợ ấn vào link lạ lắm"))
    asyncio.run(content.write_followup(TargetBot.CASHBOT, "t dán link qua bot", "mình cảm ơn ạ"))
    assert "Gợi ý tâm lý" in seen[0] and "Sợ bấm link lạ" in seen[0]
    assert "Gợi ý tâm lý" not in seen[1]


def test_generate_reply_ghi_muc_kho_vao_phan_tich(monkeypatch):
    from app.features.threads.growth import evaluator
    from app.features.threads.growth.config import ABVariant, TargetBot

    prompts = []

    async def gen(prompt, *, purpose="generic"):
        prompts.append(prompt)
        return "canh sale mà hết mã cay thật, t hay dán link qua bot", {"provider": "fake", "model": "m"}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", staticmethod(gen))
    monkeypatch.setattr(evaluator, "real_example", lambda: "")
    _, analysis = asyncio.run(evaluator.GrowthEvaluator.generate_reply(
        "canh sale 12.12 mà toàn hết mã, sợ lỡ flash sale", TargetBot.CASHBOT, ABVariant.VARIANT_A, channel="telegram"))
    assert "kb: cam-xuc-mua-sam/fomo-sale" in analysis and "Gợi ý tâm lý" in prompts[0]
    _, plain = asyncio.run(evaluator.GrowthEvaluator.generate_reply(
        "hôm nay trời đẹp quá", TargetBot.CASHBOT, ABVariant.VARIANT_A, channel="telegram"))
    assert "kb:" not in plain and "Gợi ý tâm lý" not in prompts[1]


# ── /tamly ─────────────────────────────────────────────────────


def _bot(tmp_path, answer="Khách đang lo bị lừa.\nDựa vào: niem-tin/so-link-la"):
    bot = service(tmp_path, FakeClient(payload()), admin_user_ids=frozenset({ADMIN}),
                  allowed_telegram_ids=frozenset({ADMIN}))
    bot.tiktok_runner = lambda job: job()
    bot.tamly_generate = lambda prompt: (answer, {"provider": "fake"})
    bot.handle_text(ADMIN, "admin", "/start", update_id=1, now=NOW)
    return bot


def _queued(bot):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT message_html, audience, category FROM admin_notifications "
                            "WHERE event_type = 'TAMLY_ANSWER' AND chat_id = ?", (ADMIN,)).fetchall()


def test_tamly_khong_cau_hoi_liet_ke_chu_de(tmp_path):
    reply = _bot(tmp_path).handle_text(ADMIN, "admin", "/tamly", update_id=2, now=NOW)
    assert "Kho tâm lý khách" in reply.text and "Niềm tin" in reply.text
    assert "tamly" in [name for name, _ in ADMIN_COMMANDS]


def test_tamly_tra_loi_qua_hang_doi_kem_muc_kho(tmp_path):
    bot = _bot(tmp_path, answer="Khách sợ <link> lạ **nên** né.\nDựa vào: niem-tin/so-link-la")
    first = bot.handle_text(ADMIN, "admin", "/tamly khách sợ bấm link lạ thì nói sao", update_id=2, now=NOW)
    assert first.text == tamly.WORKING
    (row,) = _queued(bot)
    assert row["audience"] == "customer" and row["category"] == "tamly"
    assert "&lt;link&gt;" in row["message_html"] and "**" not in row["message_html"]
    assert "Mục kho: niem-tin/so-link-la" in row["message_html"]


def test_tamly_ai_loi_bao_ro(tmp_path):
    bot = _bot(tmp_path, answer=None)
    bot.handle_text(ADMIN, "admin", "/tamly khách sợ link lạ", update_id=2, now=NOW)
    (row,) = _queued(bot)
    assert row["message_html"] == tamly.AI_DOWN


def test_tamly_chi_admin(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(4242, "khach", "/tamly khách sợ link lạ", update_id=3, now=NOW)
    assert _queued(bot) == []


def test_prompt_co_van_dung_kho_va_cam_bia():
    ctx = prompting.advisor_context("khách sợ bấm link lạ")
    prompt = tamly.build_prompt("khách sợ bấm link lạ", ctx.text)
    assert "[niem-tin/so-link-la]" in prompt and "Không bịa số liệu" in prompt and "Dựa vào:" in prompt
