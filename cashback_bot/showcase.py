"""/admin → 🗓 Thống kê → 🖼 Ảnh đăng bài: ảnh số liệu thật để chủ bot đăng bài lấy uy tín. Chỉ đọc DB.

Chủ bot chọn (2026-10-28): ảnh kèm bài viết soạn sẵn; tiền ghi «tạm tính»; có đơn gần đây, tên khách che.
- Bot chưa chi trả lần nào thì không viết như đã trả. Dòng «Đã chi trả» chỉ hiện khi có lượt rút đã trả.
- Tên khách chỉ còn chữ đầu và chữ cuối; không có tên thì ghi kênh (Khách Telegram / Khách Zalo).
Font Be Vietnam Pro (OFL, cashback_bot/assets/fonts). Callback: c:pb:card.
"""

from __future__ import annotations

import html
import io
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from cashback_bot.messages import buyer_name
from cashback_bot.money import format_vnd
from cashback_bot.payouts import PAID_STATES
from cashback_bot.wallet import CLAWBACK_TAG

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
CARD = "c:pb:card"
CHART_DAYS = 7
RECENT = 4
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
    recent: list[tuple[str, str, int, str, str]]  # (tên che, món, tiền hoàn, trạng thái, ngày)
    updated_at: datetime

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


def collect(conn: sqlite3.Connection, now: datetime) -> Showcase:
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
    for back in range(CHART_DAYS - 1, -1, -1):
        day = today - timedelta(days=back)
        key = day.isoformat()
        label = "Hôm nay" if back == 0 else day.strftime("%d/%m")
        daily.append((label, link_days.get(key, 0), len(order_days.get(key, ()))))

    recent = []
    rows = conn.execute(
        """
        SELECT e.telegram_user_id, e.item_name, e.cashback_vnd, e.status, e.purchase_time,
               COALESCE((SELECT display_name FROM channel_identities c WHERE c.internal_user_id = e.telegram_user_id
                         ORDER BY c.created_at LIMIT 1),
                        (SELECT username FROM telegram_users t WHERE t.telegram_user_id = e.telegram_user_id)) AS name
        FROM cashback_entries e
        WHERE e.status IN ('pending', 'holding', 'available') AND instr(e.conversion_id, ?) = 0 AND e.cashback_vnd > 0
        ORDER BY e.purchase_time DESC LIMIT ?
        """,
        (CLAWBACK_TAG, RECENT),
    ).fetchall()
    for user, item, cashback, status, stamp, name in rows:
        day = _ict_day(stamp)
        recent.append((mask_name(name, int(user)), buyer_name(item or "Sản phẩm"), int(cashback),
                       STATUS_LABELS[status], datetime.fromisoformat(day).strftime("%d/%m") if day else ""))
    return Showcase(
        members=members, links=len(links), orders=len({o[0] for o in orders}),
        buyers=len({o[1] for o in orders if o[1] is not None}), days_running=days_running,
        pending_vnd=int(money[0]), holding_vnd=int(money[1]), available_vnd=int(money[2]),
        paid_vnd=int(paid[0]), paid_count=int(paid[1]), daily=daily, recent=recent, updated_at=now.astimezone(ICT),
    )


def post_text(s: Showcase) -> str:
    """Bài viết soạn sẵn để chủ bot sao chép, đi kèm ảnh. Không hứa số, không viết như đã trả khi chưa trả."""
    lines = [
        f"🛍 Bot hoàn tiền Shopee & TikTok Shop: số liệu thật sau {s.days_running} ngày chạy",
        "",
        f"👥 {s.members} thành viên · 🔗 {s.links} link đã tạo · 🛒 {s.orders} đơn ghi nhận",
        f"💰 {format_vnd(s.recorded_vnd)} hoàn tiền đã ghi nhận (tạm tính, chờ sàn duyệt)",
    ]
    if s.paid_count:
        lines.append(f"✅ Đã chi trả {format_vnd(s.paid_vnd)} qua {s.paid_count} lượt rút")
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


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width * SCALE:
        return text
    while text and draw.textlength(text + "…", font=font) > width * SCALE:
        text = text[:-1]
    return text.rstrip(" ,.-") + "…"


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


def _kpis(c: _Canvas, s: Showcase, top: int) -> int:
    items = [(s.members, "Thành viên"), (s.links, "Link đã tạo"), (s.orders, "Đơn ghi nhận")]
    gap = 24
    width = (WIDTH - 2 * PAD - 2 * gap) / 3
    for i, (value, label) in enumerate(items):
        x0 = PAD + i * (width + gap)
        c.card(x0, top, x0 + width, top + 190)
        c.text((x0 + width / 2, top + 82), f"{value:,}".replace(",", "."), _font("ExtraBold", 76), ORANGE, "mm")
        c.text((x0 + width / 2, top + 150), label, _font("Medium", 28), MUTED, "mm")
    return top + 190


def _money(c: _Canvas, s: Showcase, top: int) -> int:
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


def _chart(c: _Canvas, s: Showcase, top: int) -> int:
    bottom = top + 380
    c.card(PAD, top, WIDTH - PAD, bottom)
    x = PAD + 40
    c.text((x, top + 40), f"{CHART_DAYS} ngày gần đây", _font("SemiBold", 30), INK)
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
    for i, (label, links, orders) in enumerate(s.daily):
        mid = x + slot * i + slot / 2
        for offset, value, color in ((-17, links, PEACH), (17, orders, ORANGE)):
            h = max(height * value / peak, 6)
            c.box(mid + offset - 14, base - h, mid + offset + 14, base, color, radius=10)
            if value:
                c.text((mid + offset, base - h - 18), str(value), _font("SemiBold", 22), INK, "mm")
        c.text((mid, base + 32), label, font, INK if label == "Hôm nay" else MUTED, "mm")
    return bottom


def _recent(c: _Canvas, s: Showcase, top: int) -> int:
    if not s.recent:
        return top - 32
    row_h = 92
    bottom = top + 116 + row_h * len(s.recent)
    c.card(PAD, top, WIDTH - PAD, bottom)
    x, right = PAD + 40, WIDTH - PAD - 40
    c.text((x, top + 40), "Đơn gần đây", _font("SemiBold", 30), INK)
    name_font, item_font, money_font, chip_font = (
        _font("SemiBold", 28), _font("Regular", 24), _font("ExtraBold", 30), _font("SemiBold", 20))
    for i, (name, item, cashback, status, day) in enumerate(s.recent):
        y = top + 100 + row_h * i
        if i:
            c.box(x, y, right, y + 2, (244, 236, 231), radius=1)
        amount = f"+{format_vnd(cashback)}"
        c.text((right, y + 32), amount, money_font, GREEN, "rm")
        chip_w = c.width(status, chip_font) + 28
        c.box(right - chip_w, y + 52, right, y + 80, (255, 238, 228), radius=14)
        c.text((right - chip_w / 2, y + 66), status, chip_font, ORANGE, "mm")
        text_w = int(right - x - max(c.width(amount, money_font), chip_w) - 30)
        c.text((x, y + 32), f"{name} · {day}", name_font, INK, "lm")
        c.text((x, y + 66), _fit(c.draw, item, item_font, text_w), item_font, MUTED, "lm")
    return bottom


def render_png(s: Showcase) -> bytes:
    header = 360
    probe = _Canvas(10)
    sections = [_kpis, _money, _chart, _recent]
    y = header - 70
    for section in sections:
        y = section(probe, s, y) + 32
    height = y + 90
    c = _Canvas(height)
    _header(c, s, header)
    y = header - 70
    for section in sections:
        y = section(c, s, y) + 32
    c.text((WIDTH / 2, y + 30), NOTE, _font("Medium", 24), MUTED, "mm")
    out = io.BytesIO()
    c.image.resize((WIDTH, height), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out.getvalue()
