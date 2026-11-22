"""Bounded search missions for PLAN-179; this module does not open a browser."""

from __future__ import annotations

import unicodedata

from app.features.threads.growth.config import BotGrowthProfile, TargetBot

HELP_QUERIES = ("capcut không xuất được video", "capcut báo pro khi xuất", "capcut không lưu được video",
                "capcut template yêu cầu pro")
MAX_SEARCHES = 6


def _rotate(items: list[str], turn: int, take: int) -> list[str]:
    if not items:
        return []
    start = (turn * take) % len(items)
    return (items[start:] + items[:start])[:take]


def _intent_priority(query: str) -> int:
    text = "".join(c for c in unicodedata.normalize("NFKD", query.lower().replace("đ", "d"))
                   if not unicodedata.combining(c))
    return int(any(term in text for term in ("can mua", "mua o dau", "xin ma", "ma giam gia",
                                            "voucher", "freeship", "hoan tien", "tiet kiem", "ap ma")))


def plan_searches(profiles: dict[TargetBot, BotGrowthProfile], bots: set[str] | None,
                  *, turn: int = 0, cap: int = 10, search_top: bool = True) -> list[tuple[TargetBot, str, bool]]:
    """Prefer newest buyer questions and reserve Store slots for concrete help topics.

    A non-positive configured cap means no old cap; the new six-search budget still applies.
    Custom keywords remain eligible. Both accounts keep their own role and rotation.
    """
    budget = min(MAX_SEARCHES, cap) if cap > 0 else MAX_SEARCHES
    jobs = []
    active = [(bot, profile) for bot, profile in profiles.items() if bots is None or bot.value in bots]
    active = [(bot, profile) for bot, profile in active if any(str(k).strip() for k in profile.keywords)]
    if active:
        offset = turn % len(active)
        active = active[offset:] + active[:offset]
    for index, (bot, profile) in enumerate(active):
        keywords = list(dict.fromkeys(str(k).strip() for k in profile.keywords if str(k).strip()))
        keywords.sort(key=_intent_priority, reverse=True)
        if not keywords:
            continue
        available = budget - len(jobs)
        if available <= 0:
            break
        remaining = max(1, available // (len(active) - index))
        capcut = bot == TargetBot.AI_STORE and any("capcut" in k.lower().replace(" ", "") for k in keywords)
        if capcut:
            help_count = min(2, remaining // 3)
            buyer_count = remaining - help_count
            buyer_keywords = [k for k in keywords if not any(word in k.lower() for word in
                              ("watermark", "không xuất", "không lưu", "báo pro", "yêu cầu pro"))] or keywords
            jobs.extend((bot, k, False) for k in _rotate(buyer_keywords, turn, buyer_count))
            jobs.extend((bot, k, False) for k in _rotate(list(HELP_QUERIES), turn, help_count))
        else:
            jobs.extend((bot, k, False) for k in _rotate(keywords, turn, remaining))
            # A short custom list may still use the existing top tab within the same budget.
            if search_top:
                used = remaining - sum(j[0] == bot for j in jobs)
                jobs.extend((bot, k, True) for k in _rotate(keywords, turn, max(0, used)))
    return jobs[:budget]
