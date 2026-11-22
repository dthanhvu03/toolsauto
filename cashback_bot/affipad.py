"""AffiPad: ký Meta FB/IG lên link affiliate của mình (PLAN-174).

Hướng đã POC + owner confirm 17/11: ``s.shopee.vn/XXXX`` (bridge + sub_id mình)
→ ``POST /v1/convert`` ``trackingOnly`` + preset ``fb_reels`` → ``s.shopee.vn/XXXX?Meta…``
(form giống bot cạnh, hiện voucher). Fallback: ký thẳng ``an_redir`` nếu bridge tắt.

Không dùng ``convert`` thường (trả s.afp.ad, lệch affiliate).
Lỗi mạng / quota / 4xx → trả None; caller giữ an_redir thường. Không log chữ ký đầy đủ.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from cashback_bot.deadline_http import DeadlineHttpError, request_bytes

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
    channel = (values[0] if values else "").strip().lower()
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

    def sign_tracking_only(
        self, affiliate_url: str, *, preset: str = "fb_reels", deadline: float | None = None,
    ) -> str | None:
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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ToolsAuto-Cashbot/1.0",
        }
        try:
            if deadline is not None:
                status, raw = request_bytes(
                    "POST", f"{self.base_url}/v1/convert", headers=headers,
                    body=json.dumps(body).encode("utf8"),
                    deadline=min(deadline, time.monotonic() + self.timeout),
                )
                if status != 200:
                    logger.warning("[AffiPad] convert HTTP %s", status)
                    return None
                payload = json.loads(raw)
            else:
                response = self._session.post(
                    f"{self.base_url}/v1/convert", headers=headers, json=body, timeout=self.timeout,
                )
                if response.status_code != 200:
                    logger.warning("[AffiPad] convert HTTP %s", response.status_code)
                    return None
                payload = response.json()
        except (requests.RequestException, DeadlineHttpError) as exc:
            logger.warning("[AffiPad] convert transport: %s", type(exc).__name__)
            return None
        except (ValueError, UnicodeError, RecursionError):
            logger.warning("[AffiPad] convert non-JSON")
            return None
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        results = data.get("results") if isinstance(data, dict) else None
        results = results or payload.get("results") or []
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            logger.warning("[AffiPad] convert empty or invalid results")
            return None
        link = results[0].get("link") or results[0].get("url") or ""
        if not isinstance(link, str):
            return None
        link = link.strip()
        if not link or not is_meta_signed(link):
            logger.warning("[AffiPad] convert missing Meta fields on result")
            return None
        return link
