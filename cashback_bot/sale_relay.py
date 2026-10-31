"""Tự động chuyển tiếp (Relay) tin săn sale từ các kênh Telegram lớn (PLAN-106).

- Quét định kỳ các kênh Telegram công khai (mặc định: nhomsansale).
- Tự động phát hiện tất cả link Shopee (s.shopee.vn, shp.ee, shopee.vn).
- Giải mã link đích thực tế, loại bỏ mã tiếp thị của người khác.
- Thay thế hoàn toàn bằng link tiếp thị Affiliate của chủ bot (s.shopee.vn/an_redir).
- Đăng kèm ảnh banner và nút bấm 1 chạm vào kênh trung gian (ZT báo mã) và gửi khách.
"""

from __future__ import annotations

import html
import ipaddress
import json
import logging
import re
import socket
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import fit_html
from cashback_bot.money import format_vnd
from cashback_bot.telegram_api import TelegramApi

logger = logging.getLogger("cashback_bot")

DEFAULT_CHANNELS = ["nhomsansale"]
POLL_INTERVAL_SEC = 90  # 1.5 phút quét một lần
REQUEST_TIMEOUT = (3.0, 5.0)
SUB_ID = "AUTOSALE"
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
HEAD_TIMEOUT = (2.0, 3.0)
MAX_HOPS = 3
CODES_PER_POST = 20  # voucher_posts.message_id = post_id * 100 + thứ tự mã
CODE_FRESH_FOR = timedelta(hours=24)  # mã đã có trong voucher_posts trong khoảng này thì không ghi lại

_ALLOWED_SHOPEE_HOSTS = frozenset({
    "shopee.vn",
    "www.shopee.vn",
    "s.shopee.vn",
    "shp.ee",
    "vn.shp.ee",
    "shope.ee",
})

# Link rút gọn: phải HEAD để biết trang đích. Host khác (shopee.vn…) đã là trang đích, không gọi thêm.
_SHORT_HOSTS = frozenset({"s.shopee.vn", "shp.ee", "vn.shp.ee", "shope.ee"})
_REDIRECTS = (301, 302, 303, 307, 308)
_LABEL_WORDS = ("mã", "voucher", "giảm", "lưu mã")
_SEND_WORDS = ("mã", "voucher", "giảm", "lưu mã", "hoàn xu")

# Một lượt quét chạy trong luồng nền (tick); mở link trong pool chung, mỗi luồng một Session giữ kết nối TLS.
_running = threading.Lock()
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sale-relay-link")
_local = threading.local()
# Cache trong một lượt quét (run_once): {"dns": {host: an_toàn}, "links": {link gốc: link đã bọc}}. Ngoài lượt quét
# (gọi lẻ, test) = None: luôn kiểm tra lại.
_RUN: dict[str, dict] | None = None

_ALLOWED_PHOTO_HOSTS = frozenset({
    "telesco.pe",
    "tele.pe",
    "telegram.org",
    "cdn.telegram.org",
    "cdn1.telesco.pe",
    "cdn4.telesco.pe",
    "cdn.tele.pe",
})

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "mmp_pid", "uls_trackid", "gads_t_sig", "affiliate_id", "sub_id",
    "af_sub_siteid", "c", "is_from_login", "smtt", "deep_and_deferred_rec",
    "pid", "af_click_lookback", "c_name", "af_dp", "af_web_dp", "af_adset",
    "af_ad", "af_channel", "source", "entry_point",
}


def _is_allowed_shopee_host(hostname: str) -> bool:
    if not hostname:
        return False
    host = hostname.lower()
    return host in _ALLOWED_SHOPEE_HOSTS or host.endswith(".shopee.vn")


def _public_host(hostname: str) -> bool:
    """Mọi IP của host đều là IP công khai (chống SSRF, DNS rebinding). Lỗi DNS: ngoại lệ, người gọi xử lý."""
    cache = _RUN["dns"] if _RUN is not None else None
    if cache is not None and hostname in cache:
        return cache[hostname]
    ok = True
    for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            ok = False
            break
    if cache is not None:
        cache[hostname] = ok
    return ok


def is_safe_shopee_url(url: str) -> bool:
    """Kiểm tra URL Shopee an toàn, chống SSRF và DNS rebinding."""
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        if parsed.username or parsed.password:
            return False
        hostname = (parsed.hostname or "").lower()
        if not _is_allowed_shopee_host(hostname):
            return False
        return _public_host(hostname)
    except Exception:
        return False


def is_safe_photo_url(url: str) -> bool:
    """Kiểm tra URL ảnh an toàn (chỉ nhận HTTPS từ CDN Telegram hợp lệ)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        if parsed.username or parsed.password:
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        if not any(hostname == h or hostname.endswith("." + h) for h in _ALLOWED_PHOTO_HOSTS):
            return False
        return _public_host(hostname)
    except Exception:
        return False


def _unwrap(raw: str) -> str:
    """Lấy origin_link nếu raw đã là link an_redir (chống double-wrapping)."""
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        if host in {"s.shopee.vn", "shp.ee", "shope.ee"} and parsed.path.rstrip("/") == "/an_redir":
            origin = (parse_qs(parsed.query).get("origin_link") or [""])[0].strip()
            if origin:
                return _unwrap(origin)
    except Exception:
        pass
    return raw


def _is_tracking_param(param_name: str) -> bool:
    lower = param_name.lower()
    return (
        lower in _TRACKING_PARAMS
        or lower.startswith(("an_", "af_", "utm_", "sp_"))
    )


def _clean_shopee_url(raw_url: str) -> str:
    """Loại bỏ các tham số tiếp thị của người khác, giữ nguyên link gốc sạch."""
    try:
        unwrapped = _unwrap(raw_url)
        parsed = urlparse(unwrapped)
        params = parse_qs(parsed.query)
        clean_params = {k: v for k, v in params.items() if not _is_tracking_param(k)}
        new_query = urlencode(clean_params, doseq=True)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" + (f"?{new_query}" if new_query else "")
    except Exception:
        return raw_url


def _session() -> requests.Session:
    session = getattr(_local, "session", None)
    if session is None:
        session = _local.session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0"
    return session


def _head(url: str) -> requests.Response:
    return _session().head(url, allow_redirects=False, timeout=HEAD_TIMEOUT)


def _https(url: str) -> str:
    """http:// của host Shopee → https:// (host lạ giữ nguyên để kiểm tra an toàn chặn)."""
    if url.startswith("http://") and _is_allowed_shopee_host((urlparse(url).hostname or "").lower()):
        return "https://" + url[7:]
    return url


def resolve_shopee_link(url: str, affiliate_id: str, sub_id: str = SUB_ID) -> str:
    """Lấy link đích thực tế và bọc bằng link Affiliate của mình.

    Chỉ HEAD link rút gọn; link an_redir lấy origin_link luôn, trang shopee.vn không gọi thêm.
    """
    if not affiliate_id or not affiliate_id.isdigit():
        return url

    current_url = _https(url)
    for _ in range(MAX_HOPS):
        if not is_safe_shopee_url(current_url):
            return url
        current_url = _unwrap(current_url)
        if (urlparse(current_url).hostname or "").lower() not in _SHORT_HOSTS:
            break
        try:
            resp = _head(current_url)
        except Exception as exc:
            logger.debug("[SaleRelay] Resolve error on %s: %s", current_url, exc)
            break
        if resp.status_code not in _REDIRECTS or "Location" not in resp.headers:
            break
        current_url = _https(urljoin(current_url, resp.headers["Location"].strip()))

    if not is_safe_shopee_url(current_url):
        return url

    clean = _clean_shopee_url(current_url)
    try:
        from cashback_bot.shopee_shortener import shorten_shopee_url
        short = shorten_shopee_url(clean, sub_id=sub_id)
        if short:
            return short
    except Exception as exc:
        logger.debug("[SaleRelay] Shorten bridge error on %s: %s", clean, exc)

    try:
        query = urlencode({"origin_link": clean, "affiliate_id": affiliate_id, "sub_id": sub_id})
        return f"https://s.shopee.vn/an_redir?{query}"
    except Exception:
        return url


def _resolve(link: str, affiliate_id: str) -> str:
    """resolve_shopee_link, dùng lại kết quả khi một link gặp lại trong cùng lượt quét."""
    cache = _RUN["links"] if _RUN is not None else None
    if cache is not None and link in cache:
        return cache[link]
    result = resolve_shopee_link(link, affiliate_id)
    if cache is not None:
        cache[link] = result
    return result


def _is_shopee_url_candidate(url_str: str) -> bool:
    """Kiểm tra sơ bộ cú pháp link Shopee khi bóc tách HTML bài viết."""
    try:
        parsed = urlparse(url_str)
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        if parsed.username or parsed.password:
            return False
        hostname = (parsed.hostname or "").lower()
        return _is_allowed_shopee_host(hostname)
    except Exception:
        return False


_POST_ID = re.compile(r'data-post="[^"]+/(\d+)"')
_PHOTO = re.compile(r"background-image:url\('([^']+)'\)")
_POST_TEXT = re.compile(r"tgme_widget_message_text[^>]*>(.*?)</div>", re.DOTALL)
_BR = re.compile(r"<br\s*/?>")
_TAG = re.compile(r"<[^>]+>")
_LINK = re.compile(r"https?://[^\s<>\"']+")
# Link đầy đủ hoặc tên miền trần («nhomsansale.com/fb», «t.me/x»). Chỉ đuôi tên miền hay gặp, để «ok.Fb» không khớp.
_ANY_LINK = re.compile(
    r"https?://[^\s<>\"']+"
    r"|(?<![\w@/.])(?:[a-z0-9-]+\.)+(?:com|net|org|vn|me|io|co|info|biz|xyz|link|shop|site|store|online|top|click"
    r"|app|ly|gl|cc|to|tv|gg)\b(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)


def parse_channel_html(html_text: str) -> list[dict[str, Any]]:
    """Bóc tách các bài viết từ HTML của trang t.me/s/<channel>."""
    posts: list[dict[str, Any]] = []
    blocks = html_text.split("tgme_widget_message_wrap")
    for block in blocks[1:]:
        msg_id_match = _POST_ID.search(block)
        if not msg_id_match:
            continue
        msg_id = int(msg_id_match.group(1))

        # Photo
        photos = _PHOTO.findall(block)
        photo_url = photos[0] if photos else None

        # Text
        text_match = _POST_TEXT.search(block)
        raw_html = text_match.group(1) if text_match else ""

        # Convert simple HTML tags to plain / standard
        clean_text = _BR.sub("\n", raw_html)
        clean_text = _TAG.sub(" ", clean_text)
        clean_text = html.unescape(clean_text).strip()

        # Find raw links and strictly filter against allowed Shopee domains
        links = _LINK.findall(raw_html + " " + clean_text)
        shopee_links = [
            lnk.rstrip(".,)")
            for lnk in links
            if _is_shopee_url_candidate(lnk.rstrip(".,)"))
        ]

        posts.append({
            "id": msg_id,
            "text": clean_text,
            "photo_url": photo_url,
            "shopee_links": list(dict.fromkeys(shopee_links)),
        })
    return posts


# --- Bóc mã giảm giá từ bài tổng hợp ------------------------------------------------------------------------------

# Mã: chữ HOA + số ASCII 4–20 ký tự, có ít nhất một chữ. Chữ HOA tiếng Việt (MÃ, GIẢM) không khớp vì \b Unicode.
_CODE = re.compile(r"(?<![\w/])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{4,20}(?![\w/])")
# Từ HOA hay gặp trong bài săn sale nhưng không phải mã.
_NOT_CODES = frozenset({
    "SHOPEE", "SALE", "VOUCHER", "FREESHIP", "XTRA", "LIVE", "MALL", "FLASH", "DEAL", "CODE", "LINK", "FREE",
    "SHOP", "SPAYLATER", "SPAY", "TIKTOK", "LAZADA", "HTTPS", "HTTP",
})
_AMOUNT_TOKEN = re.compile(r"\d+(?:K|M|TR|D)", re.I)  # «100K», «2TR» viết HOA không phải mã
_URL_SPAN = re.compile(r"https?://\S+")
_AMOUNT = r"(\d+(?:[.,]\d+)*)\s*(k|nghìn|ngàn|tr|triệu|m|đ|d|vnđ|vnd)?(?![a-zà-ỹ])"
_PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")
_MAX = re.compile(r"(?:tối đa|toi da|max)\s*:?\s*" + _AMOUNT, re.I)
_MIN = re.compile(r"(?:đơn\s*(?:tối thiểu|từ|tt)|don\s*(?:toi thieu|tu)|đtt|min)\s*:?\s*" + _AMOUNT, re.I)
_OFF_AMOUNT = re.compile(r"(?:giảm|giam|-)\s*:?\s*" + _AMOUNT, re.I)
_UNITS = {"k": 1_000, "nghìn": 1_000, "ngàn": 1_000, "tr": 1_000_000, "triệu": 1_000_000, "m": 1_000_000}


def _vnd(number: str, unit: str | None) -> int:
    """«50k» → 50000, «1,5tr» → 1500000, «199.000đ» → 199000."""
    unit = (unit or "").lower()
    if unit in _UNITS:
        return int(round(float(number.replace(",", ".")) * _UNITS[unit]))
    return int(re.sub(r"[.,]", "", number))


def extract_voucher_codes(text: str) -> list[dict]:
    """Bóc các mã giảm giá trong một bài tổng hợp, mỗi mã một dict theo thứ tự xuất hiện (bỏ mã trùng).

    Điều kiện của mã lấy trong đoạn của mã đó: từ đầu dòng (mã đứng sau trên cùng dòng: từ chính mã) tới trước mã
    kế tiếp; dòng không có mã thì thuộc mã phía trên. Khoá: code, discount (chữ gốc «15%» / «50k»),
    discount_percent, discount_vnd, max_discount_vnd, min_spend_vnd (None khi bài không ghi).
    """
    text = text or ""
    scan = _URL_SPAN.sub(lambda m: " " * len(m.group()), text)  # mã trong URL không tính, giữ nguyên vị trí
    hits = [m for m in _CODE.finditer(scan)
            if m.group() not in _NOT_CODES and not _AMOUNT_TOKEN.fullmatch(m.group())]
    found: list[dict] = []
    seen: set[str] = set()
    for index, hit in enumerate(hits):
        line_start = scan.rfind("\n", 0, hit.start()) + 1
        previous = hits[index - 1] if index else None
        start = hit.start() if previous and previous.end() > line_start else line_start
        following = hits[index + 1] if index + 1 < len(hits) else None
        if following is None:
            end = len(scan)
        else:
            next_line = scan.rfind("\n", 0, following.start()) + 1
            end = following.start() if next_line <= hit.start() else next_line
        segment = scan[start:end].replace(hit.group(), " ")
        if hit.group() in seen:
            continue
        seen.add(hit.group())
        maximum, minimum = _MAX.search(segment), _MIN.search(segment)
        rest = segment
        for labelled in (maximum, minimum):
            if labelled:  # số «tối đa» / «đơn từ» không phải mức giảm
                rest = rest.replace(labelled.group(), " ")
        percent = _PERCENT.search(rest)
        off = None if percent else _OFF_AMOUNT.search(rest)
        found.append({
            "code": hit.group(),
            "discount": percent.group().replace(" ", "") if percent else
            (off.group(1) + (off.group(2) or "") if off else None),
            "discount_percent": float(percent.group(1).replace(",", ".")) if percent else None,
            "discount_vnd": _vnd(off.group(1), off.group(2)) if off else None,
            "max_discount_vnd": _vnd(maximum.group(1), maximum.group(2)) if maximum else None,
            "min_spend_vnd": _vnd(minimum.group(1), minimum.group(2)) if minimum else None,
        })
    return found


def process_post_content(post: dict[str, Any], affiliate_id: str) -> tuple[str, str | None, list[dict]]:
    """Thay thế link trong bài thành link Affiliate và dựng inline keyboard."""
    text = post["text"]
    old_links = post.get("shopee_links", [])

    if not old_links:
        return text, None, []

    bounded_links = old_links[:10]

    if len(bounded_links) == 1:
        link_map = {bounded_links[0]: _resolve(bounded_links[0], affiliate_id)}
    else:
        link_map = dict(zip(bounded_links, _POOL.map(lambda lnk: _resolve(lnk, affiliate_id), bounded_links)))

    # Một lượt thay: link mới chèn vào không bị link cũ ngắn hơn thay tiếp.
    pattern = re.compile("|".join(map(re.escape, sorted(link_map, key=len, reverse=True))))
    text = pattern.sub(lambda m: link_map[m.group(0)], text)

    # Nút bấm mở Shopee (chỉ hiện nút nếu bài có ít hơn 4 link, nếu bài quá nhiều link thì để link trong bài cho gọn)
    buttons: list[list[dict]] = []
    first_link = list(link_map.values())[0] if link_map else None
    if first_link and len(link_map) <= 3:
        lowered = text.lower()
        is_voucher = any(k in lowered for k in _LABEL_WORDS)
        label = "🎟 Lưu mã trên Shopee ↗" if is_voucher else "🛒 Mua ngay trên Shopee ↗"
        buttons.append([{"text": label, "url": first_link}])

    return text, first_link, buttons


def post_html(text: str, buttons: list[list[dict]] | None) -> str:
    """Bài relay → HTML Telegram gọn: không in URL an_redir dài giữa bài, chỉ giữ link Shopee.

    Link trùng nút bấm thì bỏ khỏi chữ (nút đã mở link đó); link Shopee khác thành <a href>«🔗 Lưu mã» /
    «🔗 Mua ngay»</a>. Link không phải Shopee (kể cả tên miền trần «nhomsansale.com/fb») bị bỏ cùng dòng chứa nó;
    cụm (ngăn bởi dòng trống / «.») có link mà không còn link Shopee nào thì bỏ cả cụm. Chữ còn lại escape như cũ.
    """
    button_urls = {b.get("url") for row in buttons or [] for b in row if isinstance(b, dict) and b.get("url")}
    label = "🔗 Lưu mã" if any(k in text.lower() for k in _LABEL_WORDS) else "🔗 Mua ngay"
    separators = ("", ".")
    groups: list[list[str]] = [[]]  # các cụm dòng; mỗi dòng ngăn cụm đứng riêng một cụm
    for raw in text.split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", raw).strip()
        if line in separators:
            groups += [[line], []]
        else:
            groups[-1].append(line)
    out: list[str] = []
    for group in groups:
        if group and group[0] in separators:
            if out and out[-1] not in separators:
                out.append(group[0])
            continue
        kept: list[str] = []
        linked = has_shopee = False
        for line in group:
            rendered, shopee, other = _render_line(line, button_urls, label)
            linked = linked or shopee or other
            has_shopee = has_shopee or shopee
            if other and not shopee:
                continue
            kept.append(re.sub(r"[ \t]{2,}", " ", rendered).strip())
        if has_shopee or not linked:
            out.extend(kept)
    while out and out[-1] in separators:
        out.pop()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _render_line(line: str, button_urls: set, label: str) -> tuple[str, bool, bool]:
    """(HTML của dòng, có link Shopee, có link khác). Link Shopee trùng nút thì bỏ khỏi chữ nhưng vẫn tính là Shopee."""
    parts: list[str] = []
    shopee = other = False
    last = 0
    for found in _ANY_LINK.finditer(line):
        token = found.group()
        url = token.rstrip(".,)")
        parts.append(html.escape(line[last:found.start()]))
        full = url if url.lower().startswith(("http://", "https://")) else "https://" + url
        if _is_shopee_url_candidate(full):
            shopee = True
            if full != url:
                parts.append(html.escape(url))  # tên miền trần Shopee: để nguyên chữ như trước (chưa bọc affiliate)
            elif url not in button_urls:
                parts.append(f'<a href="{html.escape(url, quote=True)}">{label}</a>')
        else:
            other = True
        parts.append(html.escape(token[len(url):]))
        last = found.end()
    parts.append(html.escape(line[last:]))
    return "".join(parts), shopee, other


def _download_safe_photo(photo_url: str) -> bytes | None:
    """Tải ảnh an toàn bằng streaming, kiểm soát Content-Length và chống OOM/DoS."""
    if not is_safe_photo_url(photo_url):
        return None
    try:
        with requests.get(
            photo_url,
            headers={"User-Agent": "Mozilla/5.0"},
            stream=True,
            timeout=(3.0, 5.0),
        ) as resp:
            if resp.status_code != 200:
                return None
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit() and int(cl) > MAX_IMAGE_BYTES:
                logger.warning("[SaleRelay] Photo Content-Length %s exceeds %s", cl, MAX_IMAGE_BYTES)
                return None
            content = bytearray()
            for chunk in resp.iter_content(chunk_size=65536):
                content.extend(chunk)
                if len(content) > MAX_IMAGE_BYTES:
                    logger.warning("[SaleRelay] Photo exceeded MAX_IMAGE_BYTES %s", MAX_IMAGE_BYTES)
                    return None
            return bytes(content)
    except Exception as exc:
        logger.debug("[SaleRelay] Download photo error: %s", exc)
        return None


def send_to_channel(
    telegram: TelegramApi,
    channel_id: int,
    text: str,
    photo_url: str | None,
    buttons: list[list[dict]],
) -> bool:
    """Gửi bài vào kênh Telegram trung gian (kèm ảnh và nút nếu có)."""
    markup = {"inline_keyboard": buttons} if buttons else None
    safe_text = post_html(text, buttons)

    # Nếu bài dài hơn 1000 ký tự (bài tổng hợp khung giờ), ưu tiên gửi tin nhắn chữ đầy đủ (tối đa 4000 ký tự)
    if len(safe_text) > 1000:
        try:
            telegram.send_message(channel_id, fit_html(safe_text, 4000), reply_markup=markup)
            return True
        except Exception as exc:
            logger.warning("[SaleRelay] sendMessage long text error: %s", exc)
            return False

    if photo_url:
        img_bytes = _download_safe_photo(photo_url)
        if img_bytes:
            try:
                data = {
                    "chat_id": channel_id,
                    "caption": fit_html(safe_text, 1000),
                    "parse_mode": "HTML",
                }
                if markup:
                    data["reply_markup"] = json.dumps(markup)
                files = {"photo": ("image.jpg", img_bytes, "image/jpeg")}
                resp = requests.post(
                    f"{telegram._base}/sendPhoto",
                    data=data,
                    files=files,
                    timeout=telegram._timeout,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
            except Exception as exc:
                logger.debug("[SaleRelay] sendPhoto error: %s, fallback to text", exc)

    # Fallback gửi tin nhắn chữ
    try:
        telegram.send_message(channel_id, fit_html(safe_text, 4000), reply_markup=markup)
        return True
    except Exception as exc:
        logger.warning("[SaleRelay] sendMessage error: %s", exc)
        return False


def get_subscribers(repo: TrackingRepository) -> list[int]:
    """Danh sách user đang bật nhận tin mã giảm giá."""
    from cashback_bot.voucher import subscribers
    with repo.connect() as conn:
        return subscribers(conn, datetime.now(timezone.utc))


def enqueue_for_subscribers(
    repo: TrackingRepository,
    post_id: int,
    text: str,
    buttons: list[list[dict]],
    subscribers: list[int],
) -> int:
    """Xếp hàng tin nhắn gửi riêng cho từng khách."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    markup_json = json.dumps({"inline_keyboard": buttons}, ensure_ascii=False) if buttons else None
    message_html = fit_html(post_html(text, buttons), 4000)
    queued = 0

    with repo.connect() as conn:
        for user_id in subscribers:
            event_key = f"relay:{post_id}:{user_id}"
            if enqueue_event(
                conn,
                event_key=event_key,
                event_type="VOUCHER",
                chat_id=user_id,
                message_html=message_html,
                audience="customer",
                category="voucher",
                reply_markup_json=markup_json,
                source_ref=f"relay:{post_id}",
                now=stamp,
            ):
                queued += 1
    return queued


# In-memory timestamp theo dõi lần quét cuối
_LAST_TICK: float = 0.0


def tick(repo: TrackingRepository, telegram: TelegramApi, affiliate_id: str | None) -> threading.Thread | None:
    """Gọi mỗi vòng poll. Tới lượt (POLL_INTERVAL_SEC) và chưa có lượt nào đang chạy thì quét trong luồng nền:
    tải trang kênh, mở link, tải ảnh không chặn vòng lặp nhận tin của bot."""
    global _LAST_TICK
    now_ts = time.time()
    if not affiliate_id or now_ts - _LAST_TICK < POLL_INTERVAL_SEC or not _running.acquire(blocking=False):
        return None
    _LAST_TICK = now_ts

    def work() -> None:
        try:
            run_once(repo, telegram, affiliate_id)
        except Exception as exc:
            logger.warning("[SaleRelay] tick unexpected error: %s", exc)
        finally:
            _running.release()

    thread = threading.Thread(target=work, name="sale-relay", daemon=True)
    thread.start()
    return thread


def run_once(repo: TrackingRepository, telegram: TelegramApi, affiliate_id: str) -> None:
    """Một lượt quét mọi kênh nguồn (chạy đồng bộ). Cache DNS và link chỉ sống trong lượt này."""
    global _RUN
    # Lấy kênh đích: mặc định kênh ZT báo mã
    raw_channel = repo.get_state("voucher_channel") or "-1004496405998"
    try:
        target_channel_id = int(raw_channel)
    except ValueError:
        return
    _RUN = {"dns": {}, "links": {}}
    try:
        for chan in DEFAULT_CHANNELS:
            try:
                _scan_channel(chan, repo, telegram, affiliate_id, target_channel_id)
            except Exception as exc:
                logger.warning("[SaleRelay] Scan %s error: %s", chan, exc)
    finally:
        _RUN = None


def source_channel_id(channel_name: str) -> int:
    """channel_id của kênh nguồn trong voucher_posts: số âm 10 chữ số, không trùng id kênh Telegram thật (-100…)."""
    return -(zlib.crc32(channel_name.encode()) or 1)


def store_codes(repo: TrackingRepository, channel_name: str, post_id: int, text: str, url: str | None,
                now: datetime | None = None) -> int:
    """Ghi các mã bóc từ bài (extract_voucher_codes) vào voucher_posts để /magiam hiện. Trả số mã đã ghi.

    sent = 0: voucher.tick không gửi lại (relay đã tự xếp hàng gửi khách). Mã đã có trong 24 giờ qua (AddLiveTag
    hoặc bài trước) thì giữ bản cũ, kể cả trạng thái hết mã.
    """
    codes = extract_voucher_codes(text)[:CODES_PER_POST]
    if not codes:
        return 0
    moment = now or datetime.now(timezone.utc)
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    since = (moment - CODE_FRESH_FOR).strftime("%Y-%m-%dT%H:%M:%SZ")
    channel_id = source_channel_id(channel_name)
    saved = 0
    with repo.connect() as conn:
        for index, found in enumerate(codes):
            if conn.execute("SELECT 1 FROM voucher_posts WHERE code = ? AND created_at >= ? LIMIT 1",
                            (found["code"], since)).fetchone():
                continue
            cursor = conn.execute(
                "INSERT OR IGNORE INTO voucher_posts (channel_id, message_id, code, name, discount, max_discount, "
                "min_spend, used_percent, url, status, created_at, updated_at) "
                "VALUES (?, ?, ?, '', ?, ?, ?, NULL, ?, 'live', ?, ?)",
                (channel_id, post_id * 100 + index, found["code"], found["discount"] or "",
                 "" if found["max_discount_vnd"] is None else format_vnd(found["max_discount_vnd"]),
                 "" if found["min_spend_vnd"] is None else format_vnd(found["min_spend_vnd"]),
                 url, stamp, stamp))
            saved += cursor.rowcount
    return saved


def _scan_channel(
    channel_name: str,
    repo: TrackingRepository,
    telegram: TelegramApi,
    affiliate_id: str,
    target_channel_id: int,
) -> None:
    state_key = f"relay_seen:{channel_name}"
    last_id_str = repo.get_state(state_key)
    last_id = int(last_id_str) if last_id_str and last_id_str.isdigit() else None

    url = f"https://t.me/s/{channel_name}"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        return

    posts = parse_channel_html(resp.text)
    if not posts:
        return

    # Lần đầu tiên chạy: chỉ lưu ID lớn nhất hiện tại, không gửi ồ ạt các tin cũ trong lịch sử
    if last_id is None:
        max_id = max(p["id"] for p in posts)
        repo.set_state(state_key, str(max_id))
        logger.info("[SaleRelay] Khởi tạo kênh %s với post_id=%s", channel_name, max_id)
        return

    new_posts = [p for p in posts if p["id"] > last_id]
    if not new_posts:
        return

    # Sắp xếp từ cũ đến mới để đăng đúng thứ tự
    new_posts.sort(key=lambda p: p["id"])

    # Lấy danh sách khách đăng ký nhận tin
    subs = get_subscribers(repo)

    for post in new_posts:
        text, first_link, buttons = process_post_content(post, affiliate_id)
        try:
            # Bài một link: link lưu mã là link đó; bài nhiều link không biết link nào của mã nào, để trống.
            store_codes(repo, channel_name, post["id"], post["text"],
                        first_link if len(post.get("shopee_links") or []) == 1 else None)
        except Exception as exc:
            logger.warning("[SaleRelay] store_codes error for post %s: %s", post["id"], exc)
        if not first_link:
            repo.set_state(state_key, str(post["id"]))
            continue

        sent_ok = False
        try:
            # 1. Đăng vào kênh trung gian (ZT báo mã)
            sent_ok = send_to_channel(telegram, target_channel_id, text, post["photo_url"], buttons)
        except Exception as exc:
            logger.warning("[SaleRelay] send_to_channel error for post %s: %s", post["id"], exc)

        # 2. Nếu là tin mã giảm giá / voucher hot -> xếp hàng gửi riêng cho khách
        lowered = text.lower()
        is_voucher = any(k in lowered for k in _SEND_WORDS)
        if is_voucher and subs:
            try:
                enqueue_for_subscribers(repo, post["id"], text, buttons, subs)
            except Exception as exc:
                logger.warning("[SaleRelay] enqueue_for_subscribers error for post %s: %s", post["id"], exc)

        # Cập nhật post_id đã xử lý để tránh phát lại trùng lặp ở chu kỳ sau
        repo.set_state(state_key, str(post["id"]))
        logger.info("[SaleRelay] Đã chuyển tiếp bài %s từ %s (sent_ok=%s)", post["id"], channel_name, sent_ok)
