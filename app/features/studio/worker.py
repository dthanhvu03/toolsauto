"""
Tiến trình Studio: nhận việc theo làn, chạy, lặp lại.

    python -m app.features.studio.worker --lanes heavy          # PM2 Studio_Heavy
    python -m app.features.studio.worker --lanes light          # PM2 Studio_Light
    python -m app.features.studio.worker --lanes heavy,light --once   # chạy hết việc đang có rồi thoát

Mỗi lượt mở một session mới — một việc hỏng không làm bẩn session của việc sau.
Làn light còn quét hộp thư Drive (``entry.scan_inbox``) mỗi phút và đồng bộ trạng thái Buffer về dự án
(``publish.status.sync``) mỗi 5 phút; ``--once`` thì không làm hai việc này.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import time

import app.config as config
from app.core.database.core import SessionLocal
from app.core.notifier.service import NotifierService
from app.core.notifier.telegram import TelegramNotifier
from app.core.settings import load_runtime_settings_into_process
from app.features.studio import entry, pipeline, taskqueue
from app.features.studio.publish import status as publish_status
from app.features.studio.contracts import Lane
from app.utils.logger import setup_shared_logger

logger = logging.getLogger("app.studio.worker")  # con của "app" → ra PM2 log + file

IDLE_SLEEP_SEC = 5
STALE_CHECK_EVERY_SEC = 300
INBOX_SCAN_EVERY_SEC = 60
PUBLISH_SYNC_EVERY_SEC = 300
_running = True


def _stop(signum, _frame) -> None:
    global _running
    logger.info("[STUDIO] nhận tín hiệu %s — xong việc đang chạy thì dừng.", signum)
    _running = False


def run_once(lanes: list[Lane], worker_id: str) -> bool:
    """Nhận và chạy một việc. ``False`` khi hàng trống."""
    db = SessionLocal()
    try:
        task = taskqueue.claim(db, lanes=lanes, worker_id=worker_id)
        if task is None:
            return False
        logger.info("[STUDIO] việc #%s %s/%s (lần %s)", task.id, task.flow, task.stage, task.attempts)
        pipeline.run_task(db, task)
        return True
    finally:
        db.close()


def _periodic(fn, what: str):
    db = SessionLocal()
    try:
        return fn(db)
    except Exception:  # việc định kỳ hỏng không được giết worker
        logger.exception("[STUDIO] %s hỏng", what)
        db.rollback()
        return None
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Studio worker (ADR-061)")
    parser.add_argument("--lanes", default="heavy,light")
    parser.add_argument("--once", action="store_true", help="chạy hết việc đang có rồi thoát")
    args = parser.parse_args(argv)
    lanes = [Lane(x.strip()) for x in args.lanes.split(",") if x.strip()]
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{'+'.join(lanes)}"

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("[STUDIO] worker %s bắt đầu", worker_id)
    if not args.once:  # key AI / thư mục Drive anh lưu trên web nằm trong DB, không phải .env
        _periodic(load_runtime_settings_into_process, "đọc cài đặt")
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:  # dự án chờ duyệt → tin Telegram
            NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))

    last_stale_check = last_inbox_scan = last_publish_sync = 0.0
    while _running:
        if time.time() - last_stale_check >= STALE_CHECK_EVERY_SEC:
            n = _periodic(taskqueue.requeue_stale, "trả việc treo")
            if n:
                logger.warning("[STUDIO] trả %s việc treo về hàng", n)
            last_stale_check = time.time()
        if not args.once and Lane.LIGHT in lanes and time.time() - last_inbox_scan >= INBOX_SCAN_EVERY_SEC:
            _periodic(entry.scan_inbox, "quét hộp thư Drive")
            last_inbox_scan = time.time()
        if not args.once and Lane.LIGHT in lanes and time.time() - last_publish_sync >= PUBLISH_SYNC_EVERY_SEC:
            _periodic(publish_status.sync, "đồng bộ trạng thái Buffer")
            last_publish_sync = time.time()
        if run_once(lanes, worker_id):
            continue
        if args.once:
            break
        time.sleep(IDLE_SLEEP_SEC)
    logger.info("[STUDIO] worker %s dừng", worker_id)
    return 0


if __name__ == "__main__":
    setup_shared_logger("app")
    raise SystemExit(main())
