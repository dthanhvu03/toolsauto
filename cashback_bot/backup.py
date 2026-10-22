"""Backup SQLite bằng Backup API. Không copy file nóng và không ghi đè DB đang chạy."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cashback_bot.config import ConfigError, load_settings


def integrity_ok(path: Path) -> bool:
    try:
        conn = sqlite3.connect(path)
    except sqlite3.DatabaseError:
        return False
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()
    return bool(row) and row[0] == "ok"


def backup_database(source: Path, dest_dir: Path, now: datetime | None = None, keep: int = 14) -> Path:
    source = Path(source)
    dest_dir = Path(dest_dir)
    if not source.exists():
        raise FileNotFoundError(source)
    dest_dir.mkdir(parents=True, exist_ok=True)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    dest = dest_dir / f"cashback-{moment.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite"
    if dest.exists():
        raise FileExistsError(dest.name)
    _copy_consistent(source, dest)
    if not integrity_ok(dest):
        dest.unlink(missing_ok=True)
        raise RuntimeError("backup failed integrity_check")
    _prune(dest_dir, keep)
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
    if not integrity_ok(dest):
        dest.unlink(missing_ok=True)
        raise RuntimeError("restored file failed integrity_check")


def _copy_consistent(source: Path, dest: Path) -> None:
    src = sqlite3.connect(source)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _prune(dest_dir: Path, keep: int) -> None:
    files = sorted(dest_dir.glob("cashback-*.sqlite"))
    extra = len(files) - keep
    for old in files[: max(0, extra)]:
        old.unlink(missing_ok=True)


def main() -> None:
    try:
        settings = load_settings(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    path = backup_database(Path(settings.db_path), Path(settings.backup_dir), keep=settings.backup_keep)
    print(path.name)


if __name__ == "__main__":
    main()
