"""/admin → 💹 Dòng tiền · 📈 Tăng trưởng · 🛠 Vận hành · 👥 Khách hàng (PLAN-089) · 🎯 Mục tiêu (PLAN-090)
· 🔍 Tìm (PLAN-091).

Số tính ở insights.py. Chỉ đọc DB, trừ hai việc admin nhập (bot_state, ghi 📊 Lịch sử): chi phí vận hành và hạ tầng
mỗi tháng, và mục tiêu tháng.
Callback: c:in:m:<kỳ> · c:in:g:<kỳ> · c:in:o · c:in:u:<sắp xếp|nhóm>:<trang> · c:in:d:<id> · c:in:cost · c:in:b
· c:in:t · c:in:t:<mã mục tiêu> · c:in:f (tìm) · c:in:l:<link_id>
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from cashback_bot import insights
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.money import format_vnd

_MONEY = re.compile(r"^c:in:(m|g):(7d|30d|month|all)$")
_USERS = re.compile(r"^c:in:u:([a-z]{2,10}):(\d{1,3})$")
_DETAIL = re.compile(r"^c:in:d:(-?\d{1,15})$")
_GOAL = re.compile(r"^c:in:t:([a-z]{3,12})$")
_LINK = re.compile(r"^c:in:l:(\d{1,9})$")
_PERCENT = re.compile(r"^\s*(\d{1,3}(?:[.,]\d+)?)\s*%?\s*$")
_COST = re.compile(r"^\s*([\d.,\s]+)\s*(k|nghìn|ngàn|tr|triệu|trieu)?\s*$", re.IGNORECASE)
COST_MAX = 10_000_000_000
COUNT_MAX = 1_000_000
CLEAR_WORDS = ("bỏ", "bo", "xoá", "xóa", "xoa")
COST_WAIT = timedelta(minutes=10)
PAGE = 8
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
HOME = (("◀️ Tổng quan", "c:menu:home"),)
NAV = (
    (("💹 Dòng tiền", "c:in:m:30d"), ("📈 Tăng trưởng", "c:in:g:30d")),
    (("🛠 Vận hành", "c:in:o"), ("👥 Khách hàng", "c:in:u:margin:1")),
    (("🎯 Mục tiêu", "c:in:t"), *HOME),
)
GOAL_BUTTONS = {
    "completed": "⭐ Đơn hoàn thành", "net": "HH ròng", "new": "Khách mới", "active": "Khách hoạt động",
    "activation": "% có đơn 7 ngày", "cancel": "Ngưỡng huỷ",
}
# Chỉ hiện ở màn nhập để admin tham khảo; bot không tự lưu (PLAN-090 mục 1).
GOAL_HINTS = {"completed": "Gợi ý G2: 100 đơn / tháng.", "active": "Gợi ý G2: 50 khách hoạt động."}
GOAL_EXAMPLES = {
    "count": "<code>100</code>",
    "vnd": "<code>5000000</code>, <code>5tr</code> hoặc <code>800k</code>",
    "percent": "<code>30</code> hoặc <code>30%</code>",
}
SEARCH_ICONS = {"link": "🔗", "order": "📦", "ticket": "📩", "payout": "👛", "user": "👤"}
SEARCH_HELP = (
    "Gõ một trong các dạng:\n"
    "• mã link 8 ký tự, ví dụ <code>BiE1mRa5</code> (hoặc dán cả link mua có sub_id)\n"
    "• mã đơn Shopee, ví dụ <code>261023CC4UWJ0N</code>\n"
    "• <code>#12</code>: ticket hỗ trợ\n"
    "• <code>Hoan tien 000012</code>: yêu cầu rút (nội dung chuyển khoản)\n"
    "• ID khách, <code>@username</code>, tên Zalo hoặc tên sản phẩm"
)
SORT_LABELS = {"margin": "Biên", "orders": "Đơn", "wallet": "Ví", "recent": "Gần đây", "new": "Mới vào"}

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def _pct(part: int | float, whole: int | float) -> str:
    return f"{part * 100 / whole:.0f}%" if whole else "–"


def _days(value: float | None, samples: int) -> str:
    return "–" if value is None else f"{value:g} ngày ({samples} mẫu)"


def _when(stamp: str | None) -> str:
    moment = insights.parse_stamp(stamp)
    return "-" if moment is None else moment.astimezone(insights.ICT).strftime("%d/%m %H:%M")


def _title(*path: str) -> str:
    return " › ".join(("⚙️ Quản trị",) + path[:-1]) + f" › <b>{path[-1]}</b>\n\n"


def _periods(prefix: str, current: str) -> tuple[tuple[str, str], ...]:
    return tuple(((f"• {label}" if key == current else label), f"c:in:{prefix}:{key}")
                 for key, label in insights.PERIODS.items())


def parse_cost(text: str) -> int | None:
    """'3000000', '3.000.000', '3tr', '500k' → VND. Sai hoặc quá lớn: None."""
    found = _COST.fullmatch(text or "")
    if not found:
        return None
    raw, unit = found.group(1).replace(" ", ""), (found.group(2) or "").lower()
    if unit:
        number = raw.replace(",", ".")
        try:
            value = float(number)
        except ValueError:
            return None
        amount = int(round(value * (1_000 if unit in ("k", "nghìn", "ngàn") else 1_000_000)))
    else:
        digits = raw.replace(".", "").replace(",", "")
        if not digits.isdigit():
            return None
        amount = int(digits)
    return amount if 0 <= amount <= COST_MAX else None


def parse_goal(unit: str, text: str) -> int | None:
    """Số mục tiêu theo đơn vị. Đếm và tiền phải > 0; phần trăm 0–100. Sai: None."""
    stripped = (text or "").strip()
    if unit == "vnd":
        amount = parse_cost(stripped)
        return amount if amount else None
    if unit == "percent":
        found = _PERCENT.fullmatch(stripped)
        value = float(found.group(1).replace(",", ".")) if found else -1
        return int(round(value)) if 0 <= value <= 100 else None
    digits = stripped.replace(".", "").replace(",", "").replace(" ", "")
    return int(digits) if digits.isdigit() and 0 < int(digits) <= COUNT_MAX else None


def goal_value(unit: str, value: float | None) -> str:
    if value is None:
        return "chưa đủ mẫu"
    if unit == "vnd":
        return format_vnd(int(value))
    if unit == "percent":
        return f"{value:.0f}%"
    return f"{int(value):,}".replace(",", ".")


def goal_history(before: dict, after: dict) -> str:
    """Dòng 📊 Lịch sử cho action `goal`."""
    key = str(after.get("key", ""))
    label, unit, _kind = insights.GOALS.get(key, (html.escape(key), "count", "level"))
    old = "chưa đặt" if before.get("value") is None else goal_value(unit, before["value"])
    new = "bỏ" if after.get("value") is None else goal_value(unit, after["value"])
    return f"Mục tiêu: {label} {old} → {new}"


_STATUS = {"done": "✅ đạt", "on_track": "🟢 kịp", "behind": "🔴 chậm", "nodata": "⚪"}


def _goal_line(r: insights.GoalRow) -> str:
    line = f"{'⭐' if r.key == 'completed' else '•'} {r.label}: <b>{goal_value(r.unit, r.actual)}</b>"
    if r.target is None:
        line += " · chưa đặt"
    else:
        status = "🔴 chưa đạt" if r.status == "behind" and r.kind == "level" else _STATUS[r.status]
        line += f" / {goal_value(r.unit, r.target)} {status}"
    if r.forecast is not None:
        line += f" · dự báo {goal_value(r.unit, r.forecast)}"
    if r.per_day:
        line += f" · cần ~{goal_value(r.unit, r.per_day)}/ngày"
    return line


def brief_text(g: insights.Goals, today: insights.DayStats, top: list[tuple[str, int, int]],
               fresh: list[str], local: datetime) -> str:
    """🌙 Bản tin tối gửi admin (PLAN-092)."""
    lines = [f"🌙 <b>Bản tin tối {local:%d/%m}</b> · tháng {g.month}, ngày {g.day}/{g.days_in_month}", "",
             f"📍 {g.stage}"]
    lines += [f"🎉 Mốc mới: <b>{html.escape(label)}</b>" for label in fresh]
    lines += ["", f"📅 <b>Hôm nay</b>: {today.new} khách mới · {today.links} link · {today.orders} đơn đặt · "
                  f"{today.completed} đơn hoàn thành · HH ròng {format_vnd(today.net)}", "", "🎯 <b>Mục tiêu tháng</b>"]
    chosen = [r for r in g.rows if r.kind != "cap" and r.target is not None]
    lines += [_goal_line(r) for r in chosen] or ["Chưa đặt mục tiêu nào."]
    red = [c.label for c in g.guards if not c.ok]
    if g.row("cancel").status == "behind":
        red.insert(0, "Tỉ lệ huỷ 30 ngày")
    lines += ["", "🛡 An toàn: " + ("🟢 tất cả ổn" if not red else "🔴 " + html.escape(", ".join(red)))]
    if top:
        lines += ["", "👥 <b>Top khách 7 ngày</b> (HH ròng)"]
        lines += [f"{n}. {html.escape(label)} · {orders} đơn · {format_vnd(net)}"
                  for n, (label, orders, net) in enumerate(top, 1)]
    lines += ["", "Xem đủ: /admin → 🎯 Mục tiêu"]
    return "\n".join(lines)


def goals_text(g: insights.Goals) -> str:
    lines = [_title(f"Mục tiêu · tháng {g.month}").rstrip("\n"), ""]
    lines.append(f"📍 Giai đoạn: <b>{g.stage}</b>")
    lines += [f"{'✅' if ok else '⬜'} {label}" for label, ok in g.milestones]
    lines += ["", f"🎯 <b>Tháng này</b> (ngày {g.day}/{g.days_in_month})"]
    for r in g.rows:
        if r.kind == "cap":
            continue
        lines.append(_goal_line(r))
        if r.key == "completed":
            lines.append(f"   đơn đặt trong tháng: {g.placed} (thành hoàn thành sau khi khách nhận hàng)")
        if r.key == "activation":
            lines.append(f"   trên {g.activation_size} khách vào 7–37 ngày trước · {g.activation_waiting} khách chưa đủ 7 ngày")
    cancel = g.row("cancel")
    icon = {"unset": "⚪", "done": "🟢", "behind": "🔴"}[cancel.status]
    limit = "chưa đặt ngưỡng" if cancel.target is None else f"tối đa {cancel.target}%"
    lines += ["", "🛡 <b>Giới hạn an toàn</b>", f"{icon} Tỉ lệ huỷ 30 ngày: {cancel.actual:.0f}% ({limit})"]
    lines += [f"{'🟢' if c.ok else '🔴'} {html.escape(c.label)}: {html.escape(c.value)}" for c in g.guards]
    lines += [
        "",
        "ⓘ Bot không tự đặt mục tiêu. Bấm ✍️ để nhập, gõ <code>bỏ</code> để xoá.",
        "ⓘ Đơn hoàn thành đến sau ngày đặt vài tuần, nên dự báo đầu tháng còn thấp.",
    ]
    return "\n".join(lines)


def _search_target(hit: insights.Hit) -> str | None:
    if hit.ref <= 0:
        return None
    return {"link": f"c:in:l:{hit.ref}", "order": f"c:in:l:{hit.ref}", "ticket": f"c:hp:t:{hit.ref}",
            "payout": f"c:wl:rq:{hit.ref}", "user": f"c:in:d:{hit.ref}"}[hit.kind]


def search_text(query: str, hits: list[insights.Hit]) -> str:
    lines = [_title("🔍 Tìm").rstrip("\n") + f": <code>{html.escape(query[:60])}</code>", ""]
    if not hits:
        return "\n".join(lines + ["Không thấy kết quả nào.", "", SEARCH_HELP])
    lines.append(f"{len(hits)} kết quả" + (f" (hiện tối đa {insights.SEARCH_LIMIT})" if len(hits) >= insights.SEARCH_LIMIT else "") + ":")
    lines += [f"{SEARCH_ICONS[h.kind]} {html.escape(h.title)}" + ("" if _search_target(h) else " · không có màn chi tiết")
              for h in hits]
    return "\n".join(lines)


_DELIVERY = {"sent": "✅ đã giao tới khách", "pending": "⏳ chưa giao", "retry": "⏳ đang gửi lại",
             "failed": "🔴 gửi lỗi", "needs_review": "🟠 cần kiểm tra"}


def link_text(d: insights.LinkDetail) -> str:
    lines = [_title("🔍 Tìm", f"Link {html.escape(d.sub_id or str(d.link_id))}").rstrip("\n"), ""]
    lines.append(f"👤 {html.escape(d.user)} · ID <code>{d.user_id}</code>")
    product = html.escape((d.product or "-")[:80])
    price = "" if d.price is None else f" · {format_vnd(int(d.price))}"
    estimate = "" if not d.cashback_estimate else f" · hoàn dự kiến {format_vnd(int(d.cashback_estimate))}"
    lines.append(f"🛍️ {product}{price}{estimate}")
    state = _DELIVERY.get(d.delivery_status or "", html.escape(d.delivery_status or "-"))
    if d.link_status != "created":
        state = f"không tạo được link ({html.escape(d.link_status)})"
    lines.append(f"🕘 Tạo {_when(d.created_at)} · {state}")
    lines.append(f"👆 Click: {d.clicks}" + (f" · gần nhất {_when(d.last_click)}" if d.last_click else ""))
    lines.append("ⓘ Click lấy từ báo cáo Shopee, về trễ khoảng 1 ngày.")
    lines += ["", "📦 <b>Đơn</b>"]
    lines += [f"• …{html.escape(o.order_sn[-8:])} · {html.escape(o.status)} · HH {format_vnd(o.net)} · đặt {_when(o.purchase_time)}"
              + (f" · hoàn thành {_when(o.complete_time)}" if o.complete_time else "") for o in d.orders] or ["Chưa có."]
    lines += ["", "👛 <b>Sổ ví</b>"]
    lines += [f"• {'Thu hồi' if e.clawback else 'Phần khách'} {format_vnd(e.cashback)} · {html.escape(e.status)}"
              for e in d.entries] or ["Chưa có."]
    if d.tickets:
        lines += ["", "📩 <b>Ticket</b>: " + ", ".join(f"#{tid} ({html.escape(status)})" for tid, status in d.tickets)]
    return "\n".join(lines)


def money_text(view: insights.Overview) -> str:
    m, debt, timing = view.money, view.liabilities, view.timing
    lines = [_title(f"Dòng tiền · {insights.PERIODS[view.period]}").rstrip("\n"), ""]
    lines += [
        "ⓘ Tạm tính: mọi đơn chưa huỷ. Thực: đơn Shopee đã trả, đối soát khớp.",
        "",
        f"🛒 GMV <b>{format_vnd(m.gmv)}</b> · {m.orders} đơn · {m.customers} khách",
        f"💰 Hoa hồng gộp {format_vnd(m.gross)} − MCN {format_vnd(m.mcn_fee)} = ròng <b>{format_vnd(m.net)}</b>",
        f" ├ Khách nhận: {format_vnd(m.cashback)} ({_pct(m.cashback, m.net)})",
        f" ├ Biên trước dự phòng: {format_vnd(m.margin_before_reserve)} ({_pct(m.margin_before_reserve, m.net)})",
        f" ├ Dự phòng thuế / phí: {format_vnd(m.reserve)}",
        f" ├ Biên sau dự phòng: <b>{format_vnd(m.margin)}</b> ({_pct(m.margin, m.net)})",
    ]
    if m.ops_cost is None:
        lines.append(" └ Chi phí vận hành / hạ tầng: <b>chưa nhập</b> (bấm ✍️ bên dưới)")
    else:
        lines.append(
            f" └ Chi phí vận hành / hạ tầng {format_vnd(m.ops_cost)} ({m.days} ngày, "
            f"{format_vnd(m.ops_cost_monthly or 0)}/tháng) → lãi <b>{format_vnd(m.profit or 0)}</b>"
        )
    lines += [
        f"❌ Mất do huỷ / gian lận: {format_vnd(m.cancelled_net)} ({m.cancelled_orders} đơn, {m.cancel_rate * 100:.0f}%)",
        f"✅ Thực: ròng {format_vnd(m.settled_net)} · biên {format_vnd(m.settled_margin)}",
        f"⏳ Shopee đã duyệt, chưa trả (sắp về): {format_vnd(debt.upcoming)}",
        "",
        "🏦 <b>Nghĩa vụ với khách</b> (hiện tại)",
        f"Chờ Shopee {format_vnd(debt.pending)} · Đang giữ {format_vnd(debt.holding)} · Trong ví {format_vnd(debt.in_wallet)}",
        f"Chờ chuyển {format_vnd(debt.requested)} · Đã trả {format_vnd(debt.paid)}"
        + (f" · Đang trừ lại {format_vnd(debt.negative)}" if debt.negative else ""),
        f"Shopee đã trả về tài khoản: {format_vnd(debt.shopee_paid)} · Quỹ có chứng từ còn: "
        + ("chưa có kỳ khớp" if debt.fund_headroom is None else format_vnd(debt.fund_headroom)),
        "",
        "⏱ <b>Ra tiền</b> (trung vị)",
        f"Mua → hoàn thành: {_days(timing.purchase_to_complete, timing.samples[0])}",
        f"Hoàn thành → Shopee trả: {_days(timing.complete_to_settled, timing.samples[1])}",
        f"Yêu cầu rút → đã trả: {_days(timing.request_to_paid, timing.samples[2])} · cam kết 3–7 ngày làm việc",
    ]
    return "\n".join(lines)


def growth_text(view: insights.Overview) -> str:
    g, f, m, c = view.growth, view.funnel, view.money, view.concentration
    active = max(1, g.active_30d)
    lines = [_title(f"Tăng trưởng · {insights.PERIODS[view.period]}").rstrip("\n"), ""]
    lines += [
        f"👥 Khách: <b>{g.total}</b> (Telegram {g.telegram} · Zalo {g.zalo}) · mới trong kỳ {g.new} "
        f"(TG {g.new_telegram} · Zalo {g.new_zalo})",
        f"🔥 Hoạt động: 7 ngày {g.active_7d} · 30 ngày {g.active_30d}",
        "",
        "🔻 <b>Phễu</b> (khách tạo link trong kỳ)",
        f"{f.linked} tạo link → {f.clicked} có click ({_pct(f.clicked, f.linked)}) → {f.ordered} có đơn "
        f"({_pct(f.ordered, f.linked)}) → {f.completed} hoàn thành → {f.settled} Shopee đã trả",
        f"{f.links} link · {f.clicks} click · {f.orders} đơn · click → đơn {_pct(f.orders, f.clicks)}",
        "ⓘ Click lấy từ báo cáo Shopee, về trễ khoảng 1 ngày: link mới tạo chưa có click là bình thường.",
        "",
        "💎 <b>Giá trị</b>",
        f"Biên / khách hoạt động 30 ngày: {format_vnd(m.margin // active)} · HH ròng / khách: {format_vnd(m.net // active)}",
        f"Đơn TB: GMV {format_vnd(m.gmv // m.orders) if m.orders else '–'} · HH {format_vnd(m.net // m.orders) if m.orders else '–'}"
        f" · {m.orders / active:.1f} đơn / khách",
        f"Phụ thuộc: khách lớn nhất {c.top1_share * 100:.0f}% biên · top 10% khách {c.top10_share * 100:.0f}% "
        f"({c.earners} khách có biên)",
        "",
        "📡 <b>Kênh</b> (từ đầu)",
    ]
    for name, label in (("telegram", "Telegram"), ("zalo", "Zalo")):
        people, orders, margin = view.channels[name]
        lines.append(f"{label}: {people} khách · {orders} đơn · biên {format_vnd(margin)}")
    for title, rows in (("🏷 Ngành hàng", view.categories), ("🏪 Shop", view.shops)):
        lines += ["", f"<b>{title}</b> (theo HH ròng)"]
        lines += [f"• {html.escape(r.label[:40])} · {r.orders} đơn · {format_vnd(r.net)}" for r in rows] or ["Chưa có."]
    lines += ["", "🔁 <b>Giữ chân</b> (tuần vào · quay lại tuần sau · tuần thứ 4)"]
    lines += [f"• {k.week}: {k.size} khách · {_pct(k.next_week, k.size)} · {_pct(k.week_4, k.size)}"
              for k in view.cohorts if k.size] or ["Chưa có."]
    return "\n".join(lines)


def breakeven_text(b: insights.Breakeven) -> str:
    """Hoà vốn theo từng mức % hoàn. Chỉ để xem: không đổi chính sách."""
    lines = [_title("Hoà vốn").rstrip("\n"), ""]
    if b.ops_cost_monthly is None:
        return "\n".join(lines + ["Chưa có chi phí vận hành. Bấm ✍️ Chi phí vận hành / tháng để nhập trước."])
    share = "–" if b.current_share is None else f"{b.current_share * 100:.0f}%"
    lines += [
        f"💼 Chi phí vận hành / hạ tầng: <b>{format_vnd(b.ops_cost_monthly)}</b>/tháng",
        f"📊 Số thật: {b.orders} đơn · HH ròng TB "
        f"{'–' if b.net_per_order is None else format_vnd(b.net_per_order)}/đơn · dự phòng {b.reserve_rate * 100:.1f}% · "
        f"đang hoàn {share} ({b.formula.upper()})",
        f"📅 30 ngày qua: HH ròng {format_vnd(b.net_30d)} · {b.orders_30d} đơn",
        "",
        "<b>% hoàn · biên của anh · cần mỗi tháng để hoà vốn</b>",
    ]
    current = b.current
    for row in b.rows:
        mark = "👉 " if current is not None and row is current else "• "
        need = "–" if row.need_net_month is None else format_vnd(row.need_net_month)
        orders = "" if row.need_orders_month is None else f" (~{row.need_orders_month:,} đơn)".replace(",", ".")
        lines.append(f"{mark}{row.share_percent}% · biên {row.margin_rate * 100:.0f}% · HH ròng {need}{orders}")
    if current is not None and current.need_net_month:
        lines += ["", f"Ở mức đang hoàn: 30 ngày qua đạt {b.net_30d * 100 / current.need_net_month:.1f}% mức hoà vốn."]
    lines += [
        "",
        "ⓘ Chỉ để xem, không đổi % hoàn của khách. Đổi % ở 💰 Chính sách (áp cho link mới).",
        "ⓘ Còn ít đơn nên HH ròng trung bình mỗi đơn còn dao động.",
    ]
    return "\n".join(lines)


def ops_text(checks: list[insights.Check], locked: tuple[str, ...] = ()) -> str:
    lines = [_title("Vận hành").rstrip("\n"), ""]
    lines += [f"{'🟢' if c.ok else '🔴'} <b>{html.escape(c.label)}</b>: {html.escape(c.value)}" for c in checks]
    if locked:
        lines += ["", f"🔒 Ví còn khoá: {len(locked)} lý do (xem 👛 Ví khách)."]
    return "\n".join(lines)


def users_text(items: list[insights.Customer], key: str, page: int, pages: int) -> str:
    title = insights.SEGMENTS.get(key) or f"xếp theo {SORT_LABELS.get(key, 'Biên').lower()}"
    lines = [_title(f"Khách hàng · {title}").rstrip("\n"), ""]
    counts = {}
    for c in items:
        counts[c.segment] = counts.get(c.segment, 0) + 1
    start = (page - 1) * PAGE
    shown = _filter(items, key)[start:start + PAGE]
    if not shown:
        lines.append("Chưa có khách trong nhóm này.")
    for n, c in enumerate(shown, start + 1):
        lines.append(
            f"{n}. {insights.SEGMENTS[c.segment].split()[0]} {html.escape(c.label[:28])} · {c.orders} đơn · "
            f"biên {format_vnd(c.margin)} · ví {format_vnd(c.wallet)}"
            + (f" · ⚠️ {', '.join(c.flags)}" if c.flags else "")
        )
    lines += ["", " · ".join(f"{label} {counts.get(seg, 0)}" for seg, label in insights.SEGMENTS.items())]
    if pages > 1:
        lines.append(f"Trang {page}/{pages}")
    return "\n".join(lines)


def _filter(items: list[insights.Customer], key: str) -> list[insights.Customer]:
    if key in insights.SEGMENTS:
        return insights.sort_customers([c for c in items if c.segment == key])
    return insights.sort_customers(items, key)


def detail_text(c: insights.Customer, m: insights.Money, prof: insights.Profile, events: list[insights.Event]) -> str:
    lines = [_title("Khách hàng", html.escape(c.label[:40])).rstrip("\n"), ""]
    lines += [
        f"{insights.SEGMENTS[c.segment]} · {'Zalo' if c.channel == 'zalo' else 'Telegram'} · ID <code>{c.user_id}</code>",
        f"Vào {_when(c.joined)} · dùng gần nhất {_when(c.last_active)}",
    ]
    if c.flags:
        lines.append("⚠️ " + ", ".join(c.flags))
    lines += [
        "",
        f"🔗 {c.links} link · {c.clicks} click · {c.orders} đơn ({c.completed} hoàn thành, {c.cancelled} huỷ)",
        f"🛒 GMV {format_vnd(c.gmv)} · HH ròng {format_vnd(c.net)}",
        f"💸 Khách nhận {format_vnd(c.cashback)} · dự phòng {format_vnd(c.reserve)} · biên <b>{format_vnd(c.margin)}</b>",
        f"✅ Thực (Shopee đã trả): ròng {format_vnd(m.settled_net)} · biên {format_vnd(m.settled_margin)}",
        f"👛 Ví {format_vnd(c.wallet)} · chờ chuyển {format_vnd(c.requested)} · đã nhận {format_vnd(c.paid)}",
        "",
        "🏦 " + (f"{html.escape(prof.bank)} · {prof.bank_state}" if prof.bank else "Chưa khai tài khoản"),
        "📋 Điều khoản: " + (html.escape(prof.terms) if prof.terms else "chưa đồng ý bản nào"),
    ]
    if prof.prefs is not None:
        off = [name for name, on in prof.prefs.items() if not on]
        lines.append("🔔 Tắt thông báo: " + (", ".join(off) if off else "không"))
    lines += ["", "🕘 <b>Gần đây</b>"]
    lines += [f"• {_when(e.at)} {html.escape(e.text)}" for e in events[:12]] or ["Chưa có."]
    return "\n".join(lines)[:3900]


class InsightsAdmin:
    def __init__(self, db_path: str, audit: AuditFn | None = None, waiting: dict | None = None,
                 sync_interval_minutes: int = 240, locked_reasons: Callable[[], tuple[str, ...]] | None = None):
        self.db_path = db_path
        self.audit = audit
        self.waiting = {} if waiting is None else waiting
        self.sync_interval = sync_interval_minutes
        self.locked_reasons = locked_reasons

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data not in ("c:in:cost", "c:in:f") and _GOAL.fullmatch(data) is None:
            self.waiting.pop(admin_id, None)
        if (found := _MONEY.fullmatch(data)) is not None:
            return self._overview(found.group(1), found.group(2), now)
        if data == "c:in:o":
            with insights.open_readonly(self.db_path) as conn:
                checks = insights.operations(conn, now, self.sync_interval)
            locked = self.locked_reasons() if self.locked_reasons else ()
            return BotReply(ops_text(checks, locked), inline_keyboard=((("🔄 Làm mới", "c:in:o"),), *NAV))
        if (found := _USERS.fullmatch(data)) is not None:
            return self._users(found.group(1), int(found.group(2)), now)
        if (found := _DETAIL.fullmatch(data)) is not None:
            return self._detail(int(found.group(1)), now)
        if data == "c:in:b":
            with insights.open_readonly(self.db_path) as conn:
                text = breakeven_text(insights.breakeven(conn, now))
            return BotReply(text, inline_keyboard=((("✍️ Chi phí vận hành / tháng", "c:in:cost"),), *NAV))
        if data == "c:in:t":
            return self._goals(now)
        if data == "c:in:f":
            return self.search(admin_id, "", now)
        if (found := _LINK.fullmatch(data)) is not None:
            return self._link(int(found.group(1)))
        if (found := _GOAL.fullmatch(data)) is not None and found.group(1) in insights.GOALS:
            return self._ask_goal(admin_id, found.group(1), now)
        if data == "c:in:cost":
            self.waiting[admin_id] = ("cost", now + COST_WAIT)
            with insights.open_readonly(self.db_path) as conn:
                current = insights.ops_cost_monthly(conn)
            return BotReply(
                "✍️ <b>Chi phí vận hành và hạ tầng mỗi tháng</b>\n\n"
                f"Hiện tại: {'chưa nhập' if current is None else format_vnd(current)}.\n"
                "Gõ tổng chi phí một tháng: máy chủ, điện, mạng, gói Zalo, công vận hành… "
                "Ví dụ <code>1500000</code>, <code>1,5tr</code> hoặc <code>800k</code>. Gõ 0 nếu không có.\n\n"
                "ⓘ Bot chia theo số ngày của kỳ đang xem để tính lãi sau chi phí.",
                inline_keyboard=((("✖️ Hủy", "c:in:m:30d"),),),
            )
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)

    def consume_text(self, admin_id: int, text: str, now: datetime) -> BotReply | None:
        entry = self.waiting.get(admin_id)
        if entry is None:
            return None
        kind, deadline = entry
        stripped = (text or "").strip()
        if deadline <= now or stripped.startswith("/"):
            self.waiting.pop(admin_id, None)
            return None
        if kind == "search":
            self.waiting.pop(admin_id, None)
            return self.search(admin_id, stripped, now)
        if kind != "cost":
            return self._save_goal(admin_id, kind, stripped, now)
        amount = parse_cost(stripped)
        if amount is None:
            return BotReply("⚠️ Chưa đọc được số. Gõ ví dụ <code>1500000</code>, <code>1,5tr</code> hoặc <code>800k</code>.",
                            inline_keyboard=((("✖️ Hủy", "c:in:m:30d"),),))
        self.waiting.pop(admin_id, None)
        repo = TrackingRepository(self.db_path)
        before = repo.get_state(insights.OPS_COST_KEY)
        repo.set_state(insights.OPS_COST_KEY, str(amount))
        if self.audit is not None and before != str(amount):
            self.audit(admin_id, "ops_cost", None if before in (None, "") else {"vnd": int(before)}, {"vnd": amount}, now)
        return self._overview("m", "30d", now, notice=f"✅ Đã lưu chi phí vận hành: {format_vnd(amount)}/tháng.")

    def search(self, admin_id: int, query: str, now: datetime) -> BotReply:
        """`/tim <mã>` hoặc nút 🔍 Tìm. Không có mã: chờ admin gõ (10 phút)."""
        query = " ".join((query or "").split())
        if not query:
            self.waiting[admin_id] = ("search", now + COST_WAIT)
            return BotReply(_title("🔍 Tìm") + SEARCH_HELP, inline_keyboard=((("✖️ Hủy", "c:menu:home"),),))
        with insights.open_readonly(self.db_path) as conn:
            hits = insights.search(conn, query)
        rows = [((f"{SEARCH_ICONS[h.kind]} {h.title}"[:60], target),) for h in hits if (target := _search_target(h))]
        return BotReply(search_text(query, hits), inline_keyboard=(*rows, (("🔍 Tìm tiếp", "c:in:f"),), *NAV))

    def _link(self, link_id: int) -> BotReply:
        with insights.open_readonly(self.db_path) as conn:
            detail = insights.link_detail(conn, link_id)
        if detail is None:
            return BotReply("Không thấy link này.", inline_keyboard=((("🔍 Tìm tiếp", "c:in:f"),), *NAV))
        return BotReply(link_text(detail)[:4000], inline_keyboard=(
            (("👤 Hồ sơ khách", f"c:in:d:{detail.user_id}"),),
            (("🔍 Tìm tiếp", "c:in:f"),),
            *NAV,
        ))

    def _goals(self, now: datetime, notice: str = "") -> BotReply:
        with insights.open_readonly(self.db_path) as conn:
            text = goals_text(insights.goals(conn, now, self.sync_interval))
        if notice:
            text = f"{notice}\n\n{text}"
        buttons = [(f"✍️ {label}", f"c:in:t:{key}") for key, label in GOAL_BUTTONS.items()]
        rows = tuple(tuple(buttons[i:i + 2]) for i in range(0, len(buttons), 2))
        return BotReply(text[:4000], inline_keyboard=(*rows, (("🔄 Làm mới", "c:in:t"),), *NAV))

    def _ask_goal(self, admin_id: int, key: str, now: datetime) -> BotReply:
        self.waiting[admin_id] = (key, now + COST_WAIT)
        with insights.open_readonly(self.db_path) as conn:
            g = insights.goals(conn, now, self.sync_interval)
        r = g.row(key)
        hint = GOAL_HINTS.get(key, "")
        if key == "net" and g.breakeven_net:
            hint = f"Mức hoà vốn ở % đang hoàn (🧮 Hoà vốn): {format_vnd(g.breakeven_net)} / tháng."
        if key == "cancel":
            hint = "Ví dụ 10: tỉ lệ huỷ 30 ngày quá 10% thì báo đỏ."
        current = "chưa đặt" if r.target is None else goal_value(r.unit, r.target)
        return BotReply(
            f"✍️ <b>Mục tiêu: {r.label}</b>\n\n"
            f"Số thật hiện tại: {goal_value(r.unit, r.actual)} · đang đặt: {current}.\n"
            + (f"{hint}\n" if hint else "")
            + f"\nGõ số, ví dụ {GOAL_EXAMPLES[r.unit]}. Gõ <code>bỏ</code> để xoá mục tiêu này.",
            inline_keyboard=((("✖️ Hủy", "c:in:t"),),),
        )

    def _save_goal(self, admin_id: int, key: str, text: str, now: datetime) -> BotReply:
        label, unit, _kind = insights.GOALS[key]
        clear = text.lower() in CLEAR_WORDS
        value = None if clear else parse_goal(unit, text)
        if not clear and value is None:
            return BotReply(f"⚠️ Chưa đọc được số. Gõ ví dụ {GOAL_EXAMPLES[unit]}, hoặc <code>bỏ</code> để xoá.",
                            inline_keyboard=((("✖️ Hủy", "c:in:t"),),))
        self.waiting.pop(admin_id, None)
        repo = TrackingRepository(self.db_path)
        try:
            stored = json.loads(repo.get_state(insights.GOALS_KEY) or "{}")
        except ValueError:
            stored = {}
        stored = stored if isinstance(stored, dict) else {}
        before = stored.pop(key, None)
        if value is not None:
            stored[key] = value
        repo.set_state(insights.GOALS_KEY, json.dumps(stored, sort_keys=True))
        if self.audit is not None and before != value:
            self.audit(admin_id, "goal", {"key": key, "value": before}, {"key": key, "value": value}, now)
        notice = f"✅ Đã bỏ mục tiêu: {label}." if value is None else f"✅ Đã đặt mục tiêu: {label} {goal_value(unit, value)}."
        return self._goals(now, notice=notice)

    def _overview(self, kind: str, period: str, now: datetime, notice: str = "") -> BotReply:
        with insights.open_readonly(self.db_path) as conn:
            view = insights.overview(conn, period, now, self.sync_interval)
        text = money_text(view) if kind == "m" else growth_text(view)
        if notice:
            text = f"{notice}\n\n{text}"
        rows: list[tuple[tuple[str, str], ...]] = [_periods(kind, view.period)]
        if kind == "m":
            rows.append((("✍️ Chi phí vận hành / tháng", "c:in:cost"), ("🧮 Hoà vốn", "c:in:b")))
        return BotReply(text[:4000], inline_keyboard=(*rows, *NAV))

    def _users(self, key: str, page: int, now: datetime) -> BotReply:
        if key not in SORT_LABELS and key not in insights.SEGMENTS:
            key = "margin"
        with insights.open_readonly(self.db_path) as conn:
            items = insights.customers(conn, now)
        chosen = _filter(items, key)
        pages = max(1, -(-len(chosen) // PAGE))
        page = min(max(1, page), pages)
        start = (page - 1) * PAGE
        rows: list[tuple[tuple[str, str], ...]] = [
            ((f"{n}. {c.label[:30]} · {format_vnd(c.margin)}", f"c:in:d:{c.user_id}"),)
            for n, c in enumerate(chosen[start:start + PAGE], start + 1)
        ]
        nav = []
        if page > 1:
            nav.append(("◀️", f"c:in:u:{key}:{page - 1}"))
        if page < pages:
            nav.append(("▶️", f"c:in:u:{key}:{page + 1}"))
        if nav:
            rows.append(tuple(nav))
        rows.append(tuple((("• " if k == key else "") + label, f"c:in:u:{k}:1") for k, label in SORT_LABELS.items()))
        segments = [(label.split()[0], f"c:in:u:{seg}:1") for seg, label in insights.SEGMENTS.items()]
        rows.append(tuple(segments))
        return BotReply(users_text(items, key, page, pages), inline_keyboard=(*rows, *NAV))

    def _detail(self, user_id: int, now: datetime) -> BotReply:
        with insights.open_readonly(self.db_path) as conn:
            found = next((c for c in insights.customers(conn, now) if c.user_id == user_id), None)
            if found is None:
                return BotReply("Không thấy khách này.", inline_keyboard=NAV)
            text = detail_text(found, insights.money(conn, EPOCH, 1, user_id),
                               insights.profile(conn, user_id), insights.timeline(conn, user_id))
        return BotReply(text, inline_keyboard=(
            (("👛 Ví của khách", f"c:wl:u:{user_id}"),),
            (("◀️ Khách hàng", "c:in:u:margin:1"),),
            *NAV,
        ))
