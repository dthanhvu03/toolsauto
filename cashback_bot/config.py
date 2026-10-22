"""Cấu hình cashback. Chỉ đọc biến CASHBACK_* / SHOPEE_AFFILIATE_ID / ADDLIVETAG_API_KEY."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# PRODUCT_MAX_AGE_HOURS là tuổi tối đa của lastUpdate, không phải chu kỳ làm mới.
# Tài liệu AddLiveTag nói cache khoảng 3 giờ. Bản dataSource=db vẫn được nhận
# nếu timestamp còn trong ngưỡng và không có warning.
# lastUpdate không có timezone. Code gắn UTC. Mốc 2026-10-21 05:56:19 khớp
# cửa sổ 3 giờ khi đọc UTC; nếu nguồn thật là ICT thì cùng mốc đã hơn 9 giờ.
DOCUMENTED_CACHE_HOURS = 3
LAST_UPDATE_TIMEZONE = "UTC"


class ConfigError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("Thiếu cấu hình: " + ", ".join(missing))


@dataclass(frozen=True)
class Settings:
    bot_token: str
    affiliate_id: str
    api_key: str
    cashback_rate_percent: int
    product_max_age_hours: int
    db_path: str
    customer_access_enabled: bool
    allowed_telegram_ids: frozenset[int]
    admin_notifications_enabled: bool
    admin_chat_id: int | None
    product_data_url: str = "https://data.addlivetag.com/product-data/product-data.php"
    user_rate_limit: int = 8
    user_rate_window_sec: int = 600
    user_cooldown_sec: int = 300
    delivery_max_attempts: int = 5
    delivery_backoff_sec: int = 30
    backup_dir: str = "./data/backups"
    backup_keep: int = 14


def _flag(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _allowed_ids(raw: str | None) -> frozenset[int]:
    found: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        piece = part.strip()
        if not piece:
            continue
        if not piece.isdigit():
            raise ConfigError(["CASHBACK_ALLOWED_TELEGRAM_IDS"])
        found.add(int(piece))
    return frozenset(found)


def load_settings(environ: dict[str, str] | None = None, dotenv_path: Path | None = None) -> Settings:
    if dotenv_path is not None:
        load_dotenv(dotenv_path, override=False)
    env = os.environ if environ is None else environ

    required = [
        "CASHBACK_BOT_TOKEN",
        "SHOPEE_AFFILIATE_ID",
        "ADDLIVETAG_API_KEY",
        "CASHBACK_RATE_PERCENT",
        "PRODUCT_MAX_AGE_HOURS",
    ]
    missing = [key for key in required if not (env.get(key) or "").strip()]
    if missing:
        raise ConfigError(missing)

    affiliate_id = env["SHOPEE_AFFILIATE_ID"].strip()
    if not affiliate_id.isdigit() or not 3 <= len(affiliate_id) <= 30:
        raise ConfigError(["SHOPEE_AFFILIATE_ID"])

    try:
        rate = int(env["CASHBACK_RATE_PERCENT"].strip())
        max_age = int(env["PRODUCT_MAX_AGE_HOURS"].strip())
    except ValueError as exc:
        raise ConfigError(["CASHBACK_RATE_PERCENT", "PRODUCT_MAX_AGE_HOURS"]) from exc
    if not 0 <= rate <= 100:
        raise ConfigError(["CASHBACK_RATE_PERCENT"])
    if not 1 <= max_age <= 168:
        raise ConfigError(["PRODUCT_MAX_AGE_HOURS"])

    db_path = (env.get("CASHBACK_DB_PATH") or "./data/cashback.sqlite").strip()
    user_rate_limit = _bounded_int(env, "CASHBACK_USER_RATE_LIMIT", 8, 0, 100)
    user_rate_window_sec = _bounded_int(env, "CASHBACK_USER_RATE_WINDOW_SEC", 600, 30, 86400)
    user_cooldown_sec = _bounded_int(env, "CASHBACK_USER_COOLDOWN_SEC", 300, 30, 86400)
    delivery_max_attempts = _bounded_int(env, "CASHBACK_DELIVERY_MAX_ATTEMPTS", 5, 1, 20)
    delivery_backoff_sec = _bounded_int(env, "CASHBACK_DELIVERY_BACKOFF_SEC", 30, 0, 3600)
    backup_keep = _bounded_int(env, "CASHBACK_BACKUP_KEEP", 14, 1, 100)
    backup_dir = (env.get("CASHBACK_BACKUP_DIR") or "./data/backups").strip()
    admin_enabled = _flag(env.get("CASHBACK_ADMIN_NOTIFICATIONS_ENABLED"))
    admin_chat_raw = (env.get("CASHBACK_ADMIN_CHAT_ID") or "").strip()
    admin_chat_id: int | None = None
    if admin_chat_raw:
        try:
            admin_chat_id = int(admin_chat_raw)
        except ValueError as exc:
            raise ConfigError(["CASHBACK_ADMIN_CHAT_ID"]) from exc
    if admin_enabled and admin_chat_id is None:
        raise ConfigError(["CASHBACK_ADMIN_CHAT_ID"])
    return Settings(
        bot_token=env["CASHBACK_BOT_TOKEN"].strip(),
        affiliate_id=affiliate_id,
        api_key=env["ADDLIVETAG_API_KEY"].strip(),
        cashback_rate_percent=rate,
        product_max_age_hours=max_age,
        db_path=db_path,
        customer_access_enabled=_flag(env.get("CUSTOMER_ACCESS_ENABLED")),
        allowed_telegram_ids=_allowed_ids(env.get("CASHBACK_ALLOWED_TELEGRAM_IDS")),
        admin_notifications_enabled=admin_enabled,
        admin_chat_id=admin_chat_id,
        user_rate_limit=user_rate_limit,
        user_rate_window_sec=user_rate_window_sec,
        user_cooldown_sec=user_cooldown_sec,
        delivery_max_attempts=delivery_max_attempts,
        delivery_backoff_sec=delivery_backoff_sec,
        backup_dir=backup_dir,
        backup_keep=backup_keep,
    )


def _bounded_int(env: dict[str, str], key: str, default: int, low: int, high: int) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError([key]) from exc
    if not low <= value <= high:
        raise ConfigError([key])
    return value
