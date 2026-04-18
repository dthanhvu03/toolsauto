import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler

def setup_shared_logger(name: str) -> logging.Logger:
    """
    Configures a shared logger for the application and background workers.
    Ensures logs go to PM2 stdout (for UI streaming) AND rotating file backups.
    """
    logger = logging.getLogger(name)

    # If the logger already has handlers, return it to avoid duplicate logs.
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Format specified: '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Stream handler explicitly using sys.stdout (for PM2 to capture in *-out.log)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
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
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
