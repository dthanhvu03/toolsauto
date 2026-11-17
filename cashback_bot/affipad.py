"""AffiPad: ký Meta FB/IG lên link affiliate của mình (PLAN-174).

Hướng đã POC + owner confirm 17/11: ``s.shopee.vn/XXXX`` (bridge + sub_id mình)
→ ``POST /v1/convert`` ``trackingOnly`` + preset ``fb_reels`` → ``s.shopee.vn/XXXX?Meta…``
(form giống bot cạnh, hiện voucher). Fallback: ký thẳng ``an_redir`` nếu bridge tắt.

Không dùng ``convert`` thường (trả s.afp.ad, lệch affiliate).
Lỗi mạng / quota / 4xx → trả None; caller giữ an_redir thường. Không log chữ ký đầy đủ.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.affipad.com"
DEFAULT_TIMEOUT = 20.0
META_MARKERS = ("fb_content_id", "encrypted_payload", "sm_sig_id")


def is_meta_signed(url: str) -> bool:
    """URL đã mang chữ ký Meta — không được rút gọn / strip query."""
    try:
        q = parse_qs(urlparse(url).query)
    except Exception:
        return False
    return any(k in q for k in META_MARKERS)


def meta_channel(url: str) -> str | None:
    """Trả 'fb' / 'ig' từ query channel_type; không có → None."""
    try:
        values = parse_qs(urlparse(url).query).get("channel_type") or []
    except Exception:
        return None
    channel = (values[0] or "").strip().lower()
    return channel if channel in {"fb", "ig"} else None


def pick_tracking_preset(mode: str, *, salt: str = "") -> str:
    """rotate → xen kẽ fb_reels/ig_reels theo salt; còn lại trả đúng preset."""
    normalized = (mode or "rotate").strip().lower()
    if normalized in {"fb_reels", "fb"}:
        return "fb_reels"
    if normalized in {"ig_reels", "ig"}:
        return "ig_reels"
    return "ig_reels" if (sum(ord(c) for c in (salt or "")) % 2) else "fb_reels"


class AffiPadClient:
    """Client mỏng; truyền api_key + tool_id từ Settings."""

    def __init__(
        self,
        api_key: str,
        tool_id: str,
        *,
        session: requests.Session | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        base_url: str = API_BASE,
    ):
        self.api_key = (api_key or "").strip()
        self.tool_id = (tool_id or "").strip()
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self._session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.tool_id)

    def sign_tracking_only(self, affiliate_url: str, *, preset: str = "fb_reels") -> str | None:
        """Ký Meta lên short opaque hoặc an_redir (đã gắn affiliate + sub_id). Thành công → URL mới; lỗi → None."""
        if not self.configured or not (affiliate_url or "").strip():
            return None
        if is_meta_signed(affiliate_url):
            return affiliate_url
        body: dict[str, Any] = {
            "url": affiliate_url.strip(),
            "toolId": self.tool_id,
            "trackingOnly": True,
            "useShortLink": False,
            "tracking": {"preset": preset},
        }
        try:
            response = self._session.post(
                f"{self.base_url}/v1/convert",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "ToolsAuto-Cashbot/1.0",
                },
                json=body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.warning("[AffiPad] convert transport: %s", type(exc).__name__)
            return None
        if response.status_code != 200:
            logger.warning("[AffiPad] convert HTTP %s", response.status_code)
            return None
        try:
            payload = response.json()
        except ValueError:
            logger.warning("[AffiPad] convert non-JSON")
            return None
        results = (payload.get("data") or {}).get("results") or payload.get("results") or []
        if not results:
            logger.warning("[AffiPad] convert empty results")
            return None
        link = (results[0].get("link") or results[0].get("url") or "").strip()
        if not link or not is_meta_signed(link):
            logger.warning("[AffiPad] convert missing Meta fields on result")
            return None
        return link
