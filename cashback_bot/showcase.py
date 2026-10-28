"""/admin → 🗓 Thống kê → 🖼 Ảnh đăng bài: ảnh số liệu thật để chủ bot đăng bài lấy uy tín. Chỉ đọc DB.

Chủ bot chọn (2026-10-28): ảnh kèm bài viết soạn sẵn; tiền ghi «tạm tính»; có đơn gần đây, tên khách che.
- Bot chưa chi trả lần nào thì không viết như đã trả. Dòng «Đã chi trả» chỉ hiện khi có lượt rút đã trả.
- Tên khách chỉ còn chữ đầu và chữ cuối; không có tên thì ghi kênh (Khách Telegram / Khách Zalo).
- Không hiện tên sản phẩm (chủ bot bỏ 2026-10-28).
- Chủ bot ẩn/hiện từng mục trước khi tạo (Options, lưu bot_state `showcase_options`). Dòng «Số tạm tính…» cuối ảnh
  luôn có, không tắt được.
Font Be Vietnam Pro (OFL, cashback_bot/assets/fonts).
Callback: c:pb:home (màn chỉnh) · c:pb:t:<mục> (bật/tắt) · c:pb:d:<ngày> · c:pb:n:<số đơn> · c:pb:go (tạo ảnh).
"""

from __future__ import annotations

import html
import io
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply, Keyboard
from cashback_bot.money import format_vnd
from cashback_bot.payouts import PAID_STATES
from cashback_bot.wallet import CLAWBACK_TAG

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
HOME = "c:pb:home"
CARD = "c:pb:go"
STATE_KEY = "showcase_options"
CHART_CHOICES = (7, 14)
RECENT_CHOICES = (3, 4, 6)
SMALL_VND = 1_000
_ACTION = re.compile(r"^c:pb:(?:(t):([a-z_]{3,12})|(d|n):(\d{1,2}))$")
FONTS = Path(__file__).parent / "assets" / "fonts"
STATUS_LABELS = {"pending": "Chờ sàn duyệt", "holding": "Đang giữ", "available": "Đã duyệt"}
NOTE = "Số tạm tính. Tiền hoàn chỉ chi khi sàn đã duyệt và trả hoa hồng."

# Khổ ảnh 1080 px; vẽ gấp đôi rồi thu nhỏ cho viền tròn mịn.
WIDTH = 1080
SCALE = 2
PAD = 56
INK = (31, 26, 23)
MUTED = (122, 111, 105)
PAPER = (255, 247, 242)
WHITE = (255, 255, 255)
ORANGE = (238, 77, 45)
ORANGE_LIGHT = (255, 140, 66)
PEACH = (255, 222, 204)
GREEN = (18, 140, 74)
# màu từng phần thanh tiền: chờ sàn, đang giữ, đã duyệt
SEGMENTS = {"pending": (255, 179, 102), "holding": (255, 112, 67), "available": (18, 140, 74)}


@dataclass(frozen=True)
class Options:
    """Mục hiện trên ảnh. Mặc định hiện hết, trừ ẩn đơn nhỏ."""

    members: bool = True
    links: bool = True
    orders: bool = True
    money: bool = True
    chart: bool = True
    recent: bool = True
    hide_small: bool = False
    chart_days: int = 7
    recent_n: int = 4

    @classmethod
    def load(cls, raw: str | None) -> Options:
        try:
            saved = json.loads(raw or "{}")
        except ValueError:
            saved = {}
        base = cls()
        kept = {}
        for f in fields(cls):
            value = saved.get(f.name) if isinstance(saved, dict) else None
            if isinstance(getattr(base, f.name), bool) and isinstance(value, bool):
                kept[f.name] = value
        if saved.get("chart_days") in CHART_CHOICES:
            kept["chart_days"] = saved["chart_days"]
        if saved.get("recent_n") in RECENT_CHOICES:
            kept["recent_n"] = saved["recent_n"]
        return replace(base, **kept)

    def dump(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


# mục bật/tắt → tên trên nút
TOGGLES = {
    "members": "Thành viên",
    "links": "Link",
    "orders": "Đơn",
    "money": "Hoàn tiền ghi nhận",
    "chart": "Biểu đồ",
    "recent": "Đơn gần đây",
    "hide_small": f"Ẩn đơn dưới {format_vnd(SMALL_VND)}",
}


@dataclass(frozen=True)
class Showcase:
    members: int
    links: int
    orders: int
    buyers: int
    days_running: int
    pending_vnd: int
    holding_vnd: int
    available_vnd: int
    paid_vnd: int
    paid_count: int
    daily: list[tuple[str, int, int]]  # (nhãn ngày, link, đơn)
    recent: list[tuple[str, int, str, str]]  # (tên che, tiền hoàn, trạng thái, ngày)
    updated_at: datetime
    options: Options = Options()

    @property
    def recorded_vnd(self) -> int:
        return self.pending_vnd + self.holding_vnd + self.available_vnd


def mask_name(name: str | None, user_id: int) -> str:
    letters = re.sub(r"[\W_\d]", "", name or "")
    if len(letters) < 2:
        return "Khách Zalo" if user_id < 0 else "Khách Telegram"
    return f"{letters[0].upper()}***{letters[-1].lower()}"


def _ict_day(stamp: str | None) -> str | None:
    if not stamp:
        return None
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return moment.astimezone(ICT).strftime("%Y-%m-%d")


def collect(conn: sqlite3.Connection, now: datetime, options: Options = Options()) -> Showcase:
    members = int(conn.execute("SELECT COUNT(*) FROM telegram_users").fetchone()[0])
    links = conn.execute("SELECT created_at FROM link_requests WHERE link_status = 'created'").fetchall()
    orders = conn.execute(
        "SELECT order_sn, telegram_user_id, purchase_time FROM shopee_conversions "
        "WHERE COALESCE(order_status, '') NOT LIKE '%CANCEL%'"
    ).fetchall()
    first = conn.execute("SELECT MIN(created_at) FROM link_requests").fetchone()[0]
    today = now.astimezone(ICT).date()
    days_running = (today - datetime.fromisoformat(_ict_day(first)).date()).days + 1 if first else 0
    money = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN status = 'pending' THEN cashback_vnd END), 0),
               COALESCE(SUM(CASE WHEN status = 'holding' THEN cashback_vnd END), 0),
               COALESCE(SUM(CASE WHEN status = 'available' THEN cashback_vnd END), 0)
        FROM cashback_entries
        """
    ).fetchone()
    marks = ", ".join("?" for _ in PAID_STATES)
    paid = conn.execute(
        f"SELECT COALESCE(SUM(amount_vnd), 0), COUNT(*) FROM cashback_payouts WHERE status IN ({marks})", PAID_STATES
    ).fetchone()

    link_days: dict[str, int] = {}
    for (stamp,) in links:
        day = _ict_day(stamp)
        link_days[day] = link_days.get(day, 0) + 1
    order_days: dict[str, set[str]] = {}
    for order_sn, _user, stamp in orders:
        order_days.setdefault(_ict_day(stamp), set()).add(order_sn)
    daily = []
    for back in range(options.chart_days - 1, -1, -1):
        day = today - timedelta(days=back)
        key = day.isoformat()
        label = "Hôm nay" if back == 0 else day.strftime("%d/%m")
        daily.append((label, link_days.get(key, 0), len(order_days.get(key, ()))))

    recent = []
    rows = conn.execute(
        """
        SELECT e.telegram_user_id, e.cashback_vnd, e.status, e.purchase_time,
               COALESCE((SELECT display_name FROM channel_identities c WHERE c.internal_user_id = e.telegram_user_id
                         ORDER BY c.created_at LIMIT 1),
                        (SELECT username FROM telegram_users t WHERE t.telegram_user_id = e.telegram_user_id)) AS name
        FROM cashback_entries e
        WHERE e.status IN ('pending', 'holding', 'available') AND instr(e.conversion_id, ?) = 0 AND e.cashback_vnd >= ?
        ORDER BY e.purchase_time DESC LIMIT ?
        """,
        (CLAWBACK_TAG, SMALL_VND if options.hide_small else 1, options.recent_n),
    ).fetchall()
    for user, cashback, status, stamp, name in rows:
        day = _ict_day(stamp)
        recent.append((mask_name(name, int(user)), int(cashback),
                       STATUS_LABELS[status], datetime.fromisoformat(day).strftime("%d/%m") if day else ""))
    return Showcase(
        members=members, links=len(links), orders=len({o[0] for o in orders}),
        buyers=len({o[1] for o in orders if o[1] is not None}), days_running=days_running,
        pending_vnd=int(money[0]), holding_vnd=int(money[1]), available_vnd=int(money[2]),
        paid_vnd=int(paid[0]), paid_count=int(paid[1]), daily=daily, recent=recent, updated_at=now.astimezone(ICT),
        options=options,
    )


def post_text(s: Showcase) -> str:
    """Bài viết soạn sẵn để chủ bot sao chép, đi kèm ảnh. Không hứa số, không viết như đã trả khi chưa trả."""
    o = s.options
    lines = [f"🛍 Bot hoàn tiền Shopee & TikTok Shop: số liệu thật sau {s.days_running} ngày chạy", ""]
    counts = [text for on, text in ((o.members, f"👥 {s.members} thành viên"), (o.links, f"🔗 {s.links} link đã tạo"),
                                    (o.orders, f"🛒 {s.orders} đơn ghi nhận")) if on]
    if counts:
        lines.append(" · ".join(counts))
    if o.money:
        lines.append(f"💰 {format_vnd(s.recorded_vnd)} hoàn tiền đã ghi nhận (tạm tính, chờ sàn duyệt)")
        if s.paid_count:
            lines.append(f"✅ Đã chi trả {format_vnd(s.paid_vnd)} qua {s.paid_count} lượt rút")
    if lines[-1] == "":
        lines.pop()
    lines += [
        "",
        "Cách dùng:",
        "1️⃣ Gửi link sản phẩm cho bot",
        "2️⃣ Mua qua link bot gửi lại",
        "3️⃣ Theo dõi tiền hoàn trong 👛 Ví",
        "",
        f"ⓘ {NOTE}",
    ]
    return "\n".join(lines)


def admin_text(s: Showcase) -> str:
    stamp = s.updated_at.strftime("%H:%M %d/%m/%Y")
    return (f"🖼 <b>Ảnh đăng bài</b> · số liệu lúc {stamp}\n\n"
            "Ảnh ở tin trên. Bài viết dưới đây chạm vào là sao chép:\n"
            f"<pre>{html.escape(post_text(s))}</pre>")


# --- Vẽ ảnh ---------------------------------------------------------------------------------------


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"BeVietnamPro-{weight}.ttf"), size * SCALE)


class _Canvas:
    """Toạ độ theo khổ 1080; tự nhân SCALE."""

    def __init__(self, height: int):
        self.image = Image.new("RGB", (WIDTH * SCALE, height * SCALE), PAPER)
        self.draw = ImageDraw.Draw(self.image)

    def text(self, xy, text, font, fill=INK, anchor="la"):
        self.draw.text((xy[0] * SCALE, xy[1] * SCALE), text, font=font, fill=fill, anchor=anchor)

    def box(self, x0, y0, x1, y1, fill, radius=28):
        self.draw.rounded_rectangle((x0 * SCALE, y0 * SCALE, x1 * SCALE, y1 * SCALE), radius * SCALE, fill=fill)

    def card(self, x0, y0, x1, y1, radius=32):
        shadow = Image.new("L", self.image.size, 0)
        ImageDraw.Draw(shadow).rounded_rectangle(
            (x0 * SCALE, (y0 + 8) * SCALE, x1 * SCALE, (y1 + 8) * SCALE), radius * SCALE, fill=60)
        shadow = shadow.filter(ImageFilter.GaussianBlur(18 * SCALE))
        self.image.paste((214, 160, 135), mask=shadow)
        self.box(x0, y0, x1, y1, WHITE, radius)

    def width(self, text, font) -> float:
        return self.draw.textlength(text, font=font) / SCALE


def _header(c: _Canvas, s: Showcase, height: int) -> None:
    ramp = Image.linear_gradient("L").rotate(90).resize((WIDTH * SCALE, height * SCALE))
    c.image.paste(Image.composite(Image.new("RGB", ramp.size, ORANGE), Image.new("RGB", ramp.size, ORANGE_LIGHT),
                                  ramp), (0, 0))
    pill = f"SỐ LIỆU THẬT · CẬP NHẬT {s.updated_at.strftime('%H:%M %d/%m/%Y')}"
    small = _font("SemiBold", 22)
    c.box(PAD, 56, PAD + c.width(pill, small) + 40, 100, (247, 110, 60), radius=22)
    c.text((PAD + 20, 78), pill, small, WHITE, anchor="lm")
    c.text((PAD, 124), "Bot hoàn tiền", _font("ExtraBold", 80), WHITE)
    c.text((PAD, 226), f"Shopee · TikTok Shop · {s.days_running} ngày chạy", _font("Medium", 34), (255, 236, 226))


def _kpis(c: _Canvas, s: Showcase, top: int) -> int | None:
    o = s.options
    items = [(value, label) for on, value, label in ((o.members, s.members, "Thành viên"),
                                                     (o.links, s.links, "Link đã tạo"),
                                                     (o.orders, s.orders, "Đơn ghi nhận")) if on]
    if not items:
        return None
    gap = 24
    width = (WIDTH - 2 * PAD - (len(items) - 1) * gap) / len(items)
    for i, (value, label) in enumerate(items):
        x0 = PAD + i * (width + gap)
        c.card(x0, top, x0 + width, top + 190)
        c.text((x0 + width / 2, top + 82), f"{value:,}".replace(",", "."), _font("ExtraBold", 76), ORANGE, "mm")
        c.text((x0 + width / 2, top + 150), label, _font("Medium", 28), MUTED, "mm")
    return top + 190


def _money(c: _Canvas, s: Showcase, top: int) -> int | None:
    if not s.options.money:
        return None
    paid_row = 56 if s.paid_count else 0
    bottom = top + 330 + paid_row
    c.card(PAD, top, WIDTH - PAD, bottom)
    x = PAD + 40
    c.text((x, top + 40), "Hoàn tiền đã ghi nhận cho khách", _font("SemiBold", 30), MUTED)
    c.text((x, top + 84), format_vnd(s.recorded_vnd), _font("ExtraBold", 92), GREEN)
    c.text((WIDTH - PAD - 40, top + 62), "tạm tính", _font("SemiBold", 24), MUTED, "rm")
    bar_top, bar_w = top + 214, WIDTH - 2 * PAD - 80
    c.box(x, bar_top, x + bar_w, bar_top + 22, (245, 236, 230), radius=11)
    parts = [("pending", s.pending_vnd), ("holding", s.holding_vnd), ("available", s.available_vnd)]
    total = max(s.recorded_vnd, 1)
    start = x
    for key, value in parts:
        if value <= 0:
            continue
        end = start + max(bar_w * value / total, 22)
        c.box(start, bar_top, min(end, x + bar_w), bar_top + 22, SEGMENTS[key], radius=11)
        start = end
    legend_y = bar_top + 64
    lx = x
    for key, value in parts:
        if value <= 0:
            continue
        label = f"{STATUS_LABELS[key]} {format_vnd(value)}"
        c.box(lx, legend_y - 9, lx + 18, legend_y + 9, SEGMENTS[key], radius=9)
        font = _font("Medium", 24)
        c.text((lx + 28, legend_y), label, font, INK, "lm")
        lx += 28 + c.width(label, font) + 34
    if s.paid_count:
        c.text((x, legend_y + 58), f"Đã chi trả {format_vnd(s.paid_vnd)} qua {s.paid_count} lượt rút",
               _font("SemiBold", 28), GREEN, "lm")
    return bottom


def _chart(c: _Canvas, s: Showcase, top: int) -> int | None:
    if not s.options.chart:
        return None
    bottom = top + 380
    c.card(PAD, top, WIDTH - PAD, bottom)
    x = PAD + 40
    c.text((x, top + 40), f"{len(s.daily)} ngày gần đây", _font("SemiBold", 30), INK)
    font = _font("Medium", 22)
    lx = WIDTH - PAD - 40
    for label, color in (("Đơn", ORANGE), ("Link", PEACH)):
        lx -= c.width(label, font)
        c.text((lx, top + 58), label, font, MUTED, "lm")
        c.box(lx - 28, top + 49, lx - 10, top + 67, color, radius=9)
        lx -= 56
    base, height = bottom - 70, 190
    peak = max([max(links, orders) for _l, links, orders in s.daily] + [1])
    slot = (WIDTH - 2 * PAD - 80) / len(s.daily)
    # 7 ngày: cột 28 px, ghi nhãn mọi ngày; 14 ngày: cột hẹp lại, nhãn ngày cách một (luôn có Hôm nay)
    bar = min(28, slot * 0.3)
    value_font = _font("SemiBold", 22 if bar >= 28 else 18)
    every = 1 if bar >= 28 else 2
    for i, (label, links, orders) in enumerate(s.daily):
        mid = x + slot * i + slot / 2
        for offset, value, color in ((-bar * 0.6, links, PEACH), (bar * 0.6, orders, ORANGE)):
            h = max(height * value / peak, 6)
            c.box(mid + offset - bar / 2, base - h, mid + offset + bar / 2, base, color, radius=min(10, bar / 2))
            if value:
                c.text((mid + offset, base - h - 18), str(value), value_font, INK, "mm")
        if (len(s.daily) - 1 - i) % every == 0:
            c.text((mid, base + 32), label, font, INK if label == "Hôm nay" else MUTED, "mm")
    return bottom


def _recent(c: _Canvas, s: Showcase, top: int) -> int | None:
    if not s.options.recent or not s.recent:
        return None
    row_h = 76
    bottom = top + 116 + row_h * len(s.recent)
    c.card(PAD, top, WIDTH - PAD, bottom)
    x, right = PAD + 40, WIDTH - PAD - 40
    c.text((x, top + 40), "Đơn gần đây", _font("SemiBold", 30), INK)
    name_font, money_font, chip_font = _font("SemiBold", 28), _font("ExtraBold", 30), _font("SemiBold", 22)
    # nhãn trạng thái thẳng cột: chừa chỗ theo số tiền dài nhất
    money_w = max(c.width(f"+{format_vnd(r[1])}", money_font) for r in s.recent)
    chip_right = right - money_w - 24
    for i, (name, cashback, status, day) in enumerate(s.recent):
        y = top + 100 + row_h * i
        if i:
            c.box(x, y, right, y + 2, (244, 236, 231), radius=1)
        mid = y + row_h / 2
        c.text((x, mid), f"{name} · {day}", name_font, INK, "lm")
        amount = f"+{format_vnd(cashback)}"
        c.text((right, mid), amount, money_font, GREEN, "rm")
        chip_w = c.width(status, chip_font) + 32
        c.box(chip_right - chip_w, mid - 18, chip_right, mid + 18, (255, 238, 228), radius=18)
        c.text((chip_right - chip_w / 2, mid), status, chip_font, ORANGE, "mm")
    return bottom


def _sections(c: _Canvas, s: Showcase, header: int) -> int:
    """Vẽ các mục đang bật, mục tắt không chừa chỗ. Trả về y sau mục cuối."""
    y = header - 70  # thẻ đầu đè lên khối cam
    drawn = False
    for section in (_kpis, _money, _chart, _recent):
        bottom = section(c, s, y)
        if bottom is not None:
            y, drawn = bottom + 32, True
    return y if drawn else header + 10


def render_png(s: Showcase) -> bytes:
    header = 360
    probe = _Canvas(10)
    height = _sections(probe, s, header) + 90
    c = _Canvas(height)
    _header(c, s, header)
    y = _sections(c, s, header)
    c.text((WIDTH / 2, y + 30), NOTE, _font("Medium", 24), MUTED, "mm")
    out = io.BytesIO()
    c.image.resize((WIDTH, height), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out.getvalue()


# --- Màn chỉnh trong /admin -------------------------------------------------------------------------

NAV = ((("◀️ Về thống kê", "c:st:all"), ("◀️ Tổng quan", "c:menu:home")),)


def _mark(on: bool, label: str) -> str:
    return f"{'✅' if on else '⬜'} {label}"


def options_keyboard(o: Options) -> Keyboard:
    def pick(prefix: str, choices: tuple[int, ...], current: int, unit: str) -> tuple[tuple[str, str], ...]:
        return tuple((f"• {n}{unit}" if n == current else f"{n}{unit}", f"c:pb:{prefix}:{n}") for n in choices)

    def toggle(key: str) -> tuple[str, str]:
        return _mark(getattr(o, key), TOGGLES[key]), f"c:pb:t:{key}"

    return (
        (toggle("members"), toggle("links"), toggle("orders")),
        (toggle("money"),),
        (toggle("chart"), *pick("d", CHART_CHOICES, o.chart_days, " ngày")),
        (toggle("recent"), *pick("n", RECENT_CHOICES, o.recent_n, " đơn")),
        (toggle("hide_small"),),
        (("🖼 Tạo ảnh", CARD),),
        *NAV,
    )


def options_text(o: Options, notice: str = "") -> str:
    lines = ["🖼 <b>Ảnh đăng bài</b>", "", "Bấm để ẩn / hiện từng mục, xong bấm 🖼 Tạo ảnh. Bot nhớ lựa chọn cho lần sau.",
             "Dòng «Số tạm tính…» cuối ảnh luôn có."]
    if notice:
        lines += ["", notice]
    return "\n".join(lines)


class ShowcaseAdmin:
    def __init__(self, repo: TrackingRepository):
        self.repo = repo

    def options(self) -> Options:
        return Options.load(self.repo.get_state(STATE_KEY))

    def route(self, data: str, now: datetime) -> BotReply:
        o = self.options()
        if data == HOME:
            return BotReply(options_text(o), inline_keyboard=options_keyboard(o))
        if data == CARD:
            return self._card(o, now)
        found = _ACTION.fullmatch(data)
        if found is None:
            return BotReply("Nút này không còn hiệu lực.", inline_keyboard=options_keyboard(o))
        if found.group(1) == "t" and found.group(2) in TOGGLES:
            key = found.group(2)
            o = replace(o, **{key: not getattr(o, key)})
        elif found.group(3) == "d" and int(found.group(4)) in CHART_CHOICES:
            o = replace(o, chart=True, chart_days=int(found.group(4)))
        elif found.group(3) == "n" and int(found.group(4)) in RECENT_CHOICES:
            o = replace(o, recent=True, recent_n=int(found.group(4)))
        else:
            return BotReply("Nút này không còn hiệu lực.", inline_keyboard=options_keyboard(o))
        self.repo.set_state(STATE_KEY, o.dump())
        return BotReply(options_text(o), inline_keyboard=options_keyboard(o))

    def _card(self, o: Options, now: datetime) -> BotReply:
        with self.repo.connect() as conn:
            data = collect(conn, now, o)
        caption = f"Số liệu thật lúc {data.updated_at:%H:%M %d/%m/%Y} · tiền tạm tính"
        again = ((("🔁 Chỉnh mục hiển thị", HOME), ("🖼 Tạo lại", CARD)), *NAV)
        return BotReply(admin_text(data), photo=("so-lieu.png", render_png(data), caption), inline_keyboard=again)
