"""Tài khoản + đăng nhập Threads cho Growth Agent (PLAN-158).

Một dòng ``accounts`` riêng (``name=threads_growth``, ``platform=threads``) dùng profile ``instagram_5``
(đã có phiên Instagram → «Tiếp tục bằng Instagram»). ``is_active=False`` để các worker Threads cũ
(``Threads_AutoReply`` / ``Threads_Publisher`` lọc ``is_active``) KHÔNG nhận tài khoản này; gói growth gọi nó theo tên.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import BASE_DIR, LOGS_DIR, PROFILES_DIR
from app.core.database.models import Account
from app.core.database.models.base import now_ts

ACCOUNT_NAME = "threads_growth"
PLATFORM = "threads"
PROFILE_DIR = Path(PROFILES_DIR) / "instagram_5"
LOGIN_SCRIPT = Path(BASE_DIR) / "app" / "scripts" / "login_browser.py"
# WSLg: cửa sổ Chromium hiện thẳng trên màn hình Windows (không cần VNC :99).
LOGIN_DISPLAY = os.getenv("THREADS_GROWTH_DISPLAY") or os.getenv("DISPLAY") or ":0"


class SessionBusy(RuntimeError):
    """Profile đang được trình duyệt khác giữ (worker đang chạy / cửa sổ đăng nhập còn mở)."""


@dataclass(frozen=True)
class SessionStatus:
    account_id: int
    profile_path: str
    login_status: str
    login_error: Optional[str]
    logging_in: bool
    profile_exists: bool

    @property
    def ready(self) -> bool:
        return self.login_status == "ACTIVE" and self.profile_exists


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def profile_locked(profile_dir: Path = PROFILE_DIR) -> bool:
    """Chromium đang mở profile này? (SingletonLock trỏ tới PID còn sống)."""
    lock = profile_dir / "SingletonLock"
    if not (lock.exists() or lock.is_symlink()):
        return False
    try:
        pid = int(os.readlink(str(lock)).rsplit("-", 1)[-1])
    except (OSError, ValueError):
        return True  # khóa lạ → coi như đang giữ cho an toàn
    return _pid_alive(pid)


def ensure_account(db: Session) -> Account:
    acc = db.query(Account).filter(Account.name == ACCOUNT_NAME).first()
    if acc:
        return acc
    acc = Account(
        name=ACCOUNT_NAME,
        platform=PLATFORM,
        is_active=False,
        profile_path=str(PROFILE_DIR),
        login_status="NEW",
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def status(db: Session) -> SessionStatus:
    acc = ensure_account(db)
    logging_in = acc.login_status == "LOGGING_IN" and _pid_alive(acc.login_process_pid)
    if acc.login_status == "LOGGING_IN" and not logging_in:
        # Tiến trình đăng nhập đã chết mà chưa kịp ghi trạng thái (vd tắt máy).
        acc.login_status, acc.login_process_pid = "INVALID", None
        acc.login_error = acc.login_error or "Cửa sổ đăng nhập đã đóng"
        db.commit()
    return SessionStatus(
        account_id=acc.id,
        profile_path=acc.resolved_profile_path,
        login_status=acc.login_status or "NEW",
        login_error=acc.login_error,
        logging_in=logging_in,
        profile_exists=Path(acc.resolved_profile_path or "").is_dir(),
    )


def mark(db: Session, ok: bool, error: Optional[str] = None) -> None:
    """Worker ghi lại kết quả kiểm phiên (mất đăng nhập / checkpoint → INVALID)."""
    acc = ensure_account(db)
    acc.login_status = "ACTIVE" if ok else "INVALID"
    acc.login_error = None if ok else (error or "")[:500]
    acc.last_login_check = now_ts()
    db.commit()


def start_login(db: Session, popen=subprocess.Popen) -> SessionStatus:
    """Mở cửa sổ Chromium (headed) để chủ bot đăng nhập Threads một lần."""
    acc = ensure_account(db)
    if acc.login_status == "LOGGING_IN" and _pid_alive(acc.login_process_pid):
        raise SessionBusy("Cửa sổ đăng nhập đang mở")
    if profile_locked(Path(acc.resolved_profile_path)):
        raise SessionBusy("Profile đang được worker dùng — tắt «Kéo khách» rồi thử lại")

    Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(BASE_DIR), "DISPLAY": LOGIN_DISPLAY}
    with open(Path(LOGS_DIR) / "login_threads_growth.log", "a") as log:
        log.write(f"\n--- Login started at {now_ts()} ---\n")
        log.flush()
        proc = popen(
            [
                sys.executable, str(LOGIN_SCRIPT),
                "--profile-dir", acc.resolved_profile_path,
                "--account-id", str(acc.id),
                "--platform", PLATFORM,
            ],
            stdout=log, stderr=log, env=env,
        )
    acc.login_status, acc.login_process_pid = "LOGGING_IN", proc.pid
    acc.login_started_at, acc.login_error = now_ts(), None
    db.commit()
    return status(db)
