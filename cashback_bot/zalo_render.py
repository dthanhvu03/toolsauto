"""Chuyển câu trả lời của bot (HTML + nút Telegram) sang tin Zalo (PLAN-082).

Zalo không có nút và bỏ link trong thẻ <a> (đã thử thật 2026-10-24), nên:
- chữ gửi dạng thuần kèm `text_styles` (đậm / nghiêng / gạch chân / gạch ngang), không gửi HTML: tên sản phẩm có
  ký tự & < > không bị hiểu nhầm;
- <a href="URL">nhãn</a> thành «nhãn: URL»; nút Mua thành «🛒 Mua trên Shopee: URL» (URL trần, bấm được);
- nút u:* thành danh sách «1 · …»; khách gõ số thì tiến trình Zalo chạy đúng nút đó;
- tin dài cắt theo dòng, mỗi tin tối đa 2000 ký tự.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from cashback_bot.messages import BUY_BUTTON, BotReply

MAX_LEN = 2000
STYLE_CODES = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "ins": "u", "s": "s", "del": "s", "strike": "s"}
MENU_TITLE = "Gõ số để chọn:"

WELCOME = (
    "👋 <b>Chào bạn! Đây là bot tự động hoàn tiền mua sắm</b>, không phải người trả lời.\n"
    "Dán link sản phẩm Shopee, bot gửi lại link mua và số tiền hoàn dự kiến.\n"
    "Bot lưu link bạn gửi, đơn mua qua link đó và nội dung bạn gửi khi cần hỗ trợ, chỉ để tính hoàn tiền.\n"
    "Gõ <b>hd</b> để xem hướng dẫn, <b>menu</b> để mở trang chủ."
)
LINK_CARD = (
    "🔗 <b>Zalo đã biến link thành thẻ xem trước nên bot chưa đọc được</b>\n"
    "Bạn gửi lại theo một trong hai cách:\n"
    "1. Dán link, bấm dấu ✕ trên thẻ xem trước rồi mới gửi.\n"
    "2. Hoặc xoá phần https:// ở đầu link, ví dụ: s.shopee.vn/abc123"
)
GUIDE_TIP = (
    "\n\n📱 <b>Trên Zalo:</b> khi dán link, bấm dấu ✕ trên thẻ xem trước rồi mới gửi "
    "(hoặc xoá phần https:// ở đầu link)."
)
NON_TEXT = "🙏 Bot chỉ đọc được tin chữ. Bạn gửi link sản phẩm Shopee dạng chữ nhé. Gõ <b>hd</b> để xem hướng dẫn."
NUMBER_STALE = "Danh sách lựa chọn đã hết hạn hoặc không có số này. Gõ <b>menu</b> để mở trang chủ."

Style = tuple[int, int, str]


def _u16(text: str) -> int:
    """Zalo tính vị trí style theo đơn vị UTF-16 (emoji chiếm 2)."""
    return len(text.encode("utf-16-le")) // 2


@dataclass(frozen=True)
class ZaloMessage:
    text: str
    styles: tuple[Style, ...] = ()

    def payload_styles(self) -> list[dict]:
        return [{"start": start, "len": length, "st": [code]} for start, length, code in self.styles]


class _Flatten(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.pos = 0
        self.open: list[tuple[str, int]] = []
        self.styles: list[Style] = []
        self.href: str | None = None
        self.link_text: list[str] = []

    def emit(self, text: str) -> None:
        self.parts.append(text)
        self.pos += _u16(text)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in STYLE_CODES:
            self.open.append((tag, self.pos))
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self.href = href if href.startswith(("http://", "https://")) else None
            self.link_text = []
        elif tag == "br":
            self.emit("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in STYLE_CODES:
            for index in range(len(self.open) - 1, -1, -1):
                if self.open[index][0] == tag:
                    _tag, start = self.open.pop(index)
                    if self.pos > start:
                        self.styles.append((start, self.pos - start, STYLE_CODES[tag]))
                    break
        elif tag == "a" and self.href:
            if "".join(self.link_text).strip() != self.href:
                self.emit(f": {self.href}")
            self.href = None

    def handle_data(self, data: str) -> None:
        self.emit(data)
        if self.href is not None:
            self.link_text.append(data)


def flatten(html_text: str) -> tuple[str, list[Style]]:
    """HTML Telegram → (chữ thuần, style). Thẻ khác (code, pre, blockquote…) bỏ thẻ, giữ chữ."""
    parser = _Flatten()
    parser.feed(html_text or "")
    parser.close()
    return "".join(parser.parts), sorted(parser.styles)


def _clip(styles: list[Style], start: int, end: int) -> tuple[Style, ...]:
    out = []
    for s_start, s_len, code in styles:
        lo, hi = max(s_start, start), min(s_start + s_len, end)
        if hi > lo:
            out.append((lo - start, hi - lo, code))
    return tuple(out)


def _pieces(line: str) -> list[str]:
    """Một dòng dài hơn MAX_LEN (hiếm): cắt cứng theo ký tự, không cắt đôi emoji."""
    if _u16(line) <= MAX_LEN:
        return [line]
    out, current = [], ""
    for char in line:
        if _u16(current + char) > MAX_LEN:
            out.append(current)
            current = ""
        current += char
    return out + ([current] if current else [])


def split(text: str, styles: list[Style]) -> list[ZaloMessage]:
    """Cắt theo dòng thành các tin ≤ MAX_LEN; style cắt và dời theo từng tin."""
    chunks: list[tuple[int, str]] = []
    start, current = 0, ""
    for line in text.splitlines(keepends=True):
        for piece in _pieces(line):
            if current and _u16(current + piece) > MAX_LEN:
                chunks.append((start, current))
                start += _u16(current)
                current = ""
            current += piece
    if current:
        chunks.append((start, current))
    messages = []
    for offset, chunk in chunks:
        body = chunk.strip("\n")
        lead = _u16(chunk[: len(chunk) - len(chunk.lstrip("\n"))])
        if body.strip():
            messages.append(ZaloMessage(body, _clip(styles, offset + lead, offset + lead + _u16(body))))
    return messages


def render(reply: BotReply) -> tuple[list[ZaloMessage], tuple[str, ...]]:
    """BotReply → (các tin Zalo, callback theo số 1..n). Tin rỗng (chỉ toast) thì gửi nội dung toast."""
    text, styles = flatten(reply.text or reply.toast or "")

    def add(piece: str, bold: bool = False) -> None:
        nonlocal text
        if bold:
            styles.append((_u16(text), _u16(piece), "b"))
        text += piece

    if reply.button_url:
        add("\n\n")
        add(BUY_BUTTON, bold=True)
        add(f": {reply.button_url}")
    choices = [(label, data) for row in reply.inline_keyboard or () for label, data in row if data.startswith("u:")]
    if choices:
        add("\n\n")
        add(MENU_TITLE, bold=True)
        for number, (label, _data) in enumerate(choices, start=1):
            add(f"\n{number} · {label}")
    return split(text, sorted(styles)), tuple(data for _label, data in choices)
