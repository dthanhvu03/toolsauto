"""
Cửa vào "dán link" đa nền tảng (ADR-017) — hàm thuần, không đụng DB.

- ``detect_platform(url)``: nhận diện tiktok / youtube / facebook / instagram, khác → ``None``.
- ``normalize_source_url(url)``: bỏ query theo dõi, giữ id video, strip ``/`` cuối — dùng để so trùng
  và lưu ``ViralMaterial.url``.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query key chỉ để theo dõi/chia sẻ — bỏ khi chuẩn hoá (không ảnh hưởng tới tải).
_TRACKING_KEYS = {
    "si", "feature", "igsh", "igshid", "fbclid", "mibextid", "rdid",
    "_r", "_t", "is_from_webapp", "sender_device", "web_id", "share_id",
}
_HOST_ALIAS_PREFIXES = ("www.", "m.")


def _split(url: str):
    raw = (url or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if not host:
        return None
    return parts, host


def _bare_host(host: str) -> str:
    for prefix in _HOST_ALIAS_PREFIXES:
        if host.startswith(prefix):
            return host[len(prefix):]
    return host


def detect_platform(url: str) -> str | None:
    """Nền tảng của link video, hoặc ``None`` nếu không nhận diện được (từ chối)."""
    split = _split(url)
    if not split:
        return None
    parts, host = split
    bare = _bare_host(host)
    path = parts.path or "/"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    if bare == "tiktok.com" or bare.endswith(".tiktok.com"):
        return "tiktok"
    if bare == "youtu.be":
        return "youtube" if path.strip("/") else None
    if bare == "youtube.com":
        if path.startswith("/shorts/") or (path == "/watch" and query.get("v")):
            return "youtube"
        return None
    if bare == "fb.watch":
        return "facebook" if path.strip("/") else None
    if bare == "facebook.com":
        if path.startswith(("/reel/", "/share/r/", "/share/v/")) or "/videos/" in path:
            return "facebook"
        if path.rstrip("/") == "/watch" and query.get("v"):
            return "facebook"
        return None
    if bare == "instagram.com":
        if path.startswith(("/reel/", "/reels/", "/p/")):
            return "instagram"
        return None
    return None


def normalize_source_url(url: str) -> str:
    """
    Chuẩn hoá để so trùng + lưu: https, bỏ ``www.``/``m.``, bỏ fragment, bỏ query theo dõi
    (``utm_*``, ``si``, ``feature``, ``igsh``, ``fbclid``…), YouTube ``/watch`` chỉ giữ ``v``,
    strip ``/`` cuối. Link không parse được thì trả về nguyên (đã strip).
    """
    split = _split(url)
    if not split:
        return (url or "").strip()
    parts, host = split
    bare = _bare_host(host)
    path = (parts.path or "").rstrip("/")

    pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _TRACKING_KEYS and not k.startswith("utm_")
    ]
    if bare == "youtube.com" and path == "/watch":
        pairs = [(k, v) for k, v in pairs if k == "v"][:1]
    query = urlencode(sorted(pairs))

    return urlunsplit(("https", bare, path, query, ""))
