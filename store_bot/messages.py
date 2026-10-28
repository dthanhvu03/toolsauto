"""Câu chữ bot bán hàng. Mọi chuỗi do người dùng/admin nhập đều đi qua esc() trước khi vào HTML."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime

from store_bot.db import ICT, ApiKey, Order, Product, StoreError, Topup, User

BOT_COMMANDS = [
    ("start", "🚀 Khởi động bot"),
    ("menu", "📍 Mở menu chính"),
    ("support", "☎️ Liên hệ hỗ trợ"),
    ("supportadmin", "🆘 Nhờ admin nhắn cho tôi (1 lần/ngày)"),
    ("huy", "Huỷ thao tác đang làm"),
]

# Bàn phím cố định dưới ô chat: khách không rành công nghệ chỉ cần bấm, không phải gõ lệnh.
MENU_SHOP = "🛒 Mua sản phẩm"
MENU_PROFILE = "👤 Hồ sơ"
MENU_ORDERS = "📦 Đơn hàng của tôi"
MENU_WALLET = "🎁 Ví"
MENU_SUPPORT = "☎️ Hỗ trợ"
MENU_ADMIN = "⚙️ Quản lý shop"
MENU_PLACEHOLDER = "📍 Vui lòng chọn menu:"
ADMIN_COMMANDS = BOT_COMMANDS + [("admin", "Quản lý shop")]

# Tin quá dài thì gửi hàng dạng file .txt (giới hạn tin Telegram 4096 ký tự).
INLINE_ITEMS_MAX_CHARS = 3500


# ---------- icon theo hãng ----------
# Tên sản phẩm chứa từ khoá → emoji thường (luôn hiện). Logo thật của hãng là emoji tuỳ chỉnh: admin gắn ở
# ⚙️ Quản lý shop → 🎨 Logo hãng (tài khoản tạo bot phải có Telegram Premium), lưu state `icon:<hãng>`,
# bot nạp vào CUSTOM_ICONS. Kênh và tin gửi hàng loạt luôn dùng emoji thường (Telegram không cho logo ở kênh).

@dataclass(frozen=True)
class Brand:
    key: str
    label: str
    keywords: tuple[str, ...]
    emoji: str


BRANDS = (
    Brand("chatgpt", "ChatGPT", ("chatgpt", "chat gpt", "openai", "gpt"), "🤖"),
    Brand("gemini", "Gemini", ("gemini",), "✨"),
    Brand("capcut", "CapCut", ("capcut",), "🎬"),
    Brand("canva", "Canva", ("canva",), "🎨"),
    Brand("office", "Microsoft 365", ("office", "microsoft", "copilot"), "💼"),
    Brand("duolingo", "Duolingo", ("duolingo",), "🦉"),
    Brand("muse", "Muse AI", ("muse",), "🧠"),
    Brand("claude", "Claude", ("claude",), "🔶"),
    Brand("grok", "Grok", ("grok",), "⚡"),
    Brand("perplexity", "Perplexity", ("perplexity",), "🔎"),
    Brand("cursor", "Cursor", ("cursor",), "💻"),
    Brand("youtube", "YouTube", ("youtube",), "▶️"),
    Brand("netflix", "Netflix", ("netflix",), "🍿"),
    Brand("spotify", "Spotify", ("spotify",), "🎧"),
    Brand("adobe", "Adobe", ("adobe", "photoshop"), "🅰️"),
    Brand("google", "Google One", ("google one", "google drive"), "☁️"),
)
DEFAULT_ICON = "📦"
CUSTOM_ICONS: dict[str, str] = {}  # key hãng → custom_emoji_id
CUSTOM_EMOJI_RE = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>')


def brand_of(name: str) -> Brand | None:
    lowered = name.lower()
    return next((b for b in BRANDS if any(k in lowered for k in b.keywords)), None)


def icon_id(name: str) -> str | None:
    """custom_emoji_id logo hãng cho nút bấm (None = chưa gắn logo)."""
    brand = brand_of(name)
    return CUSTOM_ICONS.get(brand.key) if brand else None


def icon(name: str, rich: bool = True) -> str:
    """Icon đặt trước tên sản phẩm trong tin HTML. rich=False: chỉ emoji thường (kênh, gửi hàng loạt)."""
    brand = brand_of(name)
    if brand is None:
        return DEFAULT_ICON
    custom = CUSTOM_ICONS.get(brand.key) if rich else None
    return f'<tg-emoji emoji-id="{custom}">{brand.emoji}</tg-emoji>' if custom else brand.emoji


def button_icon(name: str) -> str:
    """Tiền tố chữ trên nút: nút có logo thật (icon_custom_emoji_id) thì không lặp emoji."""
    return "" if icon_id(name) else icon(name, rich=False) + " "


def esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + "đ"


def percent(bps: int) -> str:
    value = bps / 100
    return (f"{value:.2f}".rstrip("0").rstrip(".")) + "%"


def local_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(ICT).strftime("%H:%M %d/%m/%Y")
    except ValueError:
        return iso


_AMOUNT_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(k|nghìn|nghin|tr|triệu|trieu|m)?$")


def parse_amount(text: str) -> int | None:
    """100000 · 100.000 · 100k · 1tr · 1.5tr → số đồng. Sai định dạng trả None."""
    raw = (text or "").strip().lower().replace(" ", "").removesuffix("đ").removesuffix("vnd")
    match = _AMOUNT_RE.match(raw)
    if not match:
        return None
    number, unit = match.groups()
    if unit is None:
        digits = number.replace(".", "").replace(",", "")
        return int(digits) if digits.isdigit() else None
    value = float(number.replace(",", "."))
    multiplier = 1_000 if unit in {"k", "nghìn", "nghin"} else 1_000_000
    return int(round(value * multiplier))


def error_text(exc: StoreError) -> str:
    info = exc.info
    return {
        "product_not_found": "Sản phẩm không còn tồn tại.",
        "product_inactive": "Sản phẩm đang tạm ngừng bán.",
        "product_blocked": "Sản phẩm này không mở cho khóa của bạn.",
        "out_of_stock": f"Không đủ hàng: chỉ còn {info.get('available', 0)}.",
        "insufficient_balance": (
            f"Số dư không đủ: cần {vnd(info.get('need', 0))}, bạn có {vnd(info.get('balance', 0))}."
        ),
        "bad_quantity": "Số lượng không hợp lệ.",
        "bad_price": "Giá phải lớn hơn 0.",
        "bad_amount": "Số tiền không hợp lệ.",
        "user_not_found": "Không tìm thấy người này. Họ cần bấm /start bot trước.",
        "topup_not_found": "Không tìm thấy yêu cầu nạp.",
    }.get(exc.code, f"Lỗi: {exc.code}")


# ---------- khách ----------

def home(shop_name: str, user: User) -> str:
    return (
        f"🏪 <b>{esc(shop_name)}</b>\n\n"
        f"Xin chào {esc(user.first_name or user.label)}!\n"
        f"💼 Số dư: <b>{vnd(user.balance)}</b>\n\n"
        "Chọn 🛒 Mua hàng để xem sản phẩm. Thanh toán trừ thẳng vào số dư, hàng giao ngay sau khi mua."
    )


def shop_list(products: list[Product]) -> str:
    if not products:
        return "🛒 Shop chưa có sản phẩm nào đang bán."
    return "🛒 <b>Sản phẩm</b>\n\nChọn một sản phẩm để xem và mua:"


def product_button(product: Product) -> str:
    stock = f"còn {product.stock}" if product.stock else "hết hàng"
    return f"{button_icon(product.name)}{product.name} · {vnd(product.price)} · {stock}"


def product_detail(product: Product, balance: int) -> str:
    lines = [f"{icon(product.name)} <b>{esc(product.name)}</b>"]
    if product.description:
        lines += ["", esc(product.description)]
    lines += [
        "",
        f"💰 Giá: <b>{vnd(product.price)}</b>",
        f"🗄️ Còn: <b>{product.stock}</b>",
        f"💼 Số dư của bạn: {vnd(balance)}",
    ]
    if not product.stock:
        lines += ["", "Hiện đã hết hàng. Theo dõi kênh để biết khi có hàng mới."]
    else:
        lines += ["", "Bấm số lượng bên dưới hoặc gõ số lượng muốn mua:"]
    return "\n".join(lines)


def confirm_buy(product: Product, quantity: int, balance: int) -> str:
    total = product.price * quantity
    after = balance - total
    if after >= 0:
        tail = f"Trừ vào ví. Số dư sau khi mua: {vnd(after)}"
    elif balance > 0:
        tail = f"Ví có {vnd(balance)}, cần trả thêm <b>{vnd(-after)}</b>. Bấm 📱 Thanh toán QR bên dưới."
    else:
        tail = "Bấm 📱 Thanh toán QR bên dưới, quét mã bằng app ngân hàng là xong."
    return (
        "🧾 <b>Xác nhận mua</b>\n\n"
        f"{icon(product.name)} {esc(product.name)}\n"
        f"Số lượng: <b>{quantity}</b> × {vnd(product.price)}\n"
        f"Tổng: <b>{vnd(total)}</b>\n\n{tail}"
    )


def ask_quantity(product: Product, max_quantity: int) -> str:
    return (f"✍️ Gõ số lượng muốn mua <b>{esc(product.name)}</b> "
            f"(1–{min(product.stock, max_quantity)}). Gõ /huy để thôi.")


def order_done(order: Order) -> str:
    head = "♻️ Đơn này đã mua trước đó" if order.replayed else "✅ <b>Mua thành công</b>"
    partial = ""
    if order.refunded:
        partial = (f"⚠️ Nguồn chỉ giao {len(order.items)}/{order.quantity} món, "
                   f"đã hoàn {vnd(order.refunded)} cho phần thiếu.\n")
    return (
        f"{head}\n\n"
        f"🧾 Đơn #{order.id} · {local_time(order.created_at)}\n"
        f"{icon(order.product_name)} {esc(order.product_name)} × {len(order.items) if order.refunded else order.quantity}\n"
        f"💸 Đã trừ: {vnd(order.total - order.refunded)}\n"
        f"{partial}"
        f"💼 Số dư còn: {vnd(order.balance_after or 0)}\n\n"
        "Hàng ở tin bên dưới. Xem lại bất cứ lúc nào ở 🧾 Đơn hàng."
    )


def order_waiting(order: Order) -> str:
    return (
        f"⏳ <b>Đã nhận đơn #{order.id}</b>, đang lấy hàng…\n\n"
        f"{icon(order.product_name)} {esc(order.product_name)} × {order.quantity} · {vnd(order.total)}\n\n"
        "Thường chỉ vài giây; nguồn chậm thì 1–2 phút. Hàng về bot gửi ngay, không cần bấm mua lại."
    )


def order_failed(order: Order) -> str:
    return (
        f"❌ <b>Đơn #{order.id} chưa lấy được hàng</b>\n\n"
        f"{icon(order.product_name)} {esc(order.product_name)} × {order.quantity}\n"
        f"↩️ Đã hoàn {vnd(order.refunded)} vào số dư.\n"
        f"💼 Số dư: {vnd(order.balance_after or 0)}\n\n"
        "Món này đang tạm thiếu hàng, bạn thử lại sau ít phút hoặc chọn món khác."
    )


def order_items(order: Order) -> str:
    body = "\n".join(f"<code>{esc(item)}</code>" for item in order.items)
    return f"{icon(order.product_name)} <b>Đơn #{order.id}</b> · {esc(order.product_name)}\n\n{body}"


def items_fit_inline(order: Order) -> bool:
    return len(order_items(order)) <= INLINE_ITEMS_MAX_CHARS


def orders_list(orders: list[Order]) -> str:
    if not orders:
        return "🧾 Bạn chưa có đơn nào."
    return "🧾 <b>Đơn hàng gần đây</b>\n\nBấm một đơn để nhận lại hàng:"


def order_button(order: Order) -> str:
    return f"{button_icon(order.product_name)}#{order.id} · {order.product_name} × {order.quantity} · {vnd(order.total)}"


def account(user: User, key: ApiKey | None, api_url: str) -> str:
    lines = [
        "👤 <b>Tài khoản</b>\n",
        f"ID: <code>{user.user_id}</code>",
        f"Tên: {esc(user.label)}",
        f"💼 Số dư: <b>{vnd(user.balance)}</b>",
        f"🔔 Báo hàng mới: {'Tắt' if user.notify_off else 'Bật'}",
    ]
    if key:
        lines += ["", f"🔑 Khóa API: <code>{esc(key.prefix)}…</code> · giảm {percent(key.discount_bps)}"]
        if api_url:
            lines.append(f"Địa chỉ API: {esc(api_url)}")
    return "\n".join(lines)


def topup_menu(min_amount: int) -> str:
    return (f"💰 <b>Nạp tiền</b>\n\nBấm số tiền bên dưới hoặc gõ số tiền muốn nạp, "
            f"ví dụ <code>150k</code> (tối thiểu {vnd(min_amount)}):")


def ask_topup_amount(min_amount: int) -> str:
    return f"✍️ Gõ số tiền muốn nạp, ví dụ <code>150k</code> hoặc <code>150000</code> (tối thiểu {vnd(min_amount)})."


def topup_instructions(topup: Topup, bank_name: str, account_no: str, owner: str, auto: bool,
                       product_name: str | None = None) -> str:
    if product_name:
        head = f"📱 <b>Thanh toán {vnd(topup.amount)}</b>\n📦 {esc(product_name)} × {topup.intent_quantity}"
        when = ("Tiền vào là bot tự gửi hàng trong khoảng 1 phút." if auto
                else "Shop xác nhận tiền xong là bot tự gửi hàng cho bạn, không cần bấm gì thêm.")
    else:
        head = f"💳 <b>Nạp {vnd(topup.amount)}</b>"
        when = "Tiền vào là bot tự cộng trong khoảng 1 phút." if auto else "Admin kiểm tra và cộng tiền sớm nhất có thể."
    bank_line = f"🏦 {esc(bank_name)}\n" if bank_name else ""
    return (
        "Quét mã QR bằng app ngân hàng (app tự điền sẵn mọi thứ), hoặc chuyển khoản tay:\n\n"
        f"{head}\n\n"
        f"{bank_line}"
        f"Số tài khoản: <code>{esc(account_no)}</code>\n"
        f"Chủ tài khoản: {esc(owner)}\n"
        f"Số tiền: <code>{topup.amount}</code>\n"
        f"Nội dung: <code>{topup.code}</code>\n\n"
        f"⚠️ Ghi đúng nội dung <b>{topup.code}</b>, sai nội dung bot không nhận ra được.\n"
        f"{when}"
    )


TOPUP_UNAVAILABLE = "💰 Shop chưa cài tài khoản nhận tiền. Nhắn admin để nạp."


def topup_credited(amount: int, balance: int) -> str:
    return f"✅ Đã cộng <b>{vnd(amount)}</b> vào tài khoản.\n💼 Số dư: <b>{vnd(balance)}</b>"


def balance_adjusted(delta: int, balance: int, note: str) -> str:
    verb = "cộng" if delta > 0 else "trừ"
    reason = f"\nLý do: {esc(note)}" if note else ""
    return f"💼 Admin đã {verb} {vnd(abs(delta))}.{reason}\nSố dư: <b>{vnd(balance)}</b>"


# ---------- kênh ----------

def restock_announcement(product: Product, added: int) -> str:
    return (
        "🆕 <b>HÀNG MỚI VỀ!</b>\n\n"
        f"{icon(product.name, rich=False)} <b>{esc(product.name)}</b>\n"
        f"➕ Thêm: <b>{added}</b>\n"
        f"🗄️ Tồn kho hiện tại: <b>{product.stock}</b>\n"
        f"💰 Giá: <b>{vnd(product.price)}</b>"
    )


# ---------- admin ----------

def admin_home(stats: dict[str, int], upstream_balance: int | None = None) -> str:
    pending = f"\n💳 Nạp chờ duyệt: <b>{stats['pending_topups']}</b>" if stats["pending_topups"] else ""
    upstream = f"\n🐱 Ví FatCat: <b>{vnd(upstream_balance)}</b>" if upstream_balance is not None else ""
    return (
        "⚙️ <b>Quản lý shop</b>\n\n"
        f"Hôm nay: {stats['orders_today']} đơn · doanh thu {vnd(stats['revenue_today'])} · "
        f"lãi {vnd(stats['profit_today'])}\n"
        f"Hàng tự nhập trong kho: {stats['stock']}"
        f"{upstream}{pending}"
    )


def admin_stats(stats: dict[str, int], upstream_balance: int | None = None) -> str:
    blocks = []
    for key, title in (("today", "Hôm nay"), ("7d", "7 ngày"), ("all", "Từ đầu")):
        refunded = stats[f"refunded_{key}"]
        blocks.append(
            f"<b>{title}</b>\n"
            f"💰 Khách nạp vào: {vnd(stats[f'topup_{key}'])}\n"
            f"🛒 Bán: {stats[f'orders_{key}']} đơn · doanh thu {vnd(stats[f'revenue_{key}'])}\n"
            f"🐱 Giá vốn FatCat: {vnd(stats[f'cost_{key}'])}\n"
            f"📈 Lãi: <b>{vnd(stats[f'profit_{key}'])}</b>"
            + (f"\n↩️ Đã hoàn khách: {vnd(refunded)}" if refunded else "")
        )
    wallet = f"\n🐱 Ví FatCat còn: {vnd(upstream_balance)}" if upstream_balance is not None else ""
    waiting = f"\n⏳ Đơn đang chờ FatCat: {stats['pending_orders']}" if stats["pending_orders"] else ""
    return (
        "📊 <b>Thống kê dòng tiền</b>\n\n"
        + "\n\n".join(blocks)
        + "\n\n"
        f"👥 Khách: {stats['users']} (đã mua: {stats['buyers']})\n"
        f"💼 Số dư khách đang giữ: {vnd(stats['balances'])}"
        f"{wallet}{waiting}"
    )


_LEDGER_KIND = {"topup": "💰 Nạp", "order": "🛒 Mua", "refund": "↩️ Hoàn", "adjust": "💵 Admin"}


def admin_ledger(rows: list[dict]) -> str:
    if not rows:
        return "💸 <b>Giao dịch gần đây</b>\n\nChưa có giao dịch nào."
    lines = []
    for row in rows:
        who = f"@{row['username']}" if row["username"] else (row["first_name"] or str(row["user_id"]))
        sign = "+" if row["delta"] > 0 else "−"
        if row["kind"] == "topup":
            detail = "mã " + (row["ref"] or "").removeprefix("topup:")
        else:
            detail = row["note"] or row["ref"] or ""
        lines.append(
            f"{local_time(row['created_at'])[:11]} · {_LEDGER_KIND.get(row['kind'], row['kind'])} "
            f"<b>{sign}{vnd(abs(row['delta']))}</b> · {esc(who)}\n"
            f"   {esc(detail)[:60]} · còn {vnd(row['balance_after'])}"
        )
    return "💸 <b>Giao dịch gần đây</b>\n\n" + "\n".join(lines)


def admin_product(product: Product) -> str:
    if not product.available:
        state = "⛔ FatCat đã ngừng bán món này cho khóa của bạn"
    else:
        state = "🟢 Đang bán" if product.active else "⏸ Đang ẩn"
    desc = f"\n{esc(product.description)}\n" if product.description else ""
    source = ""
    if product.upstream_id is not None:
        margin = product.price - (product.cost or 0)
        source = (f"🐱 Nguồn FatCat #{product.upstream_id} · giá vốn {vnd(product.cost or 0)} · "
                  f"lãi {vnd(margin)}/món\nGiá, tên, tồn kho tự cập nhật theo FatCat.\n")
    return (
        f"{icon(product.name)} <b>{esc(product.name)}</b> (#{product.id})\n{desc}\n"
        f"💰 Giá bán: {vnd(product.price)}\n"
        f"🗄️ Tồn kho: {product.stock}\n"
        f"{source}"
        f"{state}"
    )


def admin_product_button(product: Product) -> str:
    mark = "" if product.on_sale else "⏸ "
    mark += "🐱 " if product.upstream_id is not None else ""
    return f"{mark}{button_icon(product.name)}{product.name} · {vnd(product.price)} · {product.stock}"


ASK_NEW_PRODUCT = (
    "➕ Gửi sản phẩm mới theo mẫu:\n<code>Tên | Giá | Mô tả</code>\n\n"
    "Ví dụ: <code>Link Gemini Pro 18 tháng | 19999 | Dùng trong 1 tiếng</code>\n"
    "Mô tả có thể bỏ trống. Gõ /huy để thôi."
)
ASK_EDIT_PRODUCT = "✏️ Gửi tên và mô tả mới:\n<code>Tên | Mô tả</code>\nGõ /huy để thôi."
ASK_PRICE = "💰 Gõ giá mới (ví dụ <code>155000</code> hoặc <code>155k</code>). Gõ /huy để thôi."
ASK_GRANT = "🔑 Gửi @username hoặc ID Telegram của người được cấp khóa (họ phải bấm /start bot trước)."
ASK_ADJUST = (
    "💵 Gửi theo mẫu:\n<code>@username số_tiền lý do</code>\n\n"
    "Cộng: <code>@abc 50000 hoàn đơn 12</code>\nTrừ: <code>@abc -20000 cộng nhầm</code>"
)
ASK_DISCOUNT = "% Gõ mức giảm mới, ví dụ <code>2</code> hoặc <code>2.5</code> (đơn vị %)."

ADMIN_ICONS = (
    "🎨 <b>Logo hãng</b>\n\n"
    "Bot tự gắn icon theo tên sản phẩm (CapCut 🎬, ChatGPT 🤖, Gemini ✨…). Muốn hiện <b>logo thật</b> của hãng: "
    "bấm tên hãng rồi gửi emoji logo đó (emoji động/tuỳ chỉnh trong bộ emoji Telegram).\n\n"
    "Cần: tài khoản tạo bot có <b>Telegram Premium</b>. Logo hiện trong bot; kênh vẫn dùng icon thường.\n"
    "✅ = đã gắn logo."
)


def admin_icon_button(brand: Brand) -> str:
    return f"{'✅' if brand.key in CUSTOM_ICONS else '➖'} {brand.emoji} {brand.label}"


def ask_icon(brand: Brand) -> str:
    return (
        f"🎨 <b>Logo {esc(brand.label)}</b>\n\n"
        f"Gửi vào đây <b>một emoji logo {esc(brand.label)}</b> (mở bảng emoji → bộ emoji có logo hãng → bấm chọn → gửi).\n"
        "Mẹo: thấy logo đó trong tin của bot/kênh khác thì bấm giữ vào emoji để thêm bộ đó.\n"
        "Gõ /huy để thôi."
    )


ICON_NOT_FOUND = "Tin này không có emoji tuỳ chỉnh nào. Gửi đúng emoji logo (cần Telegram Premium), hoặc gõ /huy."


def icon_saved(brand: Brand) -> str:
    return (
        f"✅ Đã gắn logo {icon(brand.label)} <b>{esc(brand.label)}</b>.\n\n"
        "Nhìn nút bên dưới: thấy logo thật là xong. Nếu chỉ thấy emoji thường thì tài khoản tạo bot "
        "chưa có Telegram Premium (bấm 🗑 Bỏ logo để quay về icon thường)."
    )


def ask_stock(product: Product) -> str:
    return (
        f"➕ <b>Nhập kho: {esc(product.name)}</b>\n\n"
        "Dán hàng vào đây, <b>mỗi dòng một món</b>. Gửi được nhiều tin liền nhau hoặc file .txt.\n"
        "Món trùng với hàng đã có sẽ tự bỏ qua. Nhập xong bấm nút bên dưới."
    )


def stock_progress(product: Product, added: int, dup: int, session_added: int) -> str:
    dup_text = f" (bỏ {dup} món trùng)" if dup else ""
    return (
        f"📥 Đã thêm <b>{added}</b>{dup_text}.\n"
        f"Lượt nhập này: {session_added} · Tồn kho: <b>{product.stock}</b>\n\n"
        "Dán tiếp hoặc bấm Xong."
    )


def key_granted(key: ApiKey, raw: str, api_url: str) -> str:
    url = esc(api_url) if api_url else "(chưa cài STORE_API_PUBLIC_URL)"
    return (
        f"✅ Đã cấp khóa cho {esc(key.user_label)}\n\n"
        f"<code>{esc(raw)}</code>\n\n"
        "⚠️ Gửi ngay cho họ và lưu lại: bot không lưu khóa thô nên sau này không xem lại được, "
        "mất thì phải cấp lại khóa mới.\n\n"
        f"Địa chỉ API: {url}\n\n"
        f"Khóa bán được ngay mọi sản phẩm đang bán, giảm {percent(key.discount_bps)}. "
        "Muốn chặn họ bán sản phẩm nào thì vào 📦 Sản phẩm được bán tích chặn."
    )


def admin_key(key: ApiKey, blocked: int) -> str:
    used = local_time(key.last_used_at) if key.last_used_at else "chưa dùng"
    return (
        f"🔑 <b>{esc(key.user_label)}</b>\n\n"
        f"Khóa: <code>{esc(key.prefix)}…</code>\n"
        f"Giảm: {percent(key.discount_bps)}\n"
        f"Sản phẩm bị chặn: {blocked}\n"
        f"Cấp lúc: {local_time(key.created_at)}\n"
        f"Dùng gần nhất: {used}"
    )


def admin_key_button(key: ApiKey, blocked: int) -> str:
    tail = f" · chặn {blocked}" if blocked else ""
    return f"{key.user_label} · giảm {percent(key.discount_bps)}{tail}"


def admin_key_blocks(key: ApiKey) -> str:
    return (
        f"📦 <b>Sản phẩm được bán · {esc(key.user_label)}</b>\n\n"
        "✅ được bán · 🚫 bị chặn. Bấm để đổi."
    )


def admin_topup(topup: Topup, user: User | None, auto: bool, product_name: str | None = None) -> str:
    who = esc(user.label) if user else str(topup.user_id)
    hint = "\nSePay sẽ tự cộng khi tiền vào; chỉ bấm khi đã tự kiểm tra." if auto else ""
    purpose = (f"Để mua: {esc(product_name)} × {topup.intent_quantity} (bấm ✅ là bot tự mua + giao hàng)\n"
               if product_name else "")
    return (
        f"💳 <b>Yêu cầu nạp #{topup.id}</b>\n\n"
        f"Khách: {who} (<code>{topup.user_id}</code>)\n"
        f"Số tiền: <b>{vnd(topup.amount)}</b>\n"
        f"{purpose}"
        f"Nội dung: <code>{topup.code}</code>\n"
        f"Lúc: {local_time(topup.created_at)}{hint}"
    )


def admin_topup_button(topup: Topup) -> str:
    return f"#{topup.id} · {vnd(topup.amount)} · {topup.code}"


def admin_sale(order: Order, user: User | None) -> str:
    who = esc(user.label) if user else str(order.user_id)
    via = " qua API" if order.source == "api" else ""
    return f"🛒 {who} mua {esc(order.product_name)} × {order.quantity} · {vnd(order.total)}{via}"


def admin_sold_out(product: Product) -> str:
    return f"⚠️ <b>{esc(product.name)}</b> vừa hết hàng."


def admin_unmatched_transfer(amount: int, content: str) -> str:
    return f"❓ Tiền vào {vnd(amount)} không khớp mã nạp nào.\nNội dung: <code>{esc(content)}</code>"


def admin_upstream_rejected(order: Order, status_code: int | None, message: str) -> str:
    hint = ""
    if status_code == 402:
        hint = "\n\n👉 Ví FatCat không đủ tiền: nạp thêm ở bot FatCat."
    elif status_code == 401:
        hint = "\n\n👉 Khóa FatCat sai hoặc bị tắt: kiểm tra FATCAT_API_KEY."
    return (
        f"⚠️ FatCat từ chối đơn #{order.id} ({status_code}): {esc(message)}\n"
        f"📦 {esc(order.product_name)} × {order.quantity} · đã hoàn {vnd(order.refunded)} cho khách.{hint}"
    )


def admin_upstream_stuck(order: Order) -> str:
    return (
        f"⏳ Đơn #{order.id} ({esc(order.product_name)} × {order.quantity}) chờ FatCat đã lâu.\n"
        "Bot vẫn gọi lại cùng mã đơn (không bị trừ tiền hai lần). Nếu kéo dài, nhắn hỗ trợ FatCat."
    )


def admin_sync_result(count: int, balance: int | None) -> str:
    wallet = f" · ví FatCat {vnd(balance)}" if balance is not None else ""
    return f"🔄 Đã đồng bộ {count} món từ FatCat{wallet}."


def welcome(shop_name: str, auto: bool) -> str:
    step4 = "Tiền vào là bot tự gửi hàng ngay." if auto else "Shop xác nhận tiền xong là bot tự gửi hàng."
    return (
        f"Chào mừng đến với <b>{esc(shop_name)}</b>!\n\n"
        "<b>Hướng dẫn nhanh</b>\n"
        f"1. Bấm nút \"{MENU_SHOP}\".\n"
        "2. Chọn sản phẩm và số lượng.\n"
        "3. Bấm 📱 Thanh toán QR, quét mã bằng app ngân hàng.\n"
        f"4. {step4}\n\n"
        "Nạp sẵn vào 🎁 Ví thì lần sau bấm mua là nhận hàng ngay."
    )


def wallet(user: User) -> str:
    return (
        "🎁 <b>Ví của bạn</b>\n\n"
        f"💰 Số dư: <b>{vnd(user.balance)}</b>\n\n"
        "Nạp tiền để thanh toán nhanh hơn: bấm mua là trừ ví, nhận hàng ngay."
    )


def support(telegram: str, zalo: str) -> str:
    lines = ["☎️ <b>Hỗ trợ khách hàng</b>", ""]
    if telegram:
        lines.append(f"Telegram: {esc(telegram)}")
    if zalo:
        lines.append(f"Zalo: {esc(zalo)}")
    if not telegram and not zalo:
        lines.append("Nhắn admin shop để được hỗ trợ.")
    lines += ["", "Vui lòng gửi kèm <b>mã đơn hàng</b> (ví dụ #12, xem ở 📦 Đơn hàng của tôi) để được hỗ trợ nhanh nhất."]
    return "\n".join(lines)


NOTIFY_OFF_DONE = "Đã tắt báo hàng mới. Bật lại ở 👤 Hồ sơ."
CALLBACK_DONE = ("✅ Đã báo admin. Admin sẽ nhắn bạn qua Telegram sớm nhất có thể.\n"
                 "Mỗi ngày nhờ được 1 lần; cần gấp thì nhắn thẳng liên hệ ở ☎️ Hỗ trợ.")
CALLBACK_ALREADY = "Hôm nay bạn đã nhờ admin rồi, admin sẽ nhắn bạn sớm. Cần gấp thì nhắn thẳng liên hệ ở ☎️ Hỗ trợ."


def admin_callback_request(user: User) -> str:
    if user.username:
        link = f'<a href="https://t.me/{esc(user.username)}">@{esc(user.username)}</a>'
    else:
        link = f'<a href="tg://user?id={user.user_id}">{esc(user.first_name or user.user_id)}</a>'
    return (f"🆘 {link} (<code>{user.user_id}</code>) nhờ admin nhắn tin hỗ trợ.\n"
            f"Số dư khách: {vnd(user.balance)}. Bấm tên để mở chat.")


def admin_broadcast_done(product: Product, sent: int, blocked: int) -> str:
    tail = f", {blocked} khách đã chặn bot" if blocked else ""
    return f"📣 Đã báo hàng mới <b>{esc(product.name)}</b> cho {sent} khách{tail}."
