"""
System health checks, queue-pressure alerts, temp cleanup (outputs/).
Extracted from workers/maintenance.py (TASK-20260329-05).
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

import app.config as config
from app.services.notifier import NotifierService

logger = logging.getLogger(__name__)

ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "600"))
ALERT_RAM_PCT_THRESHOLD = float(os.getenv("ALERT_RAM_PCT_THRESHOLD", "85"))
ALERT_CHROME_PROC_THRESHOLD = int(os.getenv("ALERT_CHROME_PROC_THRESHOLD", "20"))
CLEANUP_OUTPUTS_AFTER_DAYS = int(os.getenv("CLEANUP_OUTPUTS_AFTER_DAYS", "7"))

# OUTPUTS_DIR is now centralized in config.py

_last_alert_ts: dict[str, float] = {}


def _get_runtime_int(db, key: str, fallback: int) -> int:
    try:
        from app.services import settings as runtime_settings

        return int(runtime_settings.get_effective(db, key))
    except Exception:
        return fallback


def _should_alert(key: str) -> bool:
    now = time.time()
    last = _last_alert_ts.get(key, 0)
    if (now - last) >= ALERT_COOLDOWN_SEC:
        _last_alert_ts[key] = now
        return True
    return False


class SystemMonitorService:
    """RAM/disk/process monitoring and Telegram alerts (best-effort)."""

    def check_health(self) -> dict[str, Any]:
        """Return RAM %, CPU %, disk usage % (project root), Chrome/Playwright process count."""
        out: dict[str, Any] = {
            "ram_percent": None,
            "cpu_percent": None,
            "disk_percent": None,
            "chrome_playwright_count": None,
            "error": None,
        }
        try:
            import psutil

            vm = psutil.virtual_memory()
            out["ram_percent"] = float(vm.percent)
            out["cpu_percent"] = float(psutil.cpu_percent(interval=0.1))
            try:
                du = psutil.disk_usage(str(config.BASE_DIR))
                out["disk_percent"] = float(du.percent)
            except Exception:
                du = psutil.disk_usage("/")
                out["disk_percent"] = float(du.percent)
            chrome_count = 0
            try:
                chrome_count = sum(
                    1
                    for p in psutil.process_iter(["name"])
                    if "chrome" in (p.info.get("name") or "").lower()
                    or "playwright" in (p.info.get("name") or "").lower()
                )
            except Exception:
                chrome_count = 0
            out["chrome_playwright_count"] = chrome_count
        except Exception as e:
            out["error"] = str(e)
        return out

    def send_alert(self, message: str) -> None:
        """Broadcast via Telegram if notifier is registered."""
        try:
            NotifierService._broadcast(message)
        except Exception:
            logger.debug("SystemMonitorService.send_alert failed", exc_info=True)

    def cleanup_temp_files(self) -> int:
        """
        Remove old files under OUTPUTS_DIR (default: project outputs/).
        Returns count of files removed.
        """
        removed = 0
        cutoff = time.time() - CLEANUP_OUTPUTS_AFTER_DAYS * 86400
        try:
            config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            return 0
        try:
            for path in config.OUTPUTS_DIR.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                except OSError:
                    continue
        except Exception as e:
            logger.warning("[SystemMonitor] cleanup_temp_files: %s", e)
        if removed:
            logger.info("[SystemMonitor] cleanup_temp_files removed %d file(s) under %s", removed, config.OUTPUTS_DIR)
        return removed

    def maybe_alert_queue_and_resources(self, db: Session) -> None:
        """Telegram alerts for queue congestion and RAM/Chrome pressure (cooldown)."""
        try:
            from app.database.models import Job, ViralMaterial

            pending = db.query(Job).filter(Job.status == "PENDING").count()
            drafts = db.query(Job).filter(Job.status == "DRAFT").count()
            ai = db.query(Job).filter(Job.status == "AI_PROCESSING").count()
            running = db.query(Job).filter(Job.status == "RUNNING").count()
            viral_new = db.query(ViralMaterial).filter(ViralMaterial.status == "NEW").count()

            th_pending = _get_runtime_int(db, "ALERT_PENDING_THRESHOLD", config.ALERT_PENDING_THRESHOLD)
            th_drafts = _get_runtime_int(db, "ALERT_DRAFT_THRESHOLD", config.ALERT_DRAFT_THRESHOLD)
            th_viral = _get_runtime_int(db, "ALERT_VIRAL_NEW_THRESHOLD", config.ALERT_VIRAL_NEW_THRESHOLD)

            if pending >= th_pending or drafts >= th_drafts or viral_new >= th_viral:
                if _should_alert("queue"):
                    NotifierService._broadcast(
                        "🚦 <b>Queue đang cao</b>\n"
                        f"• PENDING: <b>{pending}</b>\n"
                        f"• RUNNING: <b>{running}</b>\n"
                        f"• DRAFT: <b>{drafts}</b>\n"
                        f"• AI_PROCESSING: <b>{ai}</b>\n"
                        f"• Viral NEW: <b>{viral_new}</b>\n"
                        "Gợi ý: /queue để xem tổng quan."
                    )
        except Exception:
            pass

        try:
            import psutil

            vm = psutil.virtual_memory()
            ram_pct = float(vm.percent)
            chrome_count = 0
            try:
                chrome_count = sum(
                    1
                    for p in psutil.process_iter(["name"])
                    if "chrome" in (p.info.get("name") or "").lower()
                    or "playwright" in (p.info.get("name") or "").lower()
                )
            except Exception:
                chrome_count = 0

            if ram_pct >= ALERT_RAM_PCT_THRESHOLD or chrome_count >= ALERT_CHROME_PROC_THRESHOLD:
                if _should_alert("resources"):
                    NotifierService._broadcast(
                        "🧠 <b>Áp lực tài nguyên cao</b>\n"
                        f"• RAM: <b>{ram_pct:.1f}%</b>\n"
                        f"• Chrome/Playwright: <b>{chrome_count}</b>\n"
                        "Gợi ý: giảm backlog, hoặc tắt idle engagement khi bận."
                    )
        except Exception:
            pass
