"""Lọc chữ hiện lên live: tên TikTok (che từ bậy) và bong bóng chat (bỏ hẳn nếu bậy / link / số điện thoại).

So khớp trên chữ CÓ DẤU, chữ thường: bỏ dấu sẽ nhầm «đi» với «đĩ», «các» với «cặc», «lớn» với «lồn».
"""

import re

BAD_WORDS = frozenset({
    "địt", "đụ", "lồn", "cặc", "đéo", "đĩ", "buồi", "đjt", "djt", "loz", "lìn", "cặk", "cak",
    "đm", "đmm", "đcm", "đkm", "dm", "dmm", "dcm", "dkm", "vl", "vcl", "vkl", "vãilồn", "clm", "cmm", "đmcs",
})
_WORD = re.compile(r"[\wÀ-ỹđĐ]+", re.UNICODE)
_LINK = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|vn|net|me|io|xyz|shop|link)\b|t\.me/|zalo)", re.IGNORECASE)
_PHONE = re.compile(r"(?:\d[\s.\-]?){9,}")


def _bad(word: str) -> bool:
    return word.lower() in BAD_WORDS


def clean_name(name: str) -> str:
    """Tên vẫn hiện (người xem cần thấy mình), chỉ che từ bậy."""
    return _WORD.sub(lambda m: "***" if _bad(m.group()) else m.group(), name)


def allow_chat(text: str) -> bool:
    """Bong bóng chat: có từ bậy / link / số điện thoại thì không hiện."""
    if _LINK.search(text) or _PHONE.search(text):
        return False
    return not any(_bad(w) for w in _WORD.findall(text))
