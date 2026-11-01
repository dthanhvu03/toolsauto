"""Hiểu comment: tên tỉnh, «không về», lệnh ở trạm dừng chân."""

import re
import unicodedata
from dataclasses import dataclass

from .provinces import PROVINCES, Province


def normalize(text: str) -> str:
    """Bỏ dấu, chữ thường, chỉ giữ chữ + số, mỗi từ cách nhau một khoảng."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


@dataclass(frozen=True)
class Command:
    kind: str  # province | stay | food | wc | gift_shop | where | chat
    province: Province | None = None
    item: str = ""


def _build_phrases() -> tuple[list[tuple[str, Province]], dict[str, Province]]:
    phrases: list[tuple[str, Province]] = []
    exact: dict[str, Province] = {}
    for p in PROVINCES:
        for phrase in {normalize(p.name), *p.aliases}:
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
                "a", "voi", "luon", "nhaa", "lun", "dc", "duoc", "cho", "em", "anh"}
_STAY_FILLER = {"nam", "nay", "duoc", "dc", "roi", "tet", "que", "nha", "minh", "toi", "em", "anh", "thoi",
                "huhu", "buon", "qua", "lai", "lam", "nua", "oi", "a", "ve", "khong", "ko", "k", "kh", "hong",
                "hok", "chua", "o"}
_MAX_EXTRA_WORDS = 4

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


def parse(text: str, at_rest_stop: bool = False) -> Command:
    norm = normalize(text)
    if not norm:
        return Command("chat")
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
    return Command("chat")
