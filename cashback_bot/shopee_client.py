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


class ShopeeApiError(Exception):
    def __init__(self, message: str, status_code: int = 0, code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True)
class ShopeeStatusResult:
    ok: bool
    status_code: int
    allow_to_login: bool = False
    username: str = ""
    error_message: str = ""
    raw_data: dict[str, Any] | None = None


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
            return ShopeeStatusResult(ok=False, status_code=0, error_message=f"Lỗi kết nối: {type(exc).__name__}")

        if resp.status_code in (401, 403):
            return ShopeeStatusResult(
                ok=False,
                status_code=resp.status_code,
                error_message=f"Cookie hết hạn hoặc không có quyền (HTTP {resp.status_code})",
            )

        if resp.status_code >= 400:
            return ShopeeStatusResult(
                ok=False,
                status_code=resp.status_code,
                error_message=f"Shopee trả về lỗi HTTP {resp.status_code}",
            )

        try:
            payload = resp.json()
        except ValueError:
            return ShopeeStatusResult(ok=False, status_code=resp.status_code, error_message="Response không phải JSON hợp lệ")

        if not isinstance(payload, dict):
            return ShopeeStatusResult(ok=False, status_code=resp.status_code, error_message="Response format không đúng")

        code = payload.get("code")
        if code != 0:
            msg = payload.get("message") or f"Lỗi code={code}"
            return ShopeeStatusResult(ok=False, status_code=resp.status_code, error_message=str(msg))

        data = payload.get("data")
        if not isinstance(data, dict):
            return ShopeeStatusResult(ok=True, status_code=resp.status_code, allow_to_login=True)

        allow = bool(data.get("allow_to_login", True))
        username = str(data.get("username") or data.get("user_name") or "")
        return ShopeeStatusResult(
            ok=allow,
            status_code=resp.status_code,
            allow_to_login=allow,
            username=username,
            error_message="" if allow else "Tài khoản bị tạm khóa hoặc không được phép đăng nhập",
            raw_data=data,
        )

    def fetch_clicks(
        self,
        start_time: int,
        end_time: int,
        page_no: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Lấy danh sách click từ /api/v1/click_report/list."""
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "page_no": page_no,
            "page_size": page_size,
        }
        try:
            resp = requests.get(CLICK_REPORT_URL, params=params, headers=self._headers(), timeout=self._timeout)
        except requests.RequestException as exc:
            raise ShopeeApiError(f"Lỗi mạng khi lấy click: {type(exc).__name__}") from exc

        if resp.status_code in (401, 403):
            raise ShopeeApiError("Cookie hết hạn", status_code=resp.status_code)
        if resp.status_code >= 400:
            raise ShopeeApiError(f"Shopee HTTP {resp.status_code}", status_code=resp.status_code)

        try:
            payload = resp.json()
        except ValueError as exc:
            raise ShopeeApiError("Response không phải JSON") from exc

        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise ShopeeApiError(str(payload.get("message") or "Lỗi API click"), code=payload.get("code"))
        return payload

    def fetch_conversions(
        self,
        start_time: int,
        end_time: int,
        page_no: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Lấy danh sách conversion từ /api/v3/report/list."""
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "page_no": page_no,
            "page_size": page_size,
        }
        try:
            resp = requests.get(CONVERSION_REPORT_URL, params=params, headers=self._headers(), timeout=self._timeout)
        except requests.RequestException as exc:
            raise ShopeeApiError(f"Lỗi mạng khi lấy conversion: {type(exc).__name__}") from exc

        if resp.status_code in (401, 403):
            raise ShopeeApiError("Cookie hết hạn", status_code=resp.status_code)
        if resp.status_code >= 400:
            raise ShopeeApiError(f"Shopee HTTP {resp.status_code}", status_code=resp.status_code)

        try:
            payload = resp.json()
        except ValueError as exc:
            raise ShopeeApiError("Response không phải JSON") from exc

        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise ShopeeApiError(str(payload.get("message") or "Lỗi API conversion"), code=payload.get("code"))
        return payload
