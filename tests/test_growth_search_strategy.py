from dataclasses import replace

from app.features.threads.growth.config import ABVariant, BotGrowthProfile, TargetBot, VariantConfig
from app.features.threads.growth.search_strategy import HELP_QUERIES, plan_searches


def profile(bot, keywords):
    return BotGrowthProfile(bot, "test", "@test", "https://t.me/test", keywords, {
        ABVariant.VARIANT_A: VariantConfig(ABVariant.VARIANT_A, "test", "https://t.me/test", "test", "", ""),
    })


def test_store_buyer_help_mix_rotates_and_never_expands_budget():
    p = {TargetBot.AI_STORE: profile(TargetBot.AI_STORE, [
        "mua capcut pro", "capcut pro giá rẻ", "tài khoản capcut pro", "mua capcut tháng", "mua capcut 30 ngày",
    ])}
    first = plan_searches(p, {"ai_store"})
    second = plan_searches(p, {"ai_store"}, turn=1)
    assert len(first) == 6 and len(second) == 6 and first != second
    assert sum(query in HELP_QUERIES for _, query, _ in first) == 2
    assert all(not top for _, _, top in first)
    assert len(plan_searches(p, {"ai_store"}, cap=3)) <= 3
    assert len(plan_searches(p, {"ai_store"}, cap=0)) <= 6
    assert plan_searches(p, {"cashbot"}) == []


def test_custom_keywords_and_account_allowlist_remain():
    profiles = {b: profile(b, [f"custom{i}" for i in range(12)]) for b in TargetBot}
    for bot in TargetBot:
        jobs = plan_searches(profiles, {bot.value}, cap=5)
        assert len(jobs) == 5 and all(j[0] == bot and j[1].startswith("custom") for j in jobs)
        assert all(not j[2] for j in jobs)
    small = {TargetBot.CASHBOT: replace(profiles[TargetBot.CASHBOT], keywords=["custom"])}
    assert plan_searches(small, {"cashbot"}) == [
        (TargetBot.CASHBOT, "custom", False), (TargetBot.CASHBOT, "custom", True),
    ]
    assert len(plan_searches(small, {"cashbot"}, search_top=False)) == 1


def test_empty_keywords_never_open_search():
    assert plan_searches({TargetBot.AI_STORE: profile(TargetBot.AI_STORE, [])}, {"ai_store"}) == []


def test_mixed_role_never_starves_second_bot():
    profiles = {b: profile(b, [f"custom{i}" for i in range(8)]) for b in TargetBot}
    for turn in range(3):
        jobs = plan_searches(profiles, {"cashbot", "ai_store"}, turn=turn)
        assert len(jobs) == 6
        assert {bot: sum(j[0] == bot for j in jobs) for bot in TargetBot} == {
            TargetBot.CASHBOT: 3, TargetBot.AI_STORE: 3,
        }
    # Even a one-query budget rotates role priority rather than permanently starving one.
    assert {plan_searches(profiles, None, turn=t, cap=1)[0][0] for t in range(2)} == set(TargetBot)


def test_shopper_need_queries_precede_broad_sale_queries():
    p = {TargetBot.CASHBOT: profile(TargetBot.CASHBOT, [
        "sắm tết shopee", "quà tết shopee", "xin mã freeship", "tiết kiệm tiền shopee",
    ])}
    jobs = plan_searches(p, {"cashbot"}, cap=2, search_top=False)
    assert [query for _, query, _ in jobs] == ["xin mã freeship", "tiết kiệm tiền shopee"]
