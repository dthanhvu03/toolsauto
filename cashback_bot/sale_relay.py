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
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.telegram_api import TelegramApi

logger = logging.getLogger("cashback_bot")

DEFAULT_CHANNELS = ["nhomsansale"]
POLL_INTERVAL_SEC = 90  # 1.5 phút quét một lần
REQUEST_TIMEOUT = (3.0, 5.0)
SUB_ID = "AUTOSALE"
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

_ALLOWED_SHOPEE_HOSTS = frozenset({
    "shopee.vn",
    "www.shopee.vn",
    "s.shopee.vn",
    "shp.ee",
    "vn.shp.ee",
    "shope.ee",
})

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
        addrs = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True
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
        addrs = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True
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


def resolve_shopee_link(url: str, affiliate_id: str, sub_id: str = SUB_ID) -> str:
    """Lấy link đích thực tế và bọc bằng link Affiliate của mình."""
    if not affiliate_id or not affiliate_id.isdigit():
        return url

    current_url = url
    if current_url.startswith("http://"):
        parsed = urlparse(current_url)
        if _is_allowed_shopee_host((parsed.hostname or "").lower()):
            current_url = "https://" + current_url[7:]

    max_hops = 3
    for _ in range(max_hops):
        if not is_safe_shopee_url(current_url):
            return url

        try:
            resp = requests.head(
                current_url,
                allow_redirects=False,
                timeout=(2.0, 3.0),
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code in (301, 302, 303, 307, 308) and "Location" in resp.headers:
                next_url = resp.headers["Location"].strip()
                if not next_url.startswith(("http://", "https://")):
                    next_url = urljoin(current_url, next_url)
                if next_url.startswith("http://"):
                    p = urlparse(next_url)
                    if _is_allowed_shopee_host((p.hostname or "").lower()):
                        next_url = "https://" + next_url[7:]
                current_url = next_url
            else:
                break
        except Exception as exc:
            logger.debug("[SaleRelay] Resolve error on %s: %s", current_url, exc)
            break

    if not is_safe_shopee_url(current_url):
        return url

    unwrapped = _unwrap(current_url)
    clean = _clean_shopee_url(unwrapped)
    try:
        query = urlencode({"origin_link": clean, "affiliate_id": affiliate_id, "sub_id": sub_id})
        return f"https://s.shopee.vn/an_redir?{query}"
    except Exception:
        return url


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


def parse_channel_html(html_text: str) -> list[dict[str, Any]]:
    """Bóc tách các bài viết từ HTML của trang t.me/s/<channel>."""
    posts: list[dict[str, Any]] = []
    blocks = html_text.split("tgme_widget_message_wrap")
    for block in blocks[1:]:
        msg_id_match = re.search(r'data-post="[^"]+/(\d+)"', block)
        if not msg_id_match:
            continue
        msg_id = int(msg_id_match.group(1))

        # Photo
        photos = re.findall(r"background-image:url\('([^']+)'\)", block)
        photo_url = photos[0] if photos else None

        # Text
        text_match = re.search(r"tgme_widget_message_text[^>]*>(.*?)</div>", block, re.DOTALL)
        raw_html = text_match.group(1) if text_match else ""

        # Convert simple HTML tags to plain / standard
        clean_text = re.sub(r"<br\s*/?>", "\n", raw_html)
        clean_text = re.sub(r"<[^>]+>", " ", clean_text)
        clean_text = html.unescape(clean_text).strip()

        # Find raw links and strictly filter against allowed Shopee domains
        links = re.findall(r"https?://[^\s<>\"']+", raw_html + " " + clean_text)
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


def process_post_content(post: dict[str, Any], affiliate_id: str) -> tuple[str, str | None, list[dict]]:
    """Thay thế link trong bài thành link Affiliate và dựng inline keyboard."""
    text = post["text"]
    old_links = post.get("shopee_links", [])

    if not old_links:
        return text, None, []

    bounded_links = old_links[:10]

    link_map: dict[str, str] = {}
    if len(bounded_links) == 1:
        link_map[bounded_links[0]] = resolve_shopee_link(bounded_links[0], affiliate_id)
    else:
        max_workers = min(4, len(bounded_links))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            resolved = list(executor.map(lambda lnk: (lnk, resolve_shopee_link(lnk, affiliate_id)), bounded_links))
            link_map = dict(resolved)

    for old_link, new_link in sorted(link_map.items(), key=lambda kv: len(kv[0]), reverse=True):
        text = text.replace(old_link, new_link)

    # Nút bấm mở Shopee (chỉ hiện nút nếu bài có ít hơn 4 link, nếu bài quá nhiều link thì để link trong bài cho gọn)
    buttons: list[list[dict]] = []
    first_link = list(link_map.values())[0] if link_map else None
    if first_link and len(link_map) <= 3:
        is_voucher = any(k in text.lower() for k in ("mã", "voucher", "giảm", "lưu mã"))
        label = "🎟 Lưu mã trên Shopee ↗" if is_voucher else "🛒 Mua ngay trên Shopee ↗"
        buttons.append([{"text": label, "url": first_link}])

    return text, first_link, buttons


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
    safe_text = html.escape(text)

    # Nếu bài dài hơn 1000 ký tự (bài tổng hợp khung giờ), ưu tiên gửi tin nhắn chữ đầy đủ (tối đa 4000 ký tự)
    if len(text) > 1000:
        try:
            telegram.send_message(channel_id, safe_text[:4000], reply_markup=markup)
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
                    "caption": safe_text[:1000],
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
        telegram.send_message(channel_id, safe_text[:4000], reply_markup=markup)
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
    queued = 0

    with repo.connect() as conn:
        for user_id in subscribers:
            event_key = f"relay:{post_id}:{user_id}"
            if enqueue_event(
                conn,
                event_key=event_key,
                event_type="VOUCHER",
                chat_id=user_id,
                message_html=html.escape(text),
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


def tick(repo: TrackingRepository, telegram: TelegramApi, affiliate_id: str | None) -> None:
    """Hàm định kỳ được gọi trong vòng lặp chính của bot."""
    global _LAST_TICK
    try:
        now_ts = time.time()
        if now_ts - _LAST_TICK < POLL_INTERVAL_SEC:
            return
        _LAST_TICK = now_ts

        if not affiliate_id:
            return

        # Lấy kênh đích: mặc định kênh ZT báo mã
        raw_channel = repo.get_state("voucher_channel") or "-1004496405998"
        try:
            target_channel_id = int(raw_channel)
        except ValueError:
            return

        channels = DEFAULT_CHANNELS
        for chan in channels:
            try:
                _scan_channel(chan, repo, telegram, affiliate_id, target_channel_id)
            except Exception as exc:
                logger.warning("[SaleRelay] Scan %s error: %s", chan, exc)
    except Exception as exc:
        logger.warning("[SaleRelay] tick unexpected error: %s", exc)


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
        is_voucher = any(k in text.lower() for k in ("mã", "voucher", "giảm", "lưu mã", "hoàn xu"))
        if is_voucher and subs:
            try:
                enqueue_for_subscribers(repo, post["id"], text, buttons, subs)
            except Exception as exc:
                logger.warning("[SaleRelay] enqueue_for_subscribers error for post %s: %s", post["id"], exc)

        # Cập nhật post_id đã xử lý để tránh phát lại trùng lặp ở chu kỳ sau
        repo.set_state(state_key, str(post["id"]))
        logger.info("[SaleRelay] Đã chuyển tiếp bài %s từ %s (sent_ok=%s)", post["id"], channel_name, sent_ok)
