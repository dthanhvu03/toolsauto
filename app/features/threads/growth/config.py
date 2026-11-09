"""Cấu hình Threads Growth Agent (A/B Testing & Tracking cho Cashbot và AI Pass Store).

Hỗ trợ các biến thể (variants) tiếp cận khác nhau để đo lường tỷ lệ chuyển đổi
thông qua mã tham số `?start=<mã>` (PLAN-153, PLAN-097).

Phần chỉnh trên web (/app/settings → «Threads — Kéo khách», key ``growth.*``, mặc định nằm ở
``app/core/settings.py``): từ khóa, góc tiếp cận + câu mẫu A/B, hạn mức, tham số worker.
Giữ cố định trong code: handle bot, mã ``?start=`` (gắn tracking phía bot), tên biến thể.
"""

import logging
import os
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Dict, List

from app.core import settings

logger = logging.getLogger(__name__)


class TargetBot(str, Enum):
    CASHBOT = "cashbot"
    AI_STORE = "ai_store"


class ABVariant(str, Enum):
    VARIANT_A = "A"
    VARIANT_B = "B"


@dataclass(frozen=True)
class VariantConfig:
    variant: ABVariant
    code: str
    tracking_url: str
    name: str
    angle: str
    sample_hook: str


@dataclass(frozen=True)
class BotGrowthProfile:
    bot_type: TargetBot
    name: str
    handle: str
    base_url: str
    keywords: List[str]
    variants: Dict[ABVariant, VariantConfig]


# Phần cố định: (tên bot, handle, {biến thể: (mã start, tên biến thể)}).
_STATIC = {
    TargetBot.CASHBOT: (
        "Cashbot (Hoàn tiền Shopee & TikTok)",
        "zt_shopee_bot",
        {
            ABVariant.VARIANT_A: ("threads_cb_save", "Tiết kiệm & Hoàn tiền về tài khoản"),
            ABVariant.VARIANT_B: ("threads_cb_tier", "Săn Voucher & Hạng thành viên thưởng thêm"),
        },
    ),
    TargetBot.AI_STORE: (
        "AI Pass Store (Tài khoản AI & Tool bản quyền)",
        "aipass_shop_bot",
        {
            ABVariant.VARIANT_A: ("threads_ai_auto", "Cấp tài khoản tức thì 24/7 tự động"),
            ABVariant.VARIANT_B: ("threads_ai_price", "Giá sỉ tiết kiệm & Bảo hành 1 đổi 1"),
        },
    ),
}


# Kênh ngoài reply A/B (PLAN-159) — mỗi kênh một mã ``?start=`` để biết khách đến từ đâu.
CHANNELS = {"post": "bài riêng", "conv": "trả lời lại", "bio": "bio profile"}
_CHANNEL_PREFIX = {TargetBot.CASHBOT: "threads_cb_", TargetBot.AI_STORE: "threads_ai_"}


@dataclass(frozen=True)
class GrowthAccount:
    """Một tài khoản Threads kéo khách (PLAN-167). ``key`` ghi vào DB (cột ``account``) và nằm trong mã bio."""

    key: str
    handle: str
    profile: str  # thư mục trong storage/profiles


# Thứ tự = thứ tự hiện trên web. Tài khoản đầu là tài khoản worker đang chạy (session.PROFILE_DIR).
ACCOUNTS: Dict[str, GrowthAccount] = {
    "us28qt": GrowthAccount("us28qt", "us28qt", "instagram_5"),
    "anlinh": GrowthAccount("anlinh", "anlinh_08_10", "threads_anlinh"),
}
DEFAULT_ACCOUNT = "us28qt"  # mọi reply / bài riêng trước PLAN-167 đều do @us28qt đăng


def account_for_profile(profile_path: str) -> str:
    """Tài khoản ứng với thư mục profile worker đang mở; profile lạ → ``DEFAULT_ACCOUNT`` (kèm log)."""
    name = Path(str(profile_path or "")).name
    for acc in ACCOUNTS.values():
        if acc.profile == name:
            return acc.key
    logger.warning("growth: profile %r không có trong ACCOUNTS — ghi là %s", name, DEFAULT_ACCOUNT)
    return DEFAULT_ACCOUNT


def channel_code(bot: TargetBot, channel: str) -> str:
    return _CHANNEL_PREFIX[bot] + channel


def channel_url(bot: TargetBot, channel: str) -> str:
    return f"https://t.me/{_STATIC[bot][1]}?start={channel_code(bot, channel)}"


def bio_code(bot: TargetBot, account: str) -> str:
    """Mã link bio riêng từng tài khoản: ``threads_cb_bio_us28qt``, ``threads_ai_bio_anlinh``…"""
    return f"{channel_code(bot, 'bio')}_{account}"


def bio_url(bot: TargetBot, account: str) -> str:
    return f"https://t.me/{_STATIC[bot][1]}?start={bio_code(bot, account)}"


def code_map() -> Dict[str, tuple]:
    """Mã ``?start=`` → (bot, biến thể, tài khoản). Biến thể None với mã kênh (bài riêng / trả lời lại / bio).

    Mã cũ (reply A/B, kênh chung) chỉ @us28qt từng dùng → gán ``DEFAULT_ACCOUNT``; mã bio riêng mang tài khoản.
    """
    out: Dict[str, tuple] = {
        code: (bot, v, DEFAULT_ACCOUNT)
        for bot, (_, _, variants) in _STATIC.items()
        for v, (code, _) in variants.items()
    }
    for bot in _STATIC:
        for ch in CHANNELS:
            out[channel_code(bot, ch)] = (bot, None, DEFAULT_ACCOUNT)
        for acc in ACCOUNTS:
            out[bio_code(bot, acc)] = (bot, None, acc)
    return out


def code_channel(code: str) -> str:
    """Nhãn kênh cho báo cáo: «reply A», «bài riêng», «bio profile»…"""
    hit = code_map().get(code)
    if not hit:
        return "khác"
    bot, variant, _ = hit
    if variant is not None:
        return f"reply {variant.value}"
    rest = code.removeprefix(_CHANNEL_PREFIX[bot])
    return CHANNELS.get(rest.split("_", 1)[0], "khác")


def _setting(key: str):
    """Giá trị trên web; DB lỗi → mặc định khai trong ``app/core/settings.py``."""
    try:
        return settings.get(key)
    except Exception as exc:  # CLI chạy rời / test không có DB
        logger.debug("growth: không đọc được %s (%s) — dùng mặc định", key, exc)
        return settings.SETTINGS[key].default_getter()


def parse_keywords(raw) -> List[str]:
    seen: List[str] = []
    for part in str(raw or "").replace("\n", ",").split(","):
        kw = part.strip().lower()
        if kw and kw not in seen:
            seen.append(kw)
    return seen


def load_profiles() -> Dict[TargetBot, BotGrowthProfile]:
    profiles: Dict[TargetBot, BotGrowthProfile] = {}
    for bot, (name, handle, variants) in _STATIC.items():
        base_url = f"https://t.me/{handle}"
        profiles[bot] = BotGrowthProfile(
            bot_type=bot,
            name=name,
            handle=f"@{handle}",
            base_url=base_url,
            keywords=parse_keywords(_setting(f"growth.keywords_{bot.value}")),
            variants={
                v: VariantConfig(
                    variant=v,
                    code=code,
                    tracking_url=f"{base_url}?start={code}",
                    name=vname,
                    angle=str(_setting(f"growth.{bot.value}_{v.value.lower()}_angle") or ""),
                    sample_hook=str(_setting(f"growth.{bot.value}_{v.value.lower()}_hook") or ""),
                )
                for v, (code, vname) in variants.items()
            },
        )
    return profiles


# Giới hạn an toàn chống checkpoint / shadowban: chỉnh trên web (/app/settings → «Threads — Kéo khách»).
# Đây chỉ là giá trị dự phòng khi không đọc được DB cài đặt.
@dataclass(frozen=True)
class GrowthLimits:
    max_replies_per_hour: int = 5
    max_replies_per_day: int = 25
    min_delay_sec: int = 180
    max_delay_sec: int = 420
    min_relevance: int = 40


def load_limits() -> GrowthLimits:
    """Đọc giới hạn từ cài đặt runtime (cache 3s); lỗi DB → giá trị mặc định."""
    d = GrowthLimits()
    try:
        lim = GrowthLimits(
            max_replies_per_hour=settings.get_int("growth.max_replies_per_hour", d.max_replies_per_hour),
            max_replies_per_day=settings.get_int("growth.max_replies_per_day", d.max_replies_per_day),
            min_delay_sec=settings.get_int("growth.min_delay_sec", d.min_delay_sec),
            max_delay_sec=settings.get_int("growth.max_delay_sec", d.max_delay_sec),
            min_relevance=settings.get_int("growth.min_relevance", d.min_relevance),
        )
    except Exception as exc:  # DB cài đặt chưa sẵn (CLI chạy rời, test)
        logger.warning("growth: không đọc được cài đặt, dùng mặc định (%s)", exc)
        return d
    if lim.max_delay_sec < lim.min_delay_sec:
        lim = replace(lim, max_delay_sec=lim.min_delay_sec)
    return lim


@dataclass(frozen=True)
class WorkerConfig:
    enabled: bool = False
    scan_interval_min: int = 60
    auto_post_min_relevance: int = 40
    max_post_age_hours: int = 48
    author_cooldown_days: int = 14
    posts_per_keyword: int = 10
    vietnamese_only: bool = True
    top_level_only: bool = True
    telegram_review: bool = False
    search_top: bool = True
    min_reach: int = 0
    own_posts_enabled: bool = True
    own_post_times: str = "11:45, 20:15"
    followup_enabled: bool = True
    followup_max_per_day: int = 15
    followup_lookback_hours: int = 48


def load_worker_config() -> WorkerConfig:
    d = WorkerConfig()
    try:
        return WorkerConfig(
            enabled=settings.get_bool("growth.enabled", d.enabled),
            scan_interval_min=settings.get_int("growth.scan_interval_min", d.scan_interval_min),
            auto_post_min_relevance=settings.get_int("growth.auto_post_min_relevance", d.auto_post_min_relevance),
            max_post_age_hours=settings.get_int("growth.max_post_age_hours", d.max_post_age_hours),
            author_cooldown_days=settings.get_int("growth.author_cooldown_days", d.author_cooldown_days),
            posts_per_keyword=settings.get_int("growth.posts_per_keyword", d.posts_per_keyword),
            vietnamese_only=settings.get_bool("growth.vietnamese_only", d.vietnamese_only),
            top_level_only=settings.get_bool("growth.top_level_only", d.top_level_only),
            telegram_review=settings.get_bool("growth.telegram_review", d.telegram_review),
            search_top=settings.get_bool("growth.search_top", d.search_top),
            min_reach=settings.get_int("growth.min_reach", d.min_reach),
            own_posts_enabled=settings.get_bool("growth.own_posts_enabled", d.own_posts_enabled),
            own_post_times=str(settings.get("growth.own_post_times") or d.own_post_times),
            followup_enabled=settings.get_bool("growth.followup_enabled", d.followup_enabled),
            followup_max_per_day=settings.get_int("growth.followup_max_per_day", d.followup_max_per_day),
            followup_lookback_hours=settings.get_int("growth.followup_lookback_hours", d.followup_lookback_hours),
        )
    except Exception as exc:
        logger.warning("growth: không đọc được cài đặt worker, dùng mặc định — TẮT (%s)", exc)
        return d


# Neo theo gốc project, không theo thư mục đang đứng. data/ đã gitignore (giống cashback.sqlite).
_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = Path(os.getenv("THREADS_GROWTH_DB_PATH") or _ROOT / "data" / "threads_growth.sqlite")
DEMO_DB_PATH = _ROOT / "data" / "threads_growth_demo.sqlite"
