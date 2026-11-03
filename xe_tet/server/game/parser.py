"""Hiểu comment: tên tỉnh, «không về», lệnh ở trạm dừng chân."""

import re
import unicodedata
from dataclasses import dataclass

from .provinces import CITY_ALIASES, PROVINCES, Province


def normalize(text: str) -> str:
    """Bỏ dấu, chữ thường, chỉ giữ chữ + số, mỗi từ cách nhau một khoảng."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


@dataclass(frozen=True)
class Command:
    kind: str  # province | board | stay | food | wc | gift_shop | where | station | fuel | wash | chat
    province: Province | None = None
    item: str = ""
    station: str = ""  # gọi xe ra bến này («từ Hà Nội», «bến Giáp Bát») — đi kèm đặt vé nếu có cả tỉnh về


def _build_phrases() -> tuple[list[tuple[str, Province]], dict[str, Province]]:
    phrases: list[tuple[str, Province]] = []
    exact: dict[str, Province] = {}
    for p in PROVINCES:
        for phrase in {normalize(p.name), *p.aliases, *CITY_ALIASES.get(p.key, ())}:
            phrases.append((phrase, p))
        for code in (*p.codes, *p.plates):
            exact[code] = p
    phrases.sort(key=lambda item: len(item[0]), reverse=True)  # «ha nam» thua «quang nam» khi trùng
    return phrases, exact


_PHRASES, _EXACT = _build_phrases()

_STAY = ("khong ve", "ko ve", "k ve", "kh ve", "hong ve", "hok ve", "chua ve", "khong duoc ve",
         "ko dc ve", "k dc ve", "o lai")

# Comment chỉ được hiểu là đặt vé / không về khi phần còn lại toàn từ đệm — tránh «Hà Nội lạnh quá»,
# «chị Huệ ơi» thành đặt vé, «mẹ chưa về à» / «ai ở lại không» thành huỷ vé.
_BOOK_FILLER = {"ve", "di", "que", "toi", "minh", "nha", "nhe", "thoi", "nao", "day", "len", "xe", "ne",
                "a", "voi", "luon", "nhaa", "lun", "dc", "duoc", "cho", "em", "anh", "qua", "o", "tai", "den",
                # câu đặt vé tự nhiên («cho em 1 vé về Thanh Hóa», «đặt vé đi Đà Nẵng» — rà soát 02/11)
                "1", "mot", "dat", "xin", "mua", "giuong", "chuyen", "ah", "ak", "ha", "nhe", "vs", "zoi", "dk"}
# Địa chỉ chi tiết sau tên tỉnh («qua hải phòng ngõ 174 phường Lê Thanh Nghị» — live 02/11, gõ mãi không lên xe vì bị coi là
# tán gẫu): có chữ chỉ địa chỉ thì vẫn là đặt vé về tỉnh đó. Thẻ vé chỉ ghi tên tỉnh, không đọc / hiện lại địa chỉ.
_ADDRESS = ("ngo", "ngach", "hem", "kiet", "phuong", "thon", "xom", "ap", "huyen", "quan", "thi tran", "thi xa", "khu pho",
            "so nha", "khom", "tinh", "thanh pho", "tp")  # không tính «đường»: «đường về Hà Nội xa quá» không phải đặt vé
_STAY_FILLER = {"nam", "nay", "duoc", "dc", "roi", "tet", "que", "nha", "minh", "toi", "em", "anh", "thoi",
                "huhu", "buon", "qua", "lai", "lam", "nua", "oi", "a", "ve", "khong", "ko", "k", "kh", "hong",
                "hok", "chua", "o"}
_MAX_EXTRA_WORDS = 6
# Muốn lên xe mà không nói tỉnh («lên xe», «về quê», «cho đi với») — trước đây là tán gẫu, người xem không được phản hồi.
_BOARD = ("len xe", "ve que", "di xe", "cho len", "cho di", "dat ve", "mua ve", "dang ky", "dang ki", "book ve", "len xe voi")
_FUZZY_MIN = 5  # gõ sai một chữ («Nghe Ann», «nge an») chỉ xét tên ≥ 5 chữ cái — tên ngắn dễ trùng chữ thường

# (cụm từ, món hiển thị) — cụm dài xếp trước để «banh mi» không bị «mi» ăn mất.
# Món ở trạm dừng chân: (tên, emoji, cách gõ) — một bảng, thêm món là thêm một dòng. «mi» để cuối: «banh mi» khớp trước.
FOODS = (
    ("Bánh mì", "🥖", ("banh mi",)), ("Trà đá", "🧊", ("tra da",)), ("Cà phê", "☕", ("ca phe", "cafe", "cf")),
    ("Nước mía", "🥤", ("nuoc mia",)), ("Phở", "🍜", ("pho",)), ("Bún", "🍲", ("bun",)), ("Cơm", "🍚", ("com",)),
    ("Mì gói", "🍜", ("mi",)),
)
FOOD_EMOJI = {label: emoji for label, emoji, _ in FOODS}
_FOOD_PHRASES = tuple((phrase, label) for label, _, phrases in FOODS for phrase in phrases)
_WC = ("wc", "ve sinh", "toilet", "di tieu", "di ve sinh")
_SHOP = ("mua qua", "dac san", "mua do")


# Hỏi xe / vé của mình (PLAN-134 B — người xem không biết mình ở xe nào, xe tới đâu). «vé» bỏ dấu trùng «về» (câu đặt vé
# «về Huế») → chỉ nhận chữ «vé» có dấu hoặc câu hỏi rõ nghĩa, không nhận «ve» trơn.
_WHERE = ("xe nao", "xe so may", "o xe nao", "toi o dau", "minh o dau", "em o dau", "toi dau roi", "den dau roi",
          "toi noi chua", "tra ve", "check ve", "kiem tra ve", "con bao lau", "bao lau nua", "bao gio toi", "may gio toi",
          "khi nao toi", "bao gio den", "khi nao den")
_TICKET_WORD = re.compile(r"(?<!\w)vé(?!\w)")


# Gọi xe ra bến khác (PLAN-136, live 02/11 «cho xe ra bến khác»): chữ dẫn + tên bến / thành phố có bến. Chỉ «Hà Nội» trơn
# vẫn là đặt vé về Hà Nội; phải có «từ / bến / ra bến / xuất bến…» mới là gọi bến.
_STATION_LEAD = ("tu", "ben", "ben xe", "ra ben", "xuat ben", "chay tu", "di tu", "o ben", "don o", "don tu")
_STATIONS = {
    "hcm_miendong": ("sai gon", "sg", "hcm", "tp hcm", "tphcm", "ho chi minh", "mien dong", "mien dong moi"),
    "hn_giapbat": ("ha noi", "hn", "giap bat"),
    "dalat": ("da lat",),
    "danang": ("da nang",),
    "cantho": ("can tho",),
}
_STATION_PHRASES = sorted(((f"{lead} {alias}", key) for key, aliases in _STATIONS.items() for alias in aliases
                           for lead in _STATION_LEAD), key=lambda pk: -len(pk[0]))


# Đổ xăng / rửa xe lúc chờ khách (PLAN-137, anh 02/11 «khúc đợi khách thêm đổ xăng rửa xe»). «rua» trơn trùng «rùa»: bỏ.
_FUEL = ("do xang", "xang", "do dau", "bom xang", "do day binh", "do day xang", "xang dau")
_WASH = ("rua xe", "lau xe", "tam xe", "xit nuoc", "xit xe", "rua xe di", "rua cho sach")


def _station(norm: str) -> tuple[str, str] | None:
    """(cụm gọi bến, khoá bến) hoặc None."""
    return next(((phrase, key) for phrase, key in _STATION_PHRASES if _has(norm, phrase)), None)


def _has(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def _rest_words(text: str, phrase: str) -> list[str]:
    """Các từ còn lại sau khi bỏ cụm `phrase` (một lần)."""
    words = f" {text} ".replace(f" {phrase} ", " ", 1).split()
    return words


def _only_filler(words: list[str], filler: set[str]) -> bool:
    return len(words) <= _MAX_EXTRA_WORDS and all(w in filler for w in words)


def _find_province(norm: str) -> tuple[str, Province] | None:
    for phrase, prov in _PHRASES:
        if _has(norm, phrase):
            return phrase, prov
    return None


def _edits(a: str, b: str) -> int:
    """Số chữ phải sửa (thêm / bớt / đổi) để a thành b — chỉ cần biết ≤ 1."""
    if abs(len(a) - len(b)) > 1:
        return 2
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


_SQUASHED = {phrase.replace(" ", ""): prov for phrase, prov in _PHRASES}


def _loose_province(norm: str) -> Province | None:
    """Cả câu (bỏ từ đệm) là tên tỉnh viết liền («Hanoi», «nghệan») hoặc sai một chữ («Nghe Ann») — rà soát 02/11."""
    core = "".join(w for w in norm.split() if w not in _BOOK_FILLER)
    if not core:
        return None
    if core in _SQUASHED:
        return _SQUASHED[core]
    if len(core) < _FUZZY_MIN:
        return None
    near = {prov.key: prov for squashed, prov in _SQUASHED.items() if len(squashed) >= _FUZZY_MIN and _edits(core, squashed) <= 1}
    return next(iter(near.values())) if len(near) == 1 else None  # gần hai tỉnh cùng lúc thì không đoán


def parse(text: str, at_rest_stop: bool = False) -> Command:
    norm = normalize(text)
    if not norm:
        return Command("chat")
    if any(_has(norm, w) for w in _WASH) and not _find_province(norm):
        return Command("wash")
    if any(_has(norm, f) for f in _FUEL) and not _find_province(norm):
        return Command("fuel")
    station = _station(norm)
    if station:  # «từ Hà Nội» / «bến Giáp Bát»: gọi bến; «từ Hà Nội về Nghệ An»: gọi bến + đặt vé Nghệ An
        rest = " ".join(_rest_words(norm, station[0]))
        dest = _find_province(rest) if rest else None
        if dest and (_only_filler(_rest_words(rest, dest[0]), _BOOK_FILLER) or rest in _EXACT):
            return Command("province", dest[1], station=station[1])
        return Command("station", station=station[1])
    found = _find_province(norm)
    stay = next((s for s in _STAY if _has(norm, s)), None)
    if stay:
        rest = _rest_words(norm, stay)
        if found:  # «không về Nghệ An được» vẫn là không về
            rest = _rest_words(" ".join(rest), found[0])
        if _only_filler(rest, _STAY_FILLER):
            return Command("stay")
    if at_rest_stop:
        if any(_has(norm, s) for s in _WC):
            return Command("wc")
        if any(_has(norm, s) for s in _SHOP):
            return Command("gift_shop")
        for phrase, label in _FOOD_PHRASES:
            if _has(norm, phrase):
                return Command("food", item=label)
    if norm == "xe" or any(_has(norm, w) for w in _WHERE) or (not found and _TICKET_WORD.search(text.lower())):
        return Command("where")
    if norm in _EXACT:
        return Command("province", _EXACT[norm])
    if found and _only_filler(_rest_words(norm, found[0]), _BOOK_FILLER):
        return Command("province", found[1])
    if found and any(_has(" ".join(_rest_words(norm, found[0])), a) for a in _ADDRESS):
        return Command("province", found[1])
    if not found and (loose := _loose_province(norm)):
        return Command("province", loose)
    board = next((b for b in _BOARD if _has(norm, b)), None)
    if board and _only_filler(_rest_words(norm, board), _BOOK_FILLER):
        return Command("board")
    return Command("chat")
