"""Lệnh admin ``/users`` (PLAN-168): tổng khách mọi bot — Cashbot Telegram, Cashbot Zalo, AI Pass Store.

``/users`` → bảng tổng + khách mới 7 ngày + nguồn. ``/users <tên|@username|ID|mã nguồn>`` → tối đa 10 khách khớp
(khách Cashbot có nút mở hồ sơ). Chỉ đọc DB, cùng số với trang web «Khách các bot».
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from cashback_bot import all_users
from cashback_bot.admin.handlers.insights import NAV
from cashback_bot.messages import BotReply, fit_html
from cashback_bot.money import format_vnd

SHORT = {"cashbot_tg": "Cashbot TG", "cashbot_zalo": "Cashbot Zalo", "ai_store": "AI Store"}
MATCH_LIMIT = 10
SHOW_DAYS = 7
SOURCES_PER_BOT = 4


def _when(moment: datetime | None) -> str:
    return moment.astimezone(all_users.ICT).strftime("%d/%m %H:%M") if moment else "—"


def summary_text(rep: all_users.Report) -> str:
    lines = ["👥 <b>Khách các bot</b>", ""]
    for s in [*rep.bots, rep.total]:
        title = "<b>Tổng</b>" if s.bot == "all" else html.escape(s.label)
        lines.append(f"{title}: <b>{s.total}</b> · mới 24h {s.new_24h} · 7 ngày {s.new_7d}\n"
                     f"   đang dùng {s.active_7d} · có đơn {s.buyers}")
    lines += ["", f"📅 <b>Khách mới {SHOW_DAYS} ngày</b> (TG · Zalo · Store)"]
    for day, counts in rep.days[:SHOW_DAYS]:
        lines.append(f"{day}: {counts['cashbot_tg']} · {counts['cashbot_zalo']} · {counts['ai_store']}")
    lines += ["", "📍 <b>Nguồn</b>"]
    for bot in all_users.BOTS:
        rows = rep.sources.get(bot) or []
        shown = ", ".join(f"{html.escape(code)} {n}" for code, n in rows[:SOURCES_PER_BOT]) or "chưa có"
        lines.append(f"{SHORT[bot]}: {shown}")
    lines += ["", f"Đang dùng = {all_users.ACTIVE_DAYS} ngày qua có tạo link (Cashbot) / có đơn hoặc nạp (Store).",
              "Gõ <code>/users tên</code>, <code>/users @username</code> hoặc ID để tìm khách. Xem đủ: web «Khách các bot»."]
    lines += [f"⚠️ {html.escape(e)}" for e in rep.errors]
    return "\n".join(lines)


def _person_line(p: all_users.Person, rep: all_users.Report) -> str:
    dot = "🟢" if p.active(rep.now) else "⚪"
    use = f"{p.orders} đơn · đã chi {format_vnd(p.spent or 0)} · ví {format_vnd(p.balance or 0)}" \
        if p.bot == "ai_store" else f"{p.uses} link · {p.orders} đơn"
    return (f"{dot} <b>{html.escape(p.name)}</b> · {SHORT[p.bot]} · <code>{p.user_id}</code>\n"
            f"   vào {_when(p.joined_at)} · nguồn {html.escape(p.source)} · {use}")


def users_reply(query: str, now: datetime | None = None, cashback_path: str | None = None) -> BotReply:
    rep = all_users.report(now, cashback_path=Path(cashback_path) if cashback_path else None)
    query = " ".join((query or "").split())
    if not query:
        return BotReply(fit_html(summary_text(rep)), inline_keyboard=NAV)
    hits = all_users.search(rep.people, query)
    head = f"🔍 <b>Khách khớp «{html.escape(query)}»</b>: {len(hits)}"
    if not hits:
        return BotReply(f"{head}\n\nKhông thấy. Thử tên khác, @username hoặc ID.", inline_keyboard=NAV)
    shown = hits[:MATCH_LIMIT]
    body = "\n\n".join(_person_line(p, rep) for p in shown)
    more = f"\n\n… còn {len(hits) - len(shown)} khách, gõ cụ thể hơn." if len(hits) > len(shown) else ""
    buttons = tuple(((f"👤 {p.name}"[:40], f"c:in:d:{p.user_id}"),) for p in shown if p.bot != "ai_store")
    return BotReply(fit_html(f"{head}\n\n{body}{more}"), inline_keyboard=(*buttons, *NAV))
