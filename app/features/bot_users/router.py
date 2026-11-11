"""API trang «Khách các bot» (PLAN-168). Chỉ đọc DB của Cashbot + AI Pass Store qua ``cashback_bot.all_users``."""

from datetime import datetime

from fastapi import APIRouter

from cashback_bot import all_users

router = APIRouter(prefix="/bot-users/api", tags=["bot-users"])

LIST_LIMIT = 300


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


@router.get("/report")
def report_api(q: str = "", bot: str = ""):
    rep = all_users.report()
    people = all_users.search(rep.people, q, bot if bot in all_users.BOTS else "")

    def summary(s: all_users.BotSummary) -> dict:
        return {"bot": s.bot, "label": s.label, "total": s.total, "new_24h": s.new_24h, "new_7d": s.new_7d,
                "active_7d": s.active_7d, "buyers": s.buyers}

    return {
        "generated_at": _iso(rep.now),
        "active_days": all_users.ACTIVE_DAYS,
        "bots": [summary(s) for s in rep.bots],
        "total": summary(rep.total),
        "days": [{"day": day, **counts} for day, counts in rep.days],
        "sources": {bot: [{"source": code, "count": n} for code, n in rows] for bot, rows in rep.sources.items()},
        "matched": len(people),
        "people": [
            {"bot": p.bot, "user_id": p.user_id, "name": p.name, "joined_at": _iso(p.joined_at),
             "last_seen_at": _iso(p.last_seen_at), "last_used_at": _iso(p.last_used_at), "source": p.source,
             "uses": p.uses, "orders": p.orders, "active": p.active(rep.now), "balance": p.balance, "spent": p.spent}
            for p in people[:LIST_LIMIT]
        ],
        "errors": rep.errors,
    }
