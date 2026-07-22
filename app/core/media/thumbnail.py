"""Generic media helpers shared by notifier / processors (not FB-specific)."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


def extract_thumbnail(video_path: str, job_id: int) -> Optional[str]:
    if not video_path or not os.path.exists(video_path):
        return None
    thumb_path = os.path.join(tempfile.gettempdir(), f"thumb_{job_id}.jpg")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", "00:00:01",
            "-frames:v", "1",
            "-q:v", "5",
            thumb_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=10, check=True)
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return thumb_path
    except Exception as e:
        logger.debug("Thumbnail extraction failed for job %s: %s", job_id, e)
    return None


def cleanup_thumbnail(thumb_path: Optional[str]) -> None:
    if thumb_path and os.path.exists(thumb_path):
        try:
            os.remove(thumb_path)
        except OSError:
            pass


def telegram_video_within_size_limit(video_path: str, max_mb: float = 50.0) -> bool:
    if not video_path or not os.path.exists(video_path):
        return False
    return os.path.getsize(video_path) / (1024 * 1024) <= max_mb
