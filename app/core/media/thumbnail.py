"""Generic media helpers shared by notifier / processors (not FB-specific)."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Optional

from app.core.media.ffmpeg_path import ffmpeg_bin, ffprobe_bin

logger = logging.getLogger(__name__)


def media_info(video_path: str) -> dict:
    """
    ADR-035 — ``{"duration": float, "width": int, "height": int}``; số 0 khi không đọc được.

    Đặt ở core vì cả notifier lẫn processor đều cần: notifier để nói "video dài bao nhiêu",
    client để truyền ``duration`` cho Telegram (thiếu nó thì khung video hiện ``0:00``).

    Không bao giờ ném — đây là thông tin phụ, hỏng thì thiếu chứ không được làm hỏng lượt gửi.
    """
    info = {"duration": 0.0, "width": 0, "height": 0}
    if not video_path or not os.path.isfile(video_path):
        return info
    try:
        out = subprocess.run(
            [
                ffprobe_bin(), "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=30,
        ).stdout.split()
        nums = [float(x) for x in out if x.replace(".", "", 1).isdigit()]
        if len(nums) >= 3:
            info["width"], info["height"], info["duration"] = int(nums[0]), int(nums[1]), nums[2]
        elif nums:
            info["duration"] = nums[-1]
    except Exception as exc:
        logger.debug("[media_info] không đọc được %s: %s", video_path, exc)
    return info


def extract_thumbnail(video_path: str, job_id: int) -> Optional[str]:
    if not video_path or not os.path.exists(video_path):
        return None
    thumb_path = os.path.join(tempfile.gettempdir(), f"thumb_{job_id}.jpg")
    try:
        cmd = [
            ffmpeg_bin(), "-y",
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
