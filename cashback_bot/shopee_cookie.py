"""Quản lý cookie Shopee Affiliate (PLAN-065).

Hỗ trợ:
- Xuất từ J2TEAM Cookies / Cookie-Editor (JSON mảng [{'name': '...', 'value': '...'}]).
- JSON object ({'cookies': [...]}) hoặc key-value.
- Chuỗi HTTP Cookie header: name=value; name2=value2.

Lưu tại storage/db/config/shopee_affiliate_cookies.json với quyền 0o600 (owner only).
Tuyệt đối không log chuỗi cookie thô.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_COOKIE_PATH = Path("storage/db/config/shopee_affiliate_cookies.json")


def parse_cookies(raw_text: str) -> dict[str, str]:
    """Parse cookie từ text J2TEAM Cookies JSON hoặc chuỗi header 'k=v; k2=v2'."""
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Nội dung cookie rỗng")

    cookies: dict[str, str] = {}

    # Thử parse JSON
    if (text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}")):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        name = item.get("name")
                        value = item.get("value")
                        if name and value is not None:
                            cookies[str(name).strip()] = str(value).strip()
            elif isinstance(parsed, dict):
                if "cookies" in parsed and isinstance(parsed["cookies"], list):
                    for item in parsed["cookies"]:
                        if isinstance(item, dict):
                            name = item.get("name")
                            value = item.get("value")
                            if name and value is not None:
                                cookies[str(name).strip()] = str(value).strip()
                else:
                    for k, v in parsed.items():
                        if isinstance(k, str) and v is not None and not isinstance(v, (list, dict)):
                            cookies[k.strip()] = str(v).strip()
        except json.JSONDecodeError:
            pass

    # Nếu không phải JSON hoặc chưa trích xuất được cookie nào, parse dạng name=value;
    if not cookies:
        for part in text.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, sep, value = part.partition("=")
            name = name.strip()
            value = value.strip()
            if name:
                cookies[name] = value

    if not cookies:
        raise ValueError("Không tìm thấy cookie hợp lệ từ dữ liệu nhập vào")

    return cookies


def save_cookies(cookies: dict[str, str], path: Path | str = DEFAULT_COOKIE_PATH) -> Path:
    """Lưu cookie vào file an toàn với phân quyền 0o600."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".tmp")
    with open(temp_target, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(temp_target, 0o600)
    except OSError as exc:
        logger.warning("[Cashback] Không thể đặt chmod 0600 cho cookie file: %s", exc)
    temp_target.replace(target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def load_cookies(path: Path | str = DEFAULT_COOKIE_PATH) -> dict[str, str] | None:
    """Đọc cookie đã lưu từ file. Trả về None nếu file chưa tồn tại."""
    target = Path(path)
    if not target.exists() or target.stat().st_size == 0:
        return None
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("[Cashback] Không thể đọc file cookie %s: %s", target, exc)
    return None


def cookies_to_header(cookies: dict[str, str]) -> str:
    """Chuyển dict cookie thành chuỗi Cookie HTTP Header."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())
