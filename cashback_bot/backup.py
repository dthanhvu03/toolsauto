"""Backup SQLite bằng Backup API. Không copy file nóng và không ghi đè DB đang chạy.

Hardening P1-9: bot tự gọi `run_scheduled_backup` mỗi ngày (poller). Bản sao ghi ra file tạm,
kiểm tra integrity và các bảng chính, rồi mới đổi tên; quyền 0600, thư mục 0700.
PLAN-087: bản chạy tay (`python -m cashback_bot.backup`, trước mỗi lần sửa DB) mang tên `cashback-manual-…` và
được dọn riêng, để nhiều bản tay không đẩy mất bản tự động hằng ngày.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cashback_bot.config import ConfigError, load_settings
from cashback_bot.redact import RedactingFormatter, error_brief

logger = logging.getLogger("cashback_bot")

# Chỉ file đúng mẫu này mới được tính là bản backup và mới có thể bị dọn. Nhóm 1: nhãn ("manual") hoặc rỗng.
BACKUP_NAME = re.compile(r"^cashback-(?:(manual)-)?(\d{8}T\d{6}Z)\.sqlite$")
MANUAL = "manual"
# Bản sao thiếu một trong các bảng này thì không dùng để khôi phục được.
# Bản backup phải có cả sổ tiền: đơn, sổ ví, yêu cầu rút và lịch sử chi trả (rà soát 2026-10-26).
REQUIRED_TABLES = (
    "telegram_users", "link_requests", "bot_state", "outbound_messages",
    "shopee_conversions", "cashback_entries", "cashback_payouts", "payout_events",
)
MIN_KEEP = 3


@dataclass(frozen=True)
class BackupCheck:
    path: Path
    tables: int
    link_requests: int


def integrity_ok(path: Path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.DatabaseError:
        return False
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()
    return bool(row) and row[0] == "ok"


def verify_backup(path: Path, required: tuple[str, ...] = REQUIRED_TABLES) -> BackupCheck:
    """Mở chỉ đọc: integrity_check, đủ bảng `required`, đếm link_requests nếu có. Không đạt thì ném lỗi."""
    if not integrity_ok(path):
        raise RuntimeError("backup failed integrity_check")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        missing = [name for name in required if name not in tables]
        if missing:
            raise RuntimeError(f"backup missing tables: {', '.join(missing)}")
        links = int(conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0]) if "link_requests" in tables else 0
    finally:
        conn.close()
    return BackupCheck(Path(path), len(tables), links)


def backup_database(
    source: Path,
    dest_dir: Path,
    now: datetime | None = None,
    keep: int = 14,
    required: tuple[str, ...] = (),
    label: str = "",
) -> Path:
    source = Path(source)
    dest_dir = Path(dest_dir)
    if not source.exists():
        raise FileNotFoundError(source)
    dest_dir.mkdir(parents=True, exist_ok=True)
    _chmod(dest_dir, 0o700)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    prefix = f"cashback-{label}-" if label else "cashback-"
    dest = dest_dir / f"{prefix}{moment.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite"
    if dest.exists():
        raise FileExistsError(dest.name)
    partial = dest.with_name(dest.name + ".partial")
    partial.unlink(missing_ok=True)
    try:
        _copy_consistent(source, partial)
        _chmod(partial, 0o600)
        verify_backup(partial, required)
        partial.rename(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    _prune(dest_dir, keep, newest=dest, label=label)
    return dest


def restore_database(backup: Path, dest: Path, protected: Path | None = None) -> None:
    backup = Path(backup)
    dest = Path(dest)
    if protected is not None and dest.resolve() == Path(protected).resolve():
        raise RuntimeError("refusing to overwrite the live database")
    if dest.exists():
        raise RuntimeError("restore destination already exists")
    if not integrity_ok(backup):
        raise RuntimeError("backup failed integrity_check")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _copy_consistent(backup, dest)
    _chmod(dest, 0o600)
    if not integrity_ok(dest):
        dest.unlink(missing_ok=True)
        raise RuntimeError("restored file failed integrity_check")


def latest_backup(dest_dir: Path) -> Path | None:
    """Bản mới nhất theo thời điểm tạo, tính cả bản tự động và bản tay."""
    files = _backups(Path(dest_dir), label=None)
    return max(files, key=lambda path: BACKUP_NAME.fullmatch(path.name).group(2)) if files else None


def run_scheduled_backup(source: Path, dest_dir: Path, keep: int, now: datetime | None = None,
                         label: str = "") -> BackupCheck:
    """Một lần backup: tạo bản sao rồi kiểm tra lại bản vừa tạo như lúc khôi phục. label="" là bản tự động."""
    path = backup_database(source, dest_dir, now=now, keep=keep, required=REQUIRED_TABLES, label=label)
    check = verify_backup(path)
    logger.info("[Cashback] backup ok file=%s tables=%s links=%s", path.name, check.tables, check.link_requests)
    return check


def _backups(dest_dir: Path, label: str | None = "") -> list[Path]:
    """Các bản backup của một nhóm ("" tự động, "manual" bản tay), cũ trước. label=None: mọi nhóm."""
    if not dest_dir.is_dir():
        return []
    files = []
    for path in dest_dir.iterdir():
        match = BACKUP_NAME.fullmatch(path.name)
        if path.is_file() and match and (label is None or (match.group(1) or "") == label):
            files.append(path)
    return sorted(files)


def _copy_consistent(source: Path, dest: Path) -> None:
    src = sqlite3.connect(source)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
            # DB chính chạy WAL (db.py): bản sao mang cờ WAL, mở chỉ đọc để kiểm tra sẽ để lại -wal/-shm cạnh file.
            # Backup phải là một file độc lập.
            dst.execute("PRAGMA journal_mode = DELETE")
        finally:
            dst.close()
    finally:
        src.close()


def _prune(dest_dir: Path, keep: int, newest: Path | None = None, label: str = "") -> None:
    """Giữ `keep` bản mới nhất của cùng nhóm (tối thiểu MIN_KEEP). Không đụng nhóm khác, file khác mẫu tên hay bản
    vừa tạo."""
    keep = max(MIN_KEEP, int(keep))
    files = _backups(dest_dir, label)
    extra = len(files) - keep
    for old in files[: max(0, extra)]:
        if newest is not None and old == newest:
            continue
        old.unlink(missing_ok=True)


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as exc:
        logger.warning("[Cashback] không đặt được quyền %o cho %s: %s", mode, Path(path).name, type(exc).__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [Cashback] %(levelname)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter("%(asctime)s [Cashback] %(levelname)s %(message)s"))
    try:
        settings = load_settings(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        check = run_scheduled_backup(Path(settings.db_path), Path(settings.backup_dir), keep=settings.backup_keep,
                                     label=MANUAL)
    except Exception as exc:
        logger.error("[Cashback] backup failed: %s", error_brief(exc))
        raise SystemExit(1) from exc
    print(check.path.name)


if __name__ == "__main__":
    main()
