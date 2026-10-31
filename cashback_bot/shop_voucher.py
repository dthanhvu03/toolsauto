"""Quét và hiển thị mã giảm giá của Shop khi khách gửi link (PLAN-105: Shop Vouchers).

- Mặc định TẮT (enabled chỉ khi repo.get_state('shop_voucher_enabled') == '1').
- Gọi bridge service nội bộ với timeout ngắn (1.0s) để tuyệt đối không làm nghẽn bot.
- Cache có giới hạn trong bộ nhớ (_MAX_CACHE_SIZE) để tối ưu RAM.
- Thoát lỗi an toàn (fail-open): nếu bridge không phản hồi, báo đúng thực tế ("Tạm thời chưa kiểm tra được...").
- Mọi dữ liệu ngoài đều được html.escape trước khi gửi qua Telegram/Zalo.
- Hỗ trợ nút mở trực tiếp trang Shop để lưu mã không cần copy ("🎟️ Mở Shop để Lưu Mã").
"""

from __future__ import annotations

import html
import logging
import os
import time
from typing import Any

import requests

from cashback_bot.affiliate import build_voucher_redir
from cashback_bot.messages import BotReply, fit_html

logger = logging.getLogger("cashback_bot")

VOUCHER_CALLBACK_PREFIX = "u:sv:"
ENABLED_KEY = "shop_voucher_enabled"
BRIDGE_URL = os.environ.get("SHOP_VOUCHER_BRIDGE_URL", "http://192.168.112.1:9224/api/shop_vouchers")
FALLBACK_BRIDGE_URL = "http://127.0.0.1:9224/api/shop_vouchers"
REQUEST_TIMEOUT_SEC = (0.5, 0.8)

# Bounded in-memory cache: shop_id -> (timestamp, seq, vouchers)
_CACHE: dict[str, tuple[float, int, list[dict[str, Any]]]] = {}
_CACHE_TTL = 3600  # 1 hour
_MAX_CACHE_SIZE = 500
_CACHE_SEQ: int = 0


def enabled(repo: Any) -> bool:
    """Mặc định TẮT. Chỉ bật khi admin cấu hình shop_voucher_enabled = '1'."""
    if not hasattr(repo, "get_state"):
        return False
    return repo.get_state(ENABLED_KEY) == "1"


def set_enabled(repo: Any, is_enabled: bool) -> None:
    """Admin bật/tắt tính năng trong bot_state."""
    if hasattr(repo, "set_state"):
        repo.set_state(ENABLED_KEY, "1" if is_enabled else "0")


def _cache_get(shop_id: str) -> list[dict[str, Any]] | None:
    global _CACHE_SEQ
    now = time.monotonic()
    if shop_id in _CACHE:
        ts, _, vouchers = _CACHE[shop_id]
        if now - ts < _CACHE_TTL:
            _CACHE_SEQ += 1
            _CACHE[shop_id] = (now, _CACHE_SEQ, vouchers)  # Refresh LRU access
            return vouchers
        _CACHE.pop(shop_id, None)
    return None


def _cache_set(shop_id: str, vouchers: list[dict[str, Any]]) -> None:
    global _CACHE_SEQ
    now = time.monotonic()
    if len(_CACHE) >= _MAX_CACHE_SIZE and shop_id not in _CACHE:
        # Evict oldest 20% of entries based on (ts, seq)
        oldest_keys = sorted(_CACHE.keys(), key=lambda k: (_CACHE[k][0], _CACHE[k][1]))[: max(1, _MAX_CACHE_SIZE // 5)]
        for k in oldest_keys:
            _CACHE.pop(k, None)
    _CACHE_SEQ += 1
    _CACHE[shop_id] = (now, _CACHE_SEQ, vouchers)


def fetch_shop_vouchers(
    shop_id: int | str,
    timeout: tuple[float, float] | float = REQUEST_TIMEOUT_SEC,
) -> tuple[bool, list[dict[str, Any]]]:
    """Lấy danh sách mã giảm giá của shop.

    Trả về tuple (thành_công, danh_sách_mã).
    Nếu bridge lỗi hoặc timeout -> (False, []).
    Nếu thành công và shop có mã -> (True, [vouchers...]).
    Nếu thành công nhưng shop không có mã -> (True, []).
    """
    shop_id_str = str(shop_id).strip()
    if not shop_id_str or not shop_id_str.isdigit():
        return False, []

    cached = _cache_get(shop_id_str)
    if cached is not None:
        return True, cached

    urls_to_try = [BRIDGE_URL]
    if BRIDGE_URL != FALLBACK_BRIDGE_URL:
        urls_to_try.append(FALLBACK_BRIDGE_URL)

    for url in urls_to_try:
        try:
            resp = requests.get(url, params={"shop_id": shop_id_str}, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                vouchers = data.get("vouchers", [])
                _cache_set(shop_id_str, vouchers)
                return True, vouchers
        except requests.RequestException as exc:
            logger.debug("[ShopVoucher] Connection failed to %s: %s", url, exc)
            continue
        except Exception as exc:
            logger.warning("[ShopVoucher] Unexpected error from %s: %s", url, exc)
            continue

    return False, []


def format_amount(raw: int | float | None) -> str:
    """Định dạng số tiền.

    Nếu là micro-units từ Shopee (>= 1.000.000.000) thì chia cho 100.000.
    Nếu là số tiền VND bình thường (< 1.000.000.000) thì giữ nguyên.
    """
    if raw is None or raw <= 0:
        return "0₫"
    val = int(raw // 100_000) if raw >= 1_000_000_000 else int(raw)
    return f"{val:,.0f}₫".replace(",", ".")


def format_vouchers_detail(shop_id: int | str, vouchers: list[dict[str, Any]]) -> str:
    """Hiển thị chi tiết toàn bộ mã giảm giá kèm bảo vệ HTML escape."""
    safe_shop_id = html.escape(str(shop_id))
    if not vouchers or not isinstance(vouchers, list):
        return (
            f"🎟️ <b>Shop {safe_shop_id} hiện chưa có mã giảm giá riêng.</b>\n\n"
            "Bạn vẫn được nhận tiền hoàn khi mua qua link bot nhé!"
        )

    lines = [
        f"🎟️ <b>MÃ GIẢM GIÁ TỪ SHOP (Shop ID: {safe_shop_id})</b>",
        "",
        "<i>Bấm nút bên dưới để mở Shopee và lưu mã với 1 chạm:</i>",
        "",
    ]

    for idx, v in enumerate(vouchers[:15], 1):
        if not isinstance(v, dict):
            continue
        try:
            pct = v.get("discount_percentage")
            val = v.get("discount_value")
            cap = v.get("discount_cap")
            min_spend = v.get("min_spend")
            raw_code = v.get("code") or ""
            safe_code = html.escape(str(raw_code))
            used = v.get("percentage_used")

            if pct is not None and isinstance(pct, (int, float)) and pct > 0:
                cap_str = f" (tối đa {format_amount(cap)})" if cap is not None and isinstance(cap, (int, float)) else ""
                desc = f"<b>Giảm {int(pct)}%{cap_str}</b>"
            elif val is not None and isinstance(val, (int, float)) and val > 0:
                desc = f"<b>Giảm {format_amount(val)}</b>"
            else:
                desc = "<b>Mã ưu đãi đặc biệt</b>"

            meta = []
            if min_spend is not None and isinstance(min_spend, (int, float)):
                meta.append(f"Đơn tối thiểu {format_amount(min_spend)}")
            if used is not None and isinstance(used, (int, float)) and used > 0:
                meta.append(f"Đã dùng {int(used)}%")

            meta_str = " | ".join(meta)
            code_line = f" • Mã: <code>{safe_code}</code>" if safe_code else ""
            lines.append(f"{idx}. {desc}{code_line}")
            if meta_str:
                lines.append(f"   <i>({meta_str})</i>")
        except Exception as exc:
            logger.debug("[ShopVoucher] Format voucher entry error: %s", exc)
            continue

    lines.append("")
    lines.append("👉 <b>Mẹo:</b> Bấm nút 'Mở Shop để Lưu Mã' bên dưới để vào app lưu mã ngay không cần gõ!")
    return fit_html("\n".join(lines), limit=4000)


def card_row(shop_id: int | str | None, affiliate_id: str | None = None) -> tuple:
    """Trả về hàng nút bấm inline cho thẻ link mở thẳng Shop để lưu mã 1 chạm."""
    if not shop_id:
        return ()
    shop_id_str = str(shop_id).strip()
    if not shop_id_str.isdigit():
        return ()
    shop_url = f"https://shopee.vn/shop/{shop_id_str}"
    if affiliate_id and str(affiliate_id).isdigit():
        try:
            shop_url = build_voucher_redir(shop_url, str(affiliate_id))
        except Exception as exc:
            logger.debug("[ShopVoucher] Build affiliate url in card_row failed: %s", exc)
    return ((("🎟️ Mã giảm giá Shop", shop_url),),)


def action(repo: Any, user_id: int, callback_data: str, affiliate_id: str | None = None) -> BotReply:
    """Xử lý sự kiện khi khách bấm vào nút '🎟️ Mã giảm giá Shop'."""
    if not callback_data.startswith(VOUCHER_CALLBACK_PREFIX):
        return BotReply("")

    shop_id = callback_data[len(VOUCHER_CALLBACK_PREFIX):].strip()
    success, vouchers = fetch_shop_vouchers(shop_id, timeout=REQUEST_TIMEOUT_SEC)

    if not success:
        return BotReply(
            "",
            toast="Tạm thời chưa kiểm tra được mã shop, bạn xem trực tiếp trên app Shopee nhé!",
            show_alert=False,
        )

    # Tạo link mở thẳng Shop (qua link tiếp thị nếu có affiliate_id)
    shop_url = f"https://shopee.vn/shop/{shop_id}"
    if affiliate_id and str(affiliate_id).isdigit():
        try:
            shop_url = build_voucher_redir(shop_url, str(affiliate_id))
        except Exception as exc:
            logger.debug("[ShopVoucher] Build affiliate voucher url failed: %s", exc)

    if not vouchers:
        return BotReply(
            "",
            toast="Shop này hiện chưa có mã giảm giá riêng.",
            show_alert=False,
        )

    text = format_vouchers_detail(shop_id, vouchers)
    return BotReply(
        text=text,
        button_url=shop_url,
        button_label="🎟️ Mở Shop để Lưu Mã",
        toast=f"Tìm thấy {len(vouchers)} mã từ Shop!",
        show_alert=False,
    )
