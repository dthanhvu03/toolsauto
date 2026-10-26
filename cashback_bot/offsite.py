"""D3: chép bản backup mới nhất ra ngoài máy bằng rclone (chủ bot duyệt 2026-10-26: Google Drive, mã hoá).

- Remote do chủ bot tự tạo bằng `rclone config` (Google Drive + lớp `crypt`), tên đặt ở .env:
  `CASHBACK_OFFSITE_REMOTE=cashback-crypt:`. Bot không đụng tài khoản Google hay mật khẩu mã hoá.
- Mỗi lần chạy: chép bản mới nhất lên remote, tải lại về thư mục tạm để so sha256 và `integrity_check`, rồi giữ
  `CASHBACK_OFFSITE_KEEP` bản mới nhất trên remote (mặc định 30; chỉ xoá file đúng mẫu tên backup).
- Ghi `bot_state`: offsite_last_ok (giờ unix), offsite_last_file, offsite_last_error. 🛠 Vận hành đọc các khoá này.
- Chạy bằng systemd timer (deploy/cashback/cashback-offsite.timer), tách khỏi bot để việc tải lên không chặn vòng
  poll. Chạy tay: `python -m cashback_bot.offsite`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from cashback_bot.backup import BACKUP_NAME, integrity_ok, latest_backup
from cashback_bot.config import ConfigError, load_settings
from cashback_bot.db import TrackingRepository
from cashback_bot.redact import RedactingFormatter, error_brief

logger = logging.getLogger("cashback_bot")

REMOTE_ENV = "CASHBACK_OFFSITE_REMOTE"
KEEP_ENV = "CASHBACK_OFFSITE_KEEP"
DEFAULT_KEEP = 30
MIN_KEEP = 3
TIMEOUT_SEC = 600
OK_KEY = "offsite_last_ok"
FILE_KEY = "offsite_last_file"
ERROR_KEY = "offsite_last_error"

Runner = Callable[..., subprocess.CompletedProcess]


class OffsiteError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rclone(runner: Runner, binary: str, *args: str) -> str:
    try:
        done = runner([binary, *args], check=True, capture_output=True, text=True, timeout=TIMEOUT_SEC)
    except FileNotFoundError as exc:
        raise OffsiteError("chưa cài rclone") from exc
    except subprocess.TimeoutExpired as exc:
        raise OffsiteError(f"rclone {args[0]} quá {TIMEOUT_SEC} giây") from exc
    except subprocess.CalledProcessError as exc:
        # stderr của rclone có thể dài; chỉ giữ dòng cuối, đủ để biết lỗi gì.
        tail = (exc.stderr or "").strip().splitlines()[-1:] or ["không có thông báo"]
        raise OffsiteError(f"rclone {args[0]} lỗi: {tail[0][:200]}") from exc
    return done.stdout or ""


def push_latest(backup_dir: Path, remote: str, keep: int = DEFAULT_KEEP, binary: str = "rclone",
                runner: Runner = subprocess.run) -> str:
    """Chép, kiểm tra lại, dọn remote. Trả tên file đã chép. Lỗi: OffsiteError."""
    latest = latest_backup(Path(backup_dir))
    if latest is None:
        raise OffsiteError("chưa có bản backup nào trong máy")
    if not integrity_ok(latest):
        raise OffsiteError(f"bản {latest.name} trong máy hỏng, không chép")
    _rclone(runner, binary, "copyto", str(latest), f"{remote}{latest.name}")
    with tempfile.TemporaryDirectory() as tmp:
        back = Path(tmp) / latest.name
        _rclone(runner, binary, "copyto", f"{remote}{latest.name}", str(back))
        if not back.is_file() or _sha256(back) != _sha256(latest) or not integrity_ok(back):
            raise OffsiteError(f"bản {latest.name} tải lại từ remote không khớp")
    names = sorted(
        name.strip() for name in _rclone(runner, binary, "lsf", "--files-only", remote).splitlines()
        if BACKUP_NAME.fullmatch(name.strip())
    )
    names.sort(key=lambda name: BACKUP_NAME.fullmatch(name).group(2))
    for old in names[: max(0, len(names) - max(MIN_KEEP, keep))]:
        if old != latest.name:
            _rclone(runner, binary, "deletefile", f"{remote}{old}")
    return latest.name


def run(repo: TrackingRepository, backup_dir: Path, remote: str, keep: int = DEFAULT_KEEP,
        runner: Runner = subprocess.run, now: float | None = None) -> bool:
    """Một lần chép; ghi kết quả vào bot_state. True khi thành công."""
    try:
        name = push_latest(backup_dir, remote, keep, runner=runner)
    except OffsiteError as exc:
        repo.set_state(ERROR_KEY, str(exc))
        logger.error("[Cashback] backup ngoài máy thất bại: %s", exc)
        return False
    repo.set_state(OK_KEY, str(now if now is not None else time.time()))
    repo.set_state(FILE_KEY, name)
    repo.set_state(ERROR_KEY, "")
    logger.info("[Cashback] backup ngoài máy ok file=%s", name)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [Cashback] %(levelname)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter("%(asctime)s [Cashback] %(levelname)s %(message)s"))
    try:
        settings = load_settings(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    remote = (os.getenv(REMOTE_ENV) or "").strip()
    if not remote:
        raise SystemExit(f"Chưa đặt {REMOTE_ENV} trong .env (xem deploy/cashback/README.md)")
    try:
        keep = int(os.getenv(KEEP_ENV) or DEFAULT_KEEP)
    except ValueError:
        keep = DEFAULT_KEEP
    repo = TrackingRepository(settings.db_path)
    try:
        ok = run(repo, Path(settings.backup_dir), remote, keep)
    except Exception as exc:
        logger.error("[Cashback] backup ngoài máy lỗi bất ngờ: %s", error_brief(exc))
        raise SystemExit(1) from exc
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
