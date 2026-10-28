"""Cấu hình bot bán hàng. Chỉ đọc biến STORE_*."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("Thiếu hoặc sai cấu hình: " + ", ".join(missing))


@dataclass(frozen=True)
class BankAccount:
    bin_code: str
    account_no: str
    owner: str
    bank_name: str


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    db_path: str = "./data/store.sqlite"
    shop_name: str = "Store"
    # Kênh đăng "HÀNG MỚI VỀ": @tenkenh hoặc -100…; trống thì không đăng.
    channel_id: str | None = None
    bank: BankAccount | None = None
    min_topup_vnd: int = 10_000
    # Mức giảm mặc định cho khóa API đại lý, đơn vị 1/10000 (200 = 2%).
    reseller_discount_bps: int = 200
    api_public_url: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = 8091
    # Khóa webhook SePay (Authorization: Apikey …). Trống thì tắt tự cộng tiền nạp.
    sepay_webhook_key: str | None = None
    max_order_quantity: int = 100
    # Liên hệ hỗ trợ hiện ở ☎️ Hỗ trợ. Trống thì dùng @username của admin.
    support_telegram: str = ""
    support_zalo: str = ""
    # Nguồn hàng FatCat Store. Không có khóa thì bot chỉ bán hàng tự nhập kho.
    fatcat_api_key: str | None = None
    fatcat_api_url: str = "https://api.fatcatstore.click"
    # Mức FatCat giảm cho khóa đại lý. Giá bán = giá FatCat cho mình ÷ (1 − mức này) = giá lẻ bên FatCat.
    fatcat_discount_bps: int = 200
    sync_seconds: int = 180
    # Đăng "HÀNG MỚI VỀ" khi một món FatCat tăng ít nhất chừng này (hoặc từ hết hàng có lại).
    restock_announce_min: int = 5


def default_dotenv() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def _ids(raw: str | None, key: str) -> frozenset[int]:
    found: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        piece = part.strip()
        if not piece:
            continue
        if not piece.lstrip("-").isdigit():
            raise ConfigError([key])
        found.add(int(piece))
    return frozenset(found)


def _bounded_int(env, key: str, default: int, low: int, high: int) -> int:
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


def _bank(env) -> BankAccount | None:
    keys = ("STORE_BANK_BIN", "STORE_BANK_ACCOUNT", "STORE_BANK_OWNER")
    values = [(env.get(key) or "").strip() for key in keys]
    if not any(values):
        return None
    missing = [key for key, value in zip(keys, values) if not value]
    if missing:
        raise ConfigError(missing)
    bin_code, account_no, owner = values
    if not (bin_code.isdigit() and len(bin_code) == 6):
        raise ConfigError(["STORE_BANK_BIN"])
    return BankAccount(bin_code, account_no, owner, (env.get("STORE_BANK_NAME") or "").strip())


def load_settings(environ: dict[str, str] | None = None, dotenv_path: Path | None = None) -> Settings:
    if dotenv_path is not None:
        load_dotenv(dotenv_path, override=False)
    env = os.environ if environ is None else environ

    missing = [key for key in ("STORE_BOT_TOKEN", "STORE_ADMIN_IDS") if not (env.get(key) or "").strip()]
    if missing:
        raise ConfigError(missing)
    admin_ids = _ids(env.get("STORE_ADMIN_IDS"), "STORE_ADMIN_IDS")
    if not admin_ids:
        raise ConfigError(["STORE_ADMIN_IDS"])

    return Settings(
        bot_token=env["STORE_BOT_TOKEN"].strip(),
        admin_ids=admin_ids,
        db_path=(env.get("STORE_DB_PATH") or "./data/store.sqlite").strip(),
        shop_name=(env.get("STORE_SHOP_NAME") or "Store").strip(),
        channel_id=(env.get("STORE_CHANNEL_ID") or "").strip() or None,
        bank=_bank(env),
        min_topup_vnd=_bounded_int(env, "STORE_MIN_TOPUP_VND", 10_000, 1_000, 100_000_000),
        reseller_discount_bps=_bounded_int(env, "STORE_RESELLER_DISCOUNT_BPS", 200, 0, 5_000),
        api_public_url=(env.get("STORE_API_PUBLIC_URL") or "").strip().rstrip("/"),
        api_host=(env.get("STORE_API_HOST") or "127.0.0.1").strip(),
        api_port=_bounded_int(env, "STORE_API_PORT", 8091, 1, 65535),
        sepay_webhook_key=(env.get("STORE_SEPAY_WEBHOOK_KEY") or "").strip() or None,
        max_order_quantity=_bounded_int(env, "STORE_MAX_ORDER_QUANTITY", 100, 1, 1000),
        support_telegram=(env.get("STORE_SUPPORT_TELEGRAM") or "").strip(),
        support_zalo=(env.get("STORE_SUPPORT_ZALO") or "").strip(),
        fatcat_api_key=(env.get("FATCAT_API_KEY") or "").strip() or None,
        fatcat_api_url=(env.get("FATCAT_API_URL") or "https://api.fatcatstore.click").strip().rstrip("/"),
        fatcat_discount_bps=_bounded_int(env, "FATCAT_DISCOUNT_BPS", 200, 0, 5_000),
        sync_seconds=_bounded_int(env, "STORE_SYNC_SECONDS", 180, 60, 3600),
        restock_announce_min=_bounded_int(env, "STORE_RESTOCK_ANNOUNCE_MIN", 5, 1, 10_000),
    )
