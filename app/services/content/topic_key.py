import hashlib
import re
import unicodedata


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_BASE_STOP_WORDS = {
    "va",
    "la",
    "cua",
    "trong",
    "tai",
    "cho",
    "voi",
    "da",
    "se",
    "mot",
    "cac",
    "nhung",
    "nay",
    "do",
    "khi",
    "sau",
    "truoc",
    "theo",
    "de",
    "ra",
    "vao",
    "len",
    "xuong",
    "co",
    "khong",
}
_GENERIC_HEADLINE_TOKENS = {
    "tong",
    "thong",
    "lenh",
    "moi",
    "tren",
}
_STOP_WORDS = _BASE_STOP_WORDS | _GENERIC_HEADLINE_TOKENS
_MIN_KEYWORD_LEN = 3
_MAX_KEYWORDS = 7


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").lower())
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.replace("\u0111", "d")


def _extract_keywords(normalized_title: str) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []

    for token in _TOKEN_RE.findall(normalized_title):
        if len(token) < _MIN_KEYWORD_LEN or token in _STOP_WORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        keywords.append(token)

    ranked = sorted(keywords, key=lambda token: (-len(token), token))
    return ranked[:_MAX_KEYWORDS]


def compute_topic_key(title: str) -> str:
    """Return a stable 16-char key for near-duplicate Vietnamese headlines."""
    normalized_title = _normalize_text(title)
    keywords = _extract_keywords(normalized_title)

    if keywords:
        payload = "|".join(sorted(keywords))
    else:
        payload = normalized_title.strip() or "empty"

    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]
