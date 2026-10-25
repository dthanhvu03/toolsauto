"""/admin → 💹 Dòng tiền · 📈 Tăng trưởng · 🛠 Vận hành · 👥 Khách hàng (PLAN-089). Số tính ở insights.py.

Chỉ đọc DB, trừ một việc: admin nhập chi phí vận hành và hạ tầng mỗi tháng (bot_state, ghi 📊 Lịch sử).
Callback: c:in:m:<kỳ> · c:in:g:<kỳ> · c:in:o · c:in:u:<sắp xếp|nhóm>:<trang> · c:in:d:<id> · c:in:cost · c:in:b
"""

from __future__ import annotations

import html
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
_COST = re.compile(r"^\s*([\d.,\s]+)\s*(k|nghìn|ngàn|tr|triệu|trieu)?\s*$", re.IGNORECASE)
COST_MAX = 10_000_000_000
COST_WAIT = timedelta(minutes=10)
PAGE = 8
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
HOME = (("◀️ Tổng quan", "c:menu:home"),)
NAV = (
    (("💹 Dòng tiền", "c:in:m:30d"), ("📈 Tăng trưởng", "c:in:g:30d")),
    (("🛠 Vận hành", "c:in:o"), ("👥 Khách hàng", "c:in:u:margin:1")),
    HOME,
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
        if data != "c:in:cost":
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
        if data == "c:in:cost":
            self.waiting[admin_id] = now + COST_WAIT
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
        deadline = self.waiting.get(admin_id)
        if deadline is None:
            return None
        stripped = (text or "").strip()
        if deadline <= now or stripped.startswith("/"):
            self.waiting.pop(admin_id, None)
            return None
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
