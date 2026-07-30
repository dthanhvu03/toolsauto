import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler


class WindowsSafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """TimedRotatingFileHandler that tolerates WinError 32 during rollover.

    On Windows, web + workers often share the same app.log. Rename during
    midnight rollover fails with PermissionError (file locked by another
    process). Skip that rollover cycle instead of crashing the logger.
    """

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError as exc:
            logging.getLogger(__name__).warning(
                "Log rollover skipped (file locked): %s", exc
            )
        except OSError as exc:
            # WinError 32 = ERROR_SHARING_VIOLATION
            if getattr(exc, "winerror", None) == 32 or exc.errno in (13, 16):
                logging.getLogger(__name__).warning(
                    "Log rollover skipped (sharing violation): %s", exc
                )
                return
            raise


def setup_shared_logger(name: str) -> logging.Logger:
    """
    Configures a shared logger for the application and background workers.
    Ensures logs go to PM2 stdout (for UI streaming) AND rotating file backups.
    """
    logger = logging.getLogger(name)

    # If the logger already has handlers, return it to avoid duplicate logs.
    if logger.handlers:
        return logger

    # Keep logger at DEBUG and split visibility by handler:
    # - StreamHandler (PM2/UI): INFO+ without asctime (PM2 already stamps time)
    # - FileHandler (backup): DEBUG+ with asctime
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    stream_formatter = logging.Formatter(
        fmt="[%(levelname)s] %(name)s: %(message)s"
    )
    file_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Stream handler explicitly using sys.stdout (for PM2 to capture in *-out.log)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    # 2. TimedRotatingFileHandler for local backup
    # Allow override via environment variable for production flexibility
    try:
        from app.config import LOGS_DIR
        default_logs_dir = str(LOGS_DIR)
    except Exception:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        default_logs_dir = os.path.join(base_dir, "logs")

    logs_dir = os.environ.get("LOG_DIR", default_logs_dir)
    os.makedirs(logs_dir, exist_ok=True)

    log_file = os.path.join(logs_dir, "app.log")
    handler_cls = (
        WindowsSafeTimedRotatingFileHandler
        if os.name == "nt"
        else TimedRotatingFileHandler
    )
    file_handler = handler_cls(
        filename=log_file,
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger
