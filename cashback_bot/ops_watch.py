"""PLAN-087: canh hai tiến trình bot. Chỉ đọc / ghi bot_state và hàng đợi tin admin; không gọi Shopee.

- Mỗi bot ghi mã commit lúc khởi động (đọc thẳng .git, không chạy lệnh git). Bot Telegram thấy hai bot khác
  commit thì báo admin một lần cho mỗi cặp: bot khởi động trước đang chạy code cũ.
- Bot Telegram ghi nhịp sống mỗi vòng. Bot Zalo canh nhịp này; im quá 10 phút thì nhắn admin thẳng qua API
  Telegram (hàng đợi tin admin do chính bot Telegram gửi, nên không dùng được lúc bot đó chết).
- Mỗi sáng (từ 8 giờ VN) bot Telegram tóm tắt tin gửi không thành công trong 24 giờ, chỉ khi có.
"""

from __future__ import annotations

import html
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from cashback_bot.db import TrackingRepository
from cashback_bot.telegram_api import TelegramDeliveryError

logger = logging.getLogger("cashback_bot")

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[1]
VERSION_KEYS = {"telegram": "code_version:telegram", "zalo": "code_version:zalo"}
TELEGRAM_HEARTBEAT_KEY = "telegram_heartbeat"
TELEGRAM_CHECK_INTERVAL_SEC = 300
TELEGRAM_DOWN_AFTER_SEC = 600
DIGEST_KEY = "delivery_digest_day"
DIGEST_HOUR = 8
UNIT_DIR = Path("/etc/systemd/system")
UNITS = {"telegram": "cashback-bot", "zalo": "cashback-zalo"}
MODULES = {"telegram": "cashback_bot >> logs/cashback_bot.log", "zalo": "cashback_bot.zalo_bot >> logs/cashback_zalo.log"}


def restart_command(channel: str, unit_dir: Path = UNIT_DIR) -> str:
    """Lệnh khởi động lại một bot: systemctl nếu đã cài unit (deploy/cashback), không thì lệnh nohup cũ."""
    unit = UNITS[channel]
    if (unit_dir / f"{unit}.service").is_file():
        return f"systemctl restart {unit}"
    return f"cd {ROOT} && umask 077 && setsid nohup .venv/bin/python -m {MODULES[channel]} 2>&1 &"


def code_version(root: Path = ROOT) -> str:
    """7 ký tự đầu của commit đang checkout, hoặc 'unknown'. Hỗ trợ worktree và packed-refs."""
    git = root / ".git"
    try:
        if git.is_file():
            git = Path(git.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip())
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head[:7]
        ref = head[5:]
        common = git
        if (git / "commondir").is_file():
            common = (git / (git / "commondir").read_text(encoding="utf-8").strip()).resolve()
        for base in (git, common):
            if (base / ref).is_file():
                return (base / ref).read_text(encoding="utf-8").strip()[:7]
        for line in (common / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line[:7]
    except (OSError, IndexError):
        pass
    return "unknown"


def record_version(repo: TrackingRepository, channel: str, now: float | None = None) -> str:
    version = code_version()
    repo.set_state(VERSION_KEYS[channel], f"{version}@{int(time.time() if now is None else now)}")
    logger.info("[Cashback] %s chạy code %s", channel, version)
    return version


def _version(repo: TrackingRepository, channel: str) -> tuple[str, int] | None:
    raw = repo.get_state(VERSION_KEYS[channel]) or ""
    version, _, started = raw.partition("@")
    return (version, int(started)) if version and started.isdigit() else None


def check_versions(repo: TrackingRepository, admin_notifier) -> None:
    """Hai bot khác commit: báo admin (khoá tin theo cặp commit, không báo lặp)."""
    try:
        telegram, zalo = _version(repo, "telegram"), _version(repo, "zalo")
        if telegram is None or zalo is None or telegram[0] == zalo[0] or "unknown" in (telegram[0], zalo[0]):
            return
        stale = "telegram" if telegram[1] < zalo[1] else "zalo"
        admin_notifier.notify_code_mismatch(telegram[0], zalo[0], stale, restart_command(stale))
    except (ValueError, sqlite3.Error):
        logger.exception("[Cashback] so mã commit hai bot thất bại")


def beat(repo: TrackingRepository, now: float | None = None) -> None:
    repo.set_state(TELEGRAM_HEARTBEAT_KEY, str(time.time() if now is None else now))


def check_telegram_health(repo: TrackingRepository, telegram, admin_chat_id: int | None,
                          now: float | None = None) -> None:
    """Chạy trong bot Zalo. `telegram`: TelegramApi (gửi thẳng, không qua hàng đợi). Gửi lỗi thì lần sau thử lại."""
    if telegram is None or admin_chat_id is None:
        return
    moment = time.time() if now is None else now
    try:
        last = repo.get_state("telegram_check_last")
        if last and moment - float(last) < TELEGRAM_CHECK_INTERVAL_SEC:
            return
        repo.set_state("telegram_check_last", str(moment))
        beat_raw = repo.get_state(TELEGRAM_HEARTBEAT_KEY)
        if not beat_raw:
            return
        last_beat = float(beat_raw)
        down = moment - last_beat > TELEGRAM_DOWN_AFTER_SEC
        if down == (repo.get_state("telegram_down_alerted") == "1"):
            return
        seen = datetime.fromtimestamp(last_beat, timezone.utc).astimezone(ICT).strftime("%H:%M · %d/%m")
        if down:
            body = (
                "🔴 <b>Bot Telegram không hoạt động</b>\n\n"
                f"Nhịp sống cuối: {seen}. Khách Telegram không nhận được trả lời, tin admin không được gửi.\n"
                "Kiểm tra <code>logs/cashback_bot.log</code>, rồi khởi động lại:\n"
                f"<code>{html.escape(restart_command('telegram'))}</code>\n\n"
                "(Tin này do bot Zalo gửi.)"
            )
        else:
            body = "🟢 <b>Bot Telegram hoạt động lại</b>\n\n(Tin này do bot Zalo gửi.)"
        telegram.send_message(int(admin_chat_id), body)
        repo.set_state("telegram_down_alerted", "1" if down else "0")
    except TelegramDeliveryError as exc:
        logger.error("[Cashback] không báo được admin bot Telegram %s: %s", "dừng", exc.kind)
    except (ValueError, sqlite3.Error):
        logger.exception("[Cashback] kiểm tra nhịp sống bot Telegram thất bại")


def delivery_counts(repo: TrackingRepository, now: datetime) -> dict[str, int]:
    since = (now - timedelta(hours=24)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with repo.connect() as conn:
        rows = conn.execute(
            "SELECT audience, status, COUNT(*) FROM admin_notifications "
            "WHERE status IN ('unknown', 'failed') AND COALESCE(last_attempt_at, created_at) >= ? "
            "GROUP BY audience, status",
            (since,),
        ).fetchall()
        review = conn.execute(
            "SELECT COUNT(*) FROM outbound_messages WHERE status = 'needs_review' AND created_at >= ?", (since,)
        ).fetchone()[0]
    counts = {f"{audience}_{status}": int(count) for audience, status, count in rows}
    counts["reply_needs_review"] = int(review)
    return counts


def check_delivery_digest(repo: TrackingRepository, admin_notifier, now: datetime | None = None) -> None:
    """Một lần mỗi ngày từ DIGEST_HOUR giờ VN; không có tin lỗi thì không nhắn."""
    moment = now or datetime.now(timezone.utc)
    local = moment.astimezone(ICT)
    day = local.strftime("%Y-%m-%d")
    try:
        if local.hour < DIGEST_HOUR or repo.get_state(DIGEST_KEY) == day:
            return
        repo.set_state(DIGEST_KEY, day)
        counts = delivery_counts(repo, moment)
        if any(counts.values()):
            admin_notifier.notify_delivery_digest(day, counts)
    except sqlite3.Error:
        logger.exception("[Cashback] tóm tắt tin gửi lỗi thất bại")
