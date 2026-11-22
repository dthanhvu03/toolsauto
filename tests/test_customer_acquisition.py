"""PLAN-178: pure buyer boundaries and mocked truthful seller/helper prompts."""

import asyncio
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from app.features.threads.growth import acquisition, content, evaluator
from app.features.threads.growth.acquisition import (
    OpportunityDecision,
    is_seller_offer,
    qualify_opportunity,
    qualify_reply,
)
from app.features.threads.growth.config import ABVariant, TargetBot
from app.features.threads.growth.config import GrowthLimits
from app.features.threads.growth.runner import GrowthRunner
from app.features.threads.growth.scanner import ScannedPost
from app.features.threads.growth.storage import GrowthStorage


@pytest.mark.parametrize("text", [
    "Mình muốn mua CapCut Pro ạaaaaa",
    "Minh muon mua capcut pro 30 ngay, ai ban inbox minh nhe",
    "Có ai bán CapCut Pro uy tín không ạ?",
    "Bạn nào bán CapCut Pro chính sách rõ ràng không ạ?",
    "ai ban cap cut pro uy tin inbox em",
    "Cho mình xin link mua CapCut Pro",
    "Cần tài khoản Capcut để xuất video",
    "Can capcut pro de xuat video",
    "CapCut Pro mua ở đâu vậy?",
    "CapCut Pro giá bao nhiêu?",
    "Cho hỏi CapCut Pro còn hàng không ạ?",
    "Capcut Pro của mình hết hạn rồi, cần mua gói mới",
    "Mình đang dùng CapCut bản free, muốn mua Pro",
    "Mình đang dùng bản miễn phí, muốn mua CapCut Pro 30 ngày",
    "Cần mua CapCut Pro, trả phí cũng được, không cần miễn phí",
])
def test_explicit_compatible_capcut_buyer(text):
    assert qualify_opportunity(text, TargetBot.AI_STORE) == OpportunityDecision(True, "qualified_capcut_need")


@pytest.mark.parametrize(("text", "reason"), [
    ("", "empty_content"),
    ("Cần mua ChatGPT Plus", "no_matching_product"),
    ("Xin tóm tắt token skill MCP của Claude AI", "no_matching_product"),
    ("Công cụ AI nào làm video miễn phí?", "no_matching_product"),
    ("Tuyển dụng editor biết CapCut", "recruitment_or_job"),
    ("Tìm việc remote, biết capcut cơ bản", "recruitment_or_job"),
    ("Capcut: thực tập sinh marketing, gửi CV", "recruitment_or_job"),
    ("Capcut pro có sẵn, giá chỉ 34k, ib shop", "seller_or_promotion"),
    ("Ban capcut pro 30 ngay inbox", "seller_or_promotion"),
    ("Bên mình bán CapCut Pro", "seller_or_promotion"),
    ("Xin CapCut Pro miễn phí", "free_only"),
    ("Cần CapCut Pro crack free", "free_only"),
    ("Mình đã có Capcut Pro, vẫn chưa dùng hết", "already_has_access"),
    ("Đang dùng Capcut Pro ngon", "already_has_access"),
    ("Capcut Pro đã mua rồi nhưng lỗi acc, hoàn trả giúp", "support_or_dispute"),
    ("Đã chuyển khoản mua Capcut mà chưa nhận acc", "support_or_dispute"),
    ("CapCut Pro refund giúp mình", "support_or_dispute"),
    ("Cần mua Capcut Pro vĩnh viễn", "offer_mismatch"),
    ("Cần mua CapCut Pro 6 tháng", "offer_mismatch"),
    ("Muốn nâng cấp CapCut tài khoản cá nhân chính chủ", "offer_mismatch"),
    ("Cần mua Capcut Pro dùng 3 thiết bị", "offer_mismatch"),
    ("Mình không muốn mua CapCut Pro", "purchase_refusal"),
    ("Khong can mua capcut pro", "purchase_refusal"),
    ("Đừng mua CapCut Pro nhé", "purchase_refusal"),
    ("Mẫu Capcut này đẹp quá", "no_purchase_need"),
    ("Mình muốn video Capcut lên xu hướng", "no_purchase_need"),
    ("CapCut không đủ dài để ghép doll", "no_purchase_need"),
    ("Bí kíp nào edit Capcut đẹp hơn?", "no_purchase_need"),
])
def test_ai_mentions_and_incompatible_contexts_are_not_buyers(text, reason):
    assert qualify_opportunity(text, "ai_store") == OpportunityDecision(False, reason)


@pytest.mark.parametrize("text", [
    "Ai có mã freeship Shopee không?",
    "Can ma giam gia shopee, inbox minh nhe",
    "Mình muốn mua áo trên Shopee, có cách nào tiết kiệm hơn?",
    "Mua Shopee làm sao được hoàn tiền vậy?",
    "Xin voucher TikTok Shop",
    "Cần mua giày trên TikTok, có cách nào hoàn tiền?",
    "Shopee áp mã thế nào?",
    "Sắp đặt đơn Shopee, tìm bot cashback",
])
def test_supported_cashbot_shopper_needs(text):
    assert qualify_opportunity(text, TargetBot.CASHBOT) == OpportunityDecision(True, "qualified_shopping_need")


@pytest.mark.parametrize(("text", "reason"), [
    ("Cần mã giảm giá Lazada", "no_matching_platform"),
    ("Mình muốn mua Capcut Pro", "no_matching_platform"),
    ("Bán giày Shopee, link bio, mua ngay", "seller_or_promotion"),
    ("Shopee tuyển dụng CTV marketing", "recruitment_or_job"),
    ("Shopee tự dưng refund 300k", "support_or_dispute"),
    ("Shopee đã giao nhưng chưa nhận được hàng", "support_or_dispute"),
    ("Cần trả hàng Shopee", "support_or_dispute"),
    ("Shopee nay có giao diện mới", "no_shopping_need"),
    ("Mình không mua Shopee nữa", "purchase_refusal"),
    ("Khong muon mua Shopee nua", "purchase_refusal"),
])
def test_cashbot_does_not_pitch_to_sellers_jobs_and_support(text, reason):
    assert qualify_opportunity(text, "cashbot") == OpportunityDecision(False, reason)


@pytest.mark.parametrize("text", [
    "Có ai bán Capcut Pro thì inbox mình nhé",
    "Can mua capcut pro ai co ib em",
    "Ai có mã freeship Shopee không?",
])
def test_inbox_and_freeship_are_not_supply_side_evidence(text):
    assert not is_seller_offer(text)
    assert not evaluator.GrowthEvaluator.looks_like_seller(text)


def test_gate_is_pure_and_decision_is_immutable(monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("Pure opportunity gate must not call a model")

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", unexpected)
    result = qualify_opportunity("Cần mua Capcut Pro", "ai_store")
    assert result.eligible
    assert qualify_opportunity("Cần mua Capcut Pro", "unknown").reason == "unknown_target"
    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"
    assert acquisition.OpportunityDecision is OpportunityDecision


@pytest.mark.parametrize(("reply", "reason"), [
    ("", "empty_reply"),
    ("Bạn thử gói ChatGPT Plus bên shop nhé", "cross_product_reply"),
    ("Bên mình còn Canva Pro giá rẻ", "cross_product_reply"),
    ("Mình đã dùng CapCut ở đây rồi, uy tín lắm", "personal_testimonial"),
    ("T hay mua Capcut bên này", "personal_testimonial"),
    ("Mình test rồi bạn nhé", "personal_testimonial"),
    ("CapCut Pro bảo hành 1 đổi 1", "unsupported_claim"),
    ("CapCut Pro còn hàng giao ngay", "unsupported_claim"),
    ("CapCut giảm 50%", "unsupported_claim"),
    ("CapCut Pro cam kết rẻ nhất", "unsupported_claim"),
    ("Shop có CapCut Pro 34.000đ", "ungrounded_price_claim"),
    ("Capcut pro 34k cho 30 ngày", "ungrounded_price_claim"),
    ("CapCut Pro 34 nghìn nhé", "ungrounded_price_claim"),
    ("CapCut Pro gia 34000", "ungrounded_price_claim"),
])
def test_old_reply_copy_must_match_offer_and_evidence(reply, reason):
    assert qualify_reply("Mình muốn mua CapCut Pro", "ai_store", reply) == OpportunityDecision(False, reason)


def test_honest_offer_faq_with_current_price_pointer_passes():
    reply = "Shop có CapCut Pro 30 ngày, tài khoản cấp sẵn; bạn xem mô tả và giá hiện tại trong bot: https://t.me/aipass_shop_bot?start=threads_ai_auto"
    assert qualify_reply("Cần mua Capcut Pro", TargetBot.AI_STORE, reply) == OpportunityDecision(True, "qualified_reply")
    assert qualify_reply("Cần mua Capcut Pro", "ai_store", "Shop có CapCut Pro 30D, xem giá hiện tại trong bot").eligible


def test_copy_cannot_rescue_unqualified_original_post():
    assert qualify_reply("Tuyển dụng biết Capcut", "ai_store", "Xem Capcut trong bot").reason == "recruitment_or_job"


def test_cashbot_system_estimate_does_not_become_personal_testimony():
    original = "Mình sắp mua áo trên Shopee, có cách nào tiết kiệm?"
    honest = "Ví dụ hệ thống: áo giá 179k, bot báo hoàn khoảng 15k; số hoàn chỉ là dự kiến."
    assert qualify_reply(original, "cashbot", honest).eligible
    assert qualify_reply(original, "cashbot", "Mình đã nhận hoàn 15k rồi").reason == "personal_testimonial"
    assert qualify_reply(original, "cashbot", "Bạn dán link để xem mã giảm giá và số hoàn dự kiến trong bot nhé").eligible
    assert qualify_reply(original, "cashbot", "Số hoàn là dự kiến, không cam kết chắc chắn; xem điều kiện trong bot").eligible
    assert qualify_reply(original, "cashbot", "Cam kết hoàn tiền 100% nhé").reason == "unsupported_claim"


@pytest.fixture
def prompt_context(monkeypatch):
    cfg = SimpleNamespace(name="CapCut 30 ngày", angle="Tài khoản cấp sẵn, xem giá hiện tại trong bot",
                          tracking_url="https://t.me/aipass_shop_bot?start=threads_ai_auto")
    profile = SimpleNamespace(name="CapCut Pro 30D", handle="@aipass_shop_bot", variants={ABVariant.VARIANT_A: cfg})
    monkeypatch.setattr(evaluator, "load_profiles", lambda: {TargetBot.AI_STORE: profile})
    monkeypatch.setattr(content, "load_profiles", lambda: {TargetBot.AI_STORE: profile})
    monkeypatch.setattr(evaluator, "guidance_block", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(content, "guidance_block", lambda *_args, **_kwargs: None)
    return profile


@pytest.mark.parametrize("include_link", [True, False])
def test_reply_and_editor_prompts_require_truthful_shop_voice(monkeypatch, prompt_context, include_link):
    prompts = []

    async def generate(prompt, **_kwargs):
        prompts.append(prompt)
        return ("KEEP" if prompt.startswith("KIỂM TRA REPLY") else "Bạn có thể xem thông tin trong bot nhé"), {}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", generate)
    asyncio.run(evaluator.GrowthEvaluator.generate_reply(
        "Cần mua CapCut Pro", TargetBot.AI_STORE, ABVariant.VARIANT_A,
        include_link=include_link,
    ))
    assert len(prompts) == 2
    assert "trợ lý của shop" in prompts[0]
    assert "KHÔNG bịa đã mua" in prompts[0]
    assert "trợ lý của shop" in prompts[1]
    assert "Không bịa thói quen cá nhân" in prompts[1]
    assert "KHÔNG lộ là AI" not in "\n".join(prompts)
    assert "như kinh nghiệm cá nhân" not in prompts[0]


def test_followup_prompt_does_not_invent_customer_experience(monkeypatch, prompt_context):
    prompts = []

    async def fake_ai(prompt, min_len=20):
        prompts.append(prompt)
        return "Bạn xem giá hiện tại và mô tả trong bot nhé"

    monkeypatch.setattr(content, "_ai", fake_ai)
    verdict, _reply = asyncio.run(content.write_followup(TargetBot.AI_STORE, "Shop có Capcut", "Giá xem ở đâu?"))
    assert verdict == "answer"
    assert "trợ lý của shop/bot" in prompts[0]
    assert "Không bịa đã mua, đã dùng, đã test" in prompts[0]
    assert "không lồng bán món khác" in prompts[0]
    assert "nói thật là trợ lý tự động" in prompts[0]
    assert "Cách mua: chọn món" in prompts[0]
    assert "Hỏi cách dùng thì nhắc: dán link món" not in prompts[0]
    assert "Tiền hoàn là ước tính, được ghi vào ví" not in prompts[0]


def test_own_post_style_is_not_a_fabricated_customer():
    assert "không giả làm khách hàng" in content._STYLE
    assert "không bịa đã mua/dùng/test/nhận hoàn" in content._STYLE


def test_stale_configured_fallback_is_replaced_with_neutral_offer(prompt_context):
    variant = prompt_context.variants[ABVariant.VARIANT_A]
    variant.sample_hook = "t lấy CapCut Pro 30 ngày bên @aipass_shop_bot ~34k, mềm hơn tự cà thẻ ngoại"
    fallback = evaluator.GrowthEvaluator.get_fallback_reply(TargetBot.AI_STORE, ABVariant.VARIANT_A)
    assert variant.tracking_url in fallback
    assert "giá hiện tại trong bot" in fallback
    assert "34k" not in fallback and "t lấy" not in fallback


@pytest.mark.parametrize("text", [
    "CapCut báo cần Pro để xuất video thì làm sao biết hiệu ứng nào gây ra?",
    "Capcut khong xuat video duoc, ai biet cach nao khong?",
    "Đang dùng CapCut Pro, sao phụ đề không hiện?",
    "Làm sao tìm tài nguyên Pro trong CapCut khi xuất clip bị lỗi?",
    "CapCut không hiện font tiếng Việt, giúp mình với?",
    "CapCut export bị lỗi thì cần kiểm tra thông tin gì?",
    "CapCut báo phải nâng cấp để xuất video, làm sao biết tài nguyên nào đang dùng Pro?",
    "CapCut không xuất được video, giúp mình với?",
    "CapCut không lưu được video, giúp mình với?",
    "CapCut báo Pro khi xuất, ai biết vì sao không?",
    "CapCut template yêu cầu Pro, tại sao vậy?",
    "CapCut không xuất được video, làm sao kiểm tra?",
])
def test_specific_capcut_question_uses_help_lane(text):
    decision = qualify_opportunity(text, "ai_store")
    assert decision == OpportunityDecision(True, "qualified_capcut_help", "help_first")


@pytest.mark.parametrize("text", [
    "CapCut xuất video lên xu hướng thế nào?",
    "Làm sao edit CapCut đẹp hơn?",
    "CapCut có hiệu ứng nào viral không?",
    "Xin CapCut miễn phí để xuất video?",
    "CapCut mod bị lỗi xuất video, giúp mình?",
    "Không muốn dùng CapCut nữa vì không xuất video được",
    "Đã chuyển khoản mua CapCut nhưng xuất video bị lỗi?",
    "Tuyển editor biết CapCut xuất video, phụ đề, font",
])
def test_help_lane_does_not_bypass_existing_boundaries(text):
    assert not qualify_opportunity(text, "ai_store").eligible


@pytest.mark.parametrize(("reply", "reason"), [
    ("Bạn xem gói ở https://t.me/aipass_shop_bot", "help_link_not_allowed"),
    ("Bạn thử ở evil.example/path nhé", "help_link_not_allowed"),
    ("Bạn mở www.example.com nhé", "help_link_not_allowed"),
    ("Bạn mở app://support nhé", "help_link_not_allowed"),
    ("Bạn vào shop xem gói CapCut nha", "help_offer_not_allowed"),
    ("Bạn mua Pro sẽ được nhé", "help_offer_not_allowed"),
    ("Nâng cấp tài khoản để xuất bạn nhé", "help_offer_not_allowed"),
    ("Nhắn inbox để mình hướng dẫn nha", "help_offer_not_allowed"),
])
def test_help_reply_cannot_turn_into_an_offer(reply, reason):
    decision = qualify_reply("CapCut không xuất video được, ai biết cách nào?", "ai_store", reply)
    assert decision == OpportunityDecision(False, reason, "help_first")


def test_help_reply_keeps_useful_clarification():
    result = qualify_reply(
        "CapCut không xuất video được, ai biết cách nào?", "ai_store",
        "Bạn đang dùng máy tính hay điện thoại, và màn hình đang báo lỗi gì vậy?",
    )
    assert result.eligible and result.lane == "help_first"


@pytest.mark.parametrize("output", [
    "Bạn vào https://t.me/aipass_shop_bot nhé",
    "Bạn mở evil.example/path nhé",
    "Bạn mua gói trong bot nhé",
    "@aipass_shop_bot",
    "Dạ",
    "",
    None,
])
def test_no_link_generation_never_becomes_cta_on_unsafe_or_short_output(monkeypatch, prompt_context, output):
    async def model(prompt, **_kwargs):
        return ("KEEP" if prompt.startswith("KIỂM TRA REPLY") else output), {}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", model)
    text, analysis = asyncio.run(evaluator.GrowthEvaluator.generate_reply(
        "CapCut không xuất video được?", TargetBot.AI_STORE, ABVariant.VARIANT_A, include_link=False,
    ))
    assert text == "" and analysis.startswith("Fallback")


def test_no_link_provider_error_has_no_linked_fallback(monkeypatch, prompt_context):
    async def fail(*_args, **_kwargs):
        raise RuntimeError("test outage")

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", fail)
    text, analysis = asyncio.run(evaluator.GrowthEvaluator.generate_reply(
        "CapCut không xuất video được?", TargetBot.AI_STORE, ABVariant.VARIANT_A, include_link=False,
    ))
    assert text == "" and analysis.startswith("Fallback") and "no_link" in analysis


def test_reading_and_runner_follow_helpfulness_lane_with_useful_reply(monkeypatch, tmp_path, prompt_context):
    prompts = []

    async def model(prompt, **_kwargs):
        prompts.append(prompt)
        if prompt.startswith("PHÂN TÍCH BÀI"):
            return '{"is_seller":false,"intent":"hỏi cách xuất","need":"kiểm tra thông báo lỗi","buy_score":85}', {}
        if prompt.startswith("KIỂM TRA REPLY"):
            return "KEEP", {}
        return "Bạn dùng máy tính hay điện thoại, và thông báo lỗi cụ thể đang hiện gì vậy?", {}

    monkeypatch.setattr(evaluator.AIUseCases, "generate_text_async", model)
    monkeypatch.setattr(evaluator.GrowthEvaluator, "calculate_relevance", lambda *_a: 85)
    storage = GrowthStorage(tmp_path / "test.sqlite")
    runner = GrowthRunner(storage, limits=lambda: GrowthLimits(min_relevance=40))
    post_id = asyncio.run(runner.ingest_scanned_post(
        ScannedPost("help1", "https://threads.com/@sample/post/help1", "sample",
                    "CapCut báo cần Pro để xuất video thì làm sao?", ""),
        forced_bot=TargetBot.AI_STORE, forced_variant=ABVariant.VARIANT_A, auto_post_min=70,
    ))
    post = storage.get_post_by_id(post_id)
    assert post["status"] == "approved"
    assert "lane:help_first" in post["ai_analysis"] and "no_link" in post["ai_analysis"]
    assert "http" not in post["suggested_reply"] and "bot" not in post["suggested_reply"]
    assert "HELP_FIRST" in prompts[0] and "KHÔNG phải ý định mua" in prompts[0]
    assert "KHÔNG GẮN LINK" in prompts[1]


def test_store_buyer_lane_does_not_randomly_drop_cta(monkeypatch, tmp_path, prompt_context):
    include_link = []

    async def read(*_args):
        return SimpleNamespace(buy_score=90, is_seller=False, summary=lambda: "buyer"), ""

    async def generate(*_args, **kwargs):
        include_link.append(kwargs["include_link"])
        return "Shop có gói CapCut Pro 30 ngày, bạn xem mô tả trong bot nhé", "AI"

    monkeypatch.setattr(evaluator.GrowthEvaluator, "read_post", read)
    monkeypatch.setattr(evaluator.GrowthEvaluator, "generate_reply", generate)
    monkeypatch.setattr(evaluator.GrowthEvaluator, "calculate_relevance", lambda *_a: 90)
    storage = GrowthStorage(tmp_path / "test.sqlite")
    runner = GrowthRunner(storage, limits=lambda: GrowthLimits(min_relevance=40))
    post_id = asyncio.run(runner.ingest_scanned_post(
        ScannedPost("buy1", "https://threads.com/@sample/post/buy1", "sample", "Cần mua CapCut Pro", ""),
        forced_bot=TargetBot.AI_STORE, forced_variant=ABVariant.VARIANT_A, auto_post_min=70,
    ))
    assert include_link == [True] and storage.get_post_by_id(post_id)["status"] == "approved"
