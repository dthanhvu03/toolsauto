"""Client gọi API nội bộ affiliate.shopee.vn bằng Cookie (PLAN-065).

Chỉ gọi khi có Cookie xác thực từ Admin.
Không bao giờ ghi cookie thô vào log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from cashback_bot.shopee_cookie import cookies_to_header

logger = logging.getLogger(__name__)

USER_STATUS_URL = "https://affiliate.shopee.vn/api/v3/user/status"
CLICK_REPORT_URL = "https://affiliate.shopee.vn/api/v1/click_report/list"
CONVERSION_REPORT_URL = "https://affiliate.shopee.vn/api/v3/report/list"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://affiliate.shopee.vn/",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}


# PLAN-080: loại lỗi. Chỉ AUTH_EXPIRED khi có căn cứ (401, hoặc user/status từ chối phiên); 403 không kèm dấu hiệu
# đăng nhập là ACCESS_DENIED; trang xác minh / CAPTCHA là CHALLENGE (admin xử lý, bot không tự vượt).
AUTH_EXPIRED = "AUTH_EXPIRED"
ACCESS_DENIED = "ACCESS_DENIED"
CHALLENGE = "CHALLENGE"
RATE_LIMITED = "RATE_LIMITED"
NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
NETWORK_ERROR = "NETWORK_ERROR"
TRANSIENT_SERVER_ERROR = "TRANSIENT_SERVER_ERROR"
PARSE_ERROR = "PARSE_ERROR"
UNKNOWN_ERROR = "UNKNOWN_ERROR"
# Cần admin xem phiên / quyền: dừng tự đồng bộ, không thử lại như lỗi mạng.
NEEDS_AUTH_CATEGORIES = frozenset({AUTH_EXPIRED, ACCESS_DENIED, CHALLENGE})
# Lỗi tạm: thử lại có giới hạn trong lượt, rồi lượt sau.
TRANSIENT_CATEGORIES = frozenset({NETWORK_TIMEOUT, NETWORK_ERROR, TRANSIENT_SERVER_ERROR})
_CHALLENGE_MARKERS = ("captcha", "verify", "xác minh", "challenge")


class ShopeeApiError(Exception):
    def __init__(self, message: str, status_code: int = 0, code: int | None = None,
                 category: str = UNKNOWN_ERROR, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.category = category
        self.retry_after = retry_after


def _retry_after(resp) -> int | None:
    try:
        value = int(str(resp.headers.get("Retry-After", "")).strip())
    except (AttributeError, TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _looks_like_challenge(resp) -> bool:
    try:
        text = str(resp.text or "")[:2000].lower()
    except Exception:
        return False
    return any(marker in text for marker in _CHALLENGE_MARKERS)


def classify_http(resp) -> str | None:
    """Loại lỗi theo HTTP status (None khi 2xx/3xx). Không đọc hay ghi cookie / header."""
    code = resp.status_code
    if code == 401:
        return AUTH_EXPIRED
    if code == 403:
        return CHALLENGE if _looks_like_challenge(resp) else ACCESS_DENIED
    if code == 429:
        return RATE_LIMITED
    if code >= 500:
        return TRANSIENT_SERVER_ERROR
    if code >= 400:
        return UNKNOWN_ERROR
    return None


def classify_exception(exc: requests.RequestException) -> str:
    return NETWORK_TIMEOUT if isinstance(exc, requests.Timeout) else NETWORK_ERROR


@dataclass(frozen=True)
class ShopeeStatusResult:
    ok: bool
    status_code: int
    allow_to_login: bool = False
    username: str = ""
    error_message: str = ""
    raw_data: dict[str, Any] | None = None
    # True khi Shopee từ chối phiên (cookie hết hạn). Lỗi mạng, HTTP 5xx, 429 là lỗi tạm, để False.
    auth_failed: bool = False
    category: str | None = None
    retry_after: int | None = None


class ShopeeAffiliateClient:
    def __init__(self, cookies: dict[str, str], timeout: float = 20.0):
        self._cookie_header = cookies_to_header(cookies)
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = dict(DEFAULT_HEADERS)
        headers["Cookie"] = self._cookie_header
        return headers

    def check_status(self) -> ShopeeStatusResult:
        """Kiểm tra tính hợp lệ của Cookie qua endpoint /api/v3/user/status."""
        try:
            resp = requests.get(USER_STATUS_URL, headers=self._headers(), timeout=self._timeout)
        except requests.RequestException as exc:
            logger.warning("[ShopeeAffiliate] Lỗi kết nối check_status: %s", type(exc).__name__)
            return ShopeeStatusResult(ok=False, status_code=0, error_message=f"Lỗi kết nối: {type(exc).__name__}",
                                      category=classify_exception(exc))

        category = classify_http(resp)
        if category in NEEDS_AUTH_CATEGORIES:
            # user/status chỉ dùng để kiểm tra phiên: 401/403 ở đây là phiên bị từ chối.
            return ShopeeStatusResult(
                ok=False,
                status_code=resp.status_code,
                error_message=f"Cookie hết hạn hoặc không có quyền (HTTP {resp.status_code})",
                auth_failed=True,
                category=CHALLENGE if category == CHALLENGE else AUTH_EXPIRED,
            )

        if category is not None:
            return ShopeeStatusResult(
                ok=False,
                status_code=resp.status_code,
                error_message=f"Shopee trả về lỗi HTTP {resp.status_code}",
                category=category,
                retry_after=_retry_after(resp) if category == RATE_LIMITED else None,
            )

        try:
            payload = resp.json()
        except ValueError:
            return ShopeeStatusResult(ok=False, status_code=resp.status_code, error_message="Response không phải JSON hợp lệ",
                                      category=CHALLENGE if _looks_like_challenge(resp) else PARSE_ERROR)

        if not isinstance(payload, dict):
            return ShopeeStatusResult(ok=False, status_code=resp.status_code, error_message="Response format không đúng",
                                      category=PARSE_ERROR)

        code = payload.get("code")
        if code != 0:
            msg = payload.get("message") or f"Lỗi code={code}"
            return ShopeeStatusResult(ok=False, status_code=resp.status_code, error_message=str(msg), auth_failed=True,
                                      category=AUTH_EXPIRED)

        data = payload.get("data")
        if not isinstance(data, dict):
            return ShopeeStatusResult(ok=True, status_code=resp.status_code, allow_to_login=True)

        allow = bool(data.get("allow_to_login", True))
        # user/status không trả username; affiliate_id là thứ admin thấy trên trang Shopee.
        affiliate_id = data.get("affiliate_id")
        username = str(data.get("username") or (f"ID {affiliate_id}" if affiliate_id else ""))
        return ShopeeStatusResult(
            ok=allow,
            status_code=resp.status_code,
            allow_to_login=allow,
            username=username,
            error_message="" if allow else "Tài khoản bị tạm khóa hoặc không được phép đăng nhập",
            raw_data=data,
            auth_failed=not allow,
            category=None if allow else ACCESS_DENIED,
        )

    def _report(self, url: str, params: dict, what: str) -> dict[str, Any]:
        """Một trang báo cáo. Lỗi ném ShopeeApiError có loại; không ghi cookie hay header vào thông báo lỗi."""
        try:
            resp = requests.get(url, params=params, headers=self._headers(), timeout=self._timeout)
        except requests.RequestException as exc:
            raise ShopeeApiError(f"Lỗi mạng khi lấy {what}: {type(exc).__name__}",
                                 category=classify_exception(exc)) from exc

        category = classify_http(resp)
        if category == AUTH_EXPIRED:
            raise ShopeeApiError("Cookie hết hạn", status_code=resp.status_code, category=category)
        if category is not None:
            raise ShopeeApiError(f"Shopee HTTP {resp.status_code}", status_code=resp.status_code, category=category,
                                 retry_after=_retry_after(resp) if category == RATE_LIMITED else None)

        try:
            payload = resp.json()
        except ValueError as exc:
            raise ShopeeApiError("Response không phải JSON",
                                 category=CHALLENGE if _looks_like_challenge(resp) else PARSE_ERROR) from exc

        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise ShopeeApiError(str(payload.get("message") or f"Lỗi API {what}"), code=payload.get("code"))
        return payload

    def fetch_clicks(
        self,
        start_time: int,
        end_time: int,
        page_no: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Lấy danh sách click từ /api/v1/click_report/list.

        Tên tham số đã đối chiếu với response thật 2026-10-23; sai tên thì Shopee trả HTTP 400.
        """
        params = {
            "click_time_s": start_time,
            "click_time_e": end_time,
            "page_num": page_no,
            "page_size": page_size,
        }
        return self._report(CLICK_REPORT_URL, params, "click")

    def fetch_conversions(
        self,
        start_time: int,
        end_time: int,
        page_no: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Lấy danh sách conversion từ /api/v3/report/list (lọc theo giờ đặt hàng)."""
        params = {
            "purchase_time_s": start_time,
            "purchase_time_e": end_time,
            "page_num": page_no,
            "page_size": page_size,
            "version": 1,
        }
        return self._report(CONVERSION_REPORT_URL, params, "conversion")
