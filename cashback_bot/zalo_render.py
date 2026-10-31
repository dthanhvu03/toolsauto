"""Chuyển câu trả lời của bot (HTML + nút Telegram) sang tin Zalo (PLAN-082).

Zalo không có nút và bỏ link trong thẻ <a> (đã thử thật 2026-10-24), nên:
- chữ gửi dạng thuần kèm `text_styles` (đậm / nghiêng / gạch chân / gạch ngang), không gửi HTML: tên sản phẩm có
  ký tự & < > không bị hiểu nhầm;
- <a href="URL">nhãn</a> thành «nhãn: URL» ngay cạnh dòng; tin quá 6 link, hoặc có link vẫn dài sau khi rút gọn
  (an_redir), thành «nhãn [1]» và URL gom cuối tin (chủ bot 2026-10-31: URL an_redir dài chen giữa bài khó coi;
  link ngắn s.shopee.vn/… thì để cạnh luôn); nút Mua (nút link) thành dòng dẫn + URL trần ở cuối cùng tin
  (chủ bot 2026-10-31: một tin, không tách đôi);
- nút u:* thành danh sách «1 · …»; khách gõ số thì tiến trình Zalo chạy đúng nút đó;
- câu chữ dùng chung với Telegram: «/hotro», «bấm nút…» đổi sang lệnh gõ tắt của Zalo (PLAN-083);
- tin dài cắt theo dòng, mỗi tin tối đa 2000 ký tự.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from cashback_bot.messages import BUY_BUTTON, FOOD_BUTTON, HUONGDAN, TIKTOK_BUY_BUTTON, BotReply, with_tiktok
from cashback_bot.shopee_shortener import shorten_if_an_redir

MAX_LEN = 2000
STYLE_CODES = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "ins": "u", "s": "s", "del": "s", "strike": "s"}
MENU_TITLE = "Gõ số để chọn:"
LINKS_TITLE = "🔗 Bấm link theo số:"
INLINE_LINKS = 6  # tối đa số link để ngay cạnh dòng (bản gọn Zalo của tin mã: sale_relay.ZALO_MAX_LINKS)
SHORT_URL = 40  # «https://s.shopee.vn/4LKZbH6EWM» = 30 ký tự; an_redir ~130
# Nhãn chung của bài relay (sale_relay.post_html): link để cạnh dòng thì in «🔗 URL», không «🔗 Lưu mã: URL».
BARE_LABELS = frozenset({"🔗 Lưu mã", "🔗 Mua ngay"})

WELCOME = (
    "👋 <b>Chào bạn! Đây là bot tự động hoàn tiền mua sắm</b>, không phải người trả lời.\n"
    "Dán link sản phẩm Shopee, bot gửi lại link mua và số tiền hoàn dự kiến.\n"
    "Bot lưu link bạn gửi, đơn mua qua link đó và nội dung bạn gửi khi cần hỗ trợ, chỉ để tính hoàn tiền "
    "và hỗ trợ bạn.\n"
    "Gõ <b>hd</b> để xem hướng dẫn, <b>menu</b> để mở trang chủ."
)
LINK_CARD = (
    "🔗 <b>Zalo đã biến link thành thẻ xem trước nên bot chưa đọc được</b>\n"
    "Bạn gửi lại theo một trong hai cách:\n"
    "1. Dán link, bấm dấu ✕ trên thẻ xem trước rồi mới gửi.\n"
    "2. Hoặc xoá phần https:// ở đầu link, ví dụ: s.shopee.vn/abc123"
)
GUIDE = (
    "📖 <b>Cách dùng trên Zalo</b>\n\n"
    "1. Mở sản phẩm trên Shopee, bấm <b>Chia sẻ</b> rồi <b>Sao chép liên kết</b>.\n"
    "2. Dán link vào đây. Zalo hiện thẻ xem trước thì bấm dấu <b>✕</b> trên thẻ rồi mới gửi "
    "(hoặc xoá phần https:// ở đầu link).\n"
    "3. Bot gửi lại số tiền hoàn dự kiến và link <b>🛒 Mua trên Shopee</b>.\n"
    "4. Bấm link đó để mở sản phẩm và đặt hàng như bình thường.\n\n"
    "Gõ <b>don</b> để xem đơn, <b>hotro</b> khi cần hỗ trợ, <b>menu</b> để về trang chủ.\n\n"
    "Bot không thu phí sử dụng. Bạn thanh toán trực tiếp trên Shopee.\n\n"
    "ⓘ Số hoàn là ước tính, không bảo đảm đơn hàng được ghi nhận hay được hoàn tiền."
)
BUY_LEAD = "👉 Bấm link này để mua. Mua thẳng trong app Shopee sẽ không được hoàn:"
TIKTOK_BUY_LEAD = "👉 Bấm link này để mua. Mua thẳng trong app TikTok sẽ không được hoàn:"
FOOD_LEAD = "👉 Link đặt món ShopeeFood (đơn Food chưa được hoàn tiền):"
# Câu chữ dùng chung với Telegram nhắc tới nút bấm. Test canh câu gốc còn nằm trong messages.py.
PHRASES = (
    # Dòng dẫn + URL đã ở cuối cùng tin: bỏ câu bấm nút của Telegram.
    ("👉 Bấm <b>🛒 Mua trên Shopee</b> bên dưới rồi đặt hàng.", ""),
    # Rà soát 2026-10-26: câu «bấm» của Telegram còn lọt sang Zalo.
    ("Bấm vào đơn để xem tiến trình.", "Gõ số của đơn để xem tiến trình."),
    ("Nếu bạn thấy chưa đúng, bấm 📩 Yêu cầu kiểm tra.", "Nếu bạn thấy chưa đúng, chọn 📩 Yêu cầu kiểm tra."),
    ("Nút này không còn hiệu lực.", "Lựa chọn này đã hết hạn. Gõ menu để mở trang chủ."),
    ("👉 Bấm <b>🛒 Mua trên TikTok Shop</b> bên dưới rồi đặt hàng.", ""),
    ("Bấm nút dưới hoặc gõ /huongdan", "Gõ /huongdan"),
    ("nút <b>🛒 Mua trên Shopee</b>", "link <b>🛒 Mua trên Shopee</b>"),
    ("Bấm nút đó", "Bấm link đó"),
    ("Bạn vẫn có thể đặt món qua nút dưới nếu muốn.", "Bạn vẫn có thể đặt món qua link bên dưới nếu muốn."),
    ("Bấm chọn ngân hàng của bạn.", "Gõ số để chọn ngân hàng của bạn."),
    ("Bạn bấm chọn ngân hàng trước", "Bạn chọn ngân hàng trước"),
    ("Bấm Tài khoản nhận tiền để khai", "Chọn Tài khoản nhận tiền để khai"),
    ("đọc và bấm đồng ý bản hiện hành", "đọc và chọn đồng ý bản hiện hành"),
    ("Bấm từng mục để đọc.", "Gõ số của từng mục để đọc."),
    ("nếu đồng ý thì bấm nút cuối.", "nếu đồng ý thì gõ số của dòng ✅ Tôi đã đọc và đồng ý."),
    ("Bấm để bật / tắt.", "Gõ số để bật / tắt. Chọn nhiều thì gõ các số cách nhau, ví dụ: 1 3 5."),
    ("Bỏ chọn hết là không nhận nữa.",
     "Bỏ chọn hết là không nhận nữa. Chọn nhiều thì gõ các số cách nhau, ví dụ: 1 3 5."),
    ("👉 Bấm nút dưới để chọn danh mục deal.", "👉 Gõ số 1 để chọn danh mục deal."),
    ("Bấm món muốn mua, bot gửi link hoàn tiền liền 😎", "Gõ số món muốn mua, bot gửi link hoàn tiền liền 😎"),
    ("Đổi danh mục hay tắt deal: bấm ⚙️ Đổi danh mục bên dưới nha 🫶",
     "Đổi danh mục hay tắt deal: gõ số của dòng ⚙️ Đổi danh mục nha 🫶"),
)
# Lệnh Telegram → lệnh gõ tắt Zalo (zalo_bot.SHORTCUTS nhận cả hai).
COMMANDS = {
    "huongdan": "hd", "donhang": "don", "hotro": "hotro", "vi": "vi", "dieukien": "dieukien",
    "cachtinh": "cachtinh", "thongbao": "thongbao", "hang": "hang", "start": "menu", "theodoi": "theodoi",
    "deal": "deal", "magiam": "magiam",
}
_CMD = "|".join(COMMANDS)
_VERB_CMD = re.compile(rf"\b(Gõ|gõ|Nhắn|nhắn|Mở|mở) /({_CMD})\b")
_PREP_CMD = re.compile(rf"\b(?:tại|qua|ở) /({_CMD})\b")
_SEE_CMD = re.compile(rf"\bxem /({_CMD})\b")
_BARE_CMD = re.compile(rf"(?<![\w/.:])/({_CMD})\b")
_ARROWS = ("◀️", "▶️")
NON_TEXT = "🙏 Bot chỉ đọc được tin chữ. Bạn gửi link sản phẩm Shopee dạng chữ nhé. Gõ <b>hd</b> để xem hướng dẫn."
NUMBER_STALE = "Danh sách lựa chọn đã hết hạn hoặc không có số này. Gõ <b>menu</b> để mở trang chủ."
NUMBER_MISSING = "Không có số {number}. Tin gần nhất có {choices}, hoặc gõ <b>menu</b> để mở trang chủ."


def number_missing(number: int, count: int) -> str:
    """Gõ số ngoài danh sách đang có (danh sách vẫn còn hạn)."""
    return NUMBER_MISSING.format(number=number, choices="số 1" if count == 1 else f"số 1 đến {count}")
ERROR_REPLY = "⚠️ Bot đang gặp lỗi khi xử lý tin này. Bạn thử lại sau ít phút nhé, hoặc gõ <b>hotro</b>."
INTERRUPTED_REPLY = "🙏 Bot vừa khởi động lại đúng lúc đọc tin của bạn nên chưa trả lời được. Bạn gửi lại tin giúp mình nhé."

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
    def __init__(self, footnotes: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        # footnotes: link thành «nhãn [n]», URL gom vào self.notes (theo thứ tự, URL trùng dùng chung số).
        self.footnotes = footnotes
        self.notes: list[str] = []
        self.parts: list[str] = []
        self.pos = 0
        self.open: list[tuple[str, int]] = []
        self.styles: list[Style] = []
        self.href: str | None = None
        self.link_text: list[str] = []
        self.link_at = (0, 0)  # (số phần, vị trí) lúc mở thẻ <a>: xoá nhãn chung khi in URL cạnh dòng

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
            self.link_at = (len(self.parts), self.pos)
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
            if self.footnotes:
                if self.href not in self.notes:
                    self.notes.append(self.href)
                self.emit(f" [{self.notes.index(self.href) + 1}]")
            elif (label := "".join(self.link_text).strip()) in BARE_LABELS:
                del self.parts[self.link_at[0]:]
                self.pos = self.link_at[1]
                self.emit(f"🔗 {shorten_if_an_redir(self.href)}")
            elif label != self.href:
                self.emit(f": {shorten_if_an_redir(self.href)}")
            self.href = None

    def handle_data(self, data: str) -> None:
        self.emit(data)
        if self.href is not None:
            self.link_text.append(data)


def zalo_wording(html_text: str) -> str:
    """Đổi câu chữ kiểu Telegram sang Zalo: «Gõ /hotro» → «Gõ hotro», «tại /hotro» → «bằng cách gõ hotro»."""
    text = html_text or ""
    for old, new in PHRASES:
        text = text.replace(old, new)
    text = _VERB_CMD.sub(lambda m: f"{'Gõ' if m.group(1)[0].isupper() else 'gõ'} <b>{COMMANDS[m.group(2)]}</b>", text)
    text = _PREP_CMD.sub(lambda m: f"bằng cách gõ <b>{COMMANDS[m.group(1)]}</b>", text)
    text = _SEE_CMD.sub(lambda m: f"xem bằng cách gõ <b>{COMMANDS[m.group(1)]}</b>", text)
    return _BARE_CMD.sub(lambda m: f"gõ <b>{COMMANDS[m.group(1)]}</b>", text)


_ORDINAL = re.compile(r"^\d{1,3}\.\s+")
_HREF = re.compile(r"<a\s[^>]*href=\"(https?://[^\"]+)\"")


def _label(label: str) -> str:
    for arrow in _ARROWS:
        label = label.replace(arrow, "")
    # Nhãn nút đã có số thứ tự riêng («1. Áo…»): Zalo tự đánh số, bỏ số cũ để khách không gõ nhầm.
    return _ORDINAL.sub("", label.strip())


def flatten(html_text: str, footnotes: bool = False) -> tuple[str, list[Style]]:
    """HTML Telegram → (chữ thuần, style). Thẻ khác (code, pre, blockquote…) bỏ thẻ, giữ chữ.

    footnotes: link thành «nhãn [n]», cuối tin thêm «🔗 Bấm link theo số:» và «[n] URL» mỗi dòng.
    """
    parser = _Flatten(footnotes)
    parser.feed(html_text or "")
    parser.close()
    if parser.notes:
        parser.emit("\n\n")
        parser.styles.append((parser.pos, _u16(LINKS_TITLE), "b"))
        parser.emit(LINKS_TITLE)
        for number, url in enumerate(parser.notes, start=1):
            parser.emit(f"\n[{number}] {shorten_if_an_redir(url)}")
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
    """Cắt theo dòng thành các tin ≤ MAX_LEN; style cắt và dời theo từng tin.

    Ưu tiên cắt ở dòng trống gần nhất (hết đoạn) nếu phần trước đó dài ít nhất nửa tin: danh sách «[n] URL» và
    «Gõ số để chọn» không bị xé đôi giữa hai tin (chủ bot 2026-10-31).
    """
    chunks: list[tuple[int, str]] = []
    start, current, cut = 0, "", 0  # cut: độ dài current tính tới hết dòng trống gần nhất
    for line in text.splitlines(keepends=True):
        for piece in _pieces(line):
            while current and _u16(current + piece) > MAX_LEN:
                head = current[:cut] if _u16(current[:cut]) >= MAX_LEN // 2 else current
                chunks.append((start, head))
                start += _u16(head)
                current, cut = current[len(head):], 0
            current += piece
            if not piece.strip():
                cut = len(current)
    if current:
        chunks.append((start, current))
    messages = []
    for offset, chunk in chunks:
        body = chunk.strip("\n")
        lead = _u16(chunk[: len(chunk) - len(chunk.lstrip("\n"))])
        if body.strip():
            messages.append(ZaloMessage(body, _clip(styles, offset + lead, offset + lead + _u16(body))))
    return messages


def menu_choices(reply: BotReply) -> list[tuple[str, str]]:
    """(nhãn, callback) của các nút thành danh sách số, theo đúng thứ tự số 1..n."""
    return [(label, data) for row in reply.inline_keyboard or () for label, data in row if data.startswith("u:")]


def _footnotes(body: str) -> bool:
    """Gom URL cuối tin khi có từ 2 link trở lên và: quá INLINE_LINKS link, hoặc có link vẫn dài sau khi rút gọn."""
    urls = {shorten_if_an_redir(html.unescape(url)) for url in set(_HREF.findall(body))}
    return len(urls) >= 2 and (len(urls) > INLINE_LINKS or any(len(url) > SHORT_URL for url in urls))


def render(reply: BotReply) -> tuple[list[ZaloMessage], tuple[str, ...]]:
    """BotReply → (các tin Zalo, callback theo số 1..n). Tin rỗng (chỉ toast) thì gửi nội dung toast.

    Có nút Mua: thẻ báo giá một tin, link mua (kèm danh sách số) một tin ngay sau, để link nằm cuối, dễ bấm.
    """
    # Telegram hiện toast thành popup; Zalo không có popup nên đặt toast lên đầu tin.
    body = f"{reply.toast}\n\n{reply.text}" if reply.text and reply.toast else reply.text or reply.toast or ""
    # Màn bật / tắt: Telegram liệt kê ✅/⬜ trong nội dung lẫn trên nút; Zalo đã có danh sách số nên bỏ dòng lặp.
    toggles = {label for row in reply.inline_keyboard or () for label, _data in row if label[:2] in ("✅ ", "⬜ ")}
    if toggles:
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in body.split("\n") if line not in toggles))
    if body == HUONGDAN:
        body = GUIDE
    elif body == with_tiktok(HUONGDAN):
        body = with_tiktok(GUIDE)  # TikTok đã mở cho khách: hướng dẫn Zalo cũng nhắc cả hai sàn
    text, styles = flatten(re.sub(r"\n{3,}", "\n\n", zalo_wording(body)).strip(), footnotes=_footnotes(body))

    def add(piece: str, bold: bool = False) -> None:
        nonlocal text
        if bold:
            styles.append((_u16(text), _u16(piece), "b"))
        text += piece

    if reply.button_url:
        leads = {None: BUY_LEAD, BUY_BUTTON: BUY_LEAD, TIKTOK_BUY_BUTTON: TIKTOK_BUY_LEAD, FOOD_BUTTON: FOOD_LEAD}
        # Nút link khác (🎟 Lưu mã…, tin báo mã / săn sale qua hàng đợi): dẫn bằng chính nhãn nút.
        lead = leads.get(reply.button_label) or f"👉 {reply.button_label.rstrip(' ↗')}:"
        if text:
            add("\n\n")
        add(lead, bold=True)
        add(f"\n{shorten_if_an_redir(reply.button_url)}")
    choices = menu_choices(reply)
    if choices:
        add("\n\n")
        add(MENU_TITLE, bold=True)
        def group(label: str, data: str) -> int:
            # 0: mục bật / tắt (✅ / ⬜) · 1: lựa chọn khác · 2: về Trang chủ. Đổi nhóm thì cách một dòng.
            # Chỉ tách Trang chủ (không tách mọi u:p:*): trang chủ xen kẽ u:p / u:dc từng ra «1 · …␤␤2 · …␤␤3».
            return 0 if label[:2] in ("✅ ", "⬜ ") else (2 if data == "u:p:home" else 1)

        for number, (label, data) in enumerate(choices, start=1):
            if number > 1 and group(label, data) != group(*choices[number - 2]):
                add("\n")
            name = _label(label)
            # Màn bật / tắt: Zalo iPhone vẽ ⬜ thành khối xám to (chủ bot 2026-10-27). Mục chưa chọn để trơn,
            # mục đã chọn in đậm, ✅ đặt cuối.
            if name.startswith("✅ "):
                add(f"\n{number} · ")
                add(f"{name.removeprefix('✅ ')} ✅", bold=True)
            else:
                add(f"\n{number} · {name.removeprefix('⬜ ')}")
    return split(text, sorted(styles)), tuple(data for _name, data in choices)
