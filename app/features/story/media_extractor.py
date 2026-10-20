"""Story Media Extractor (R2 & R3).

Handles:
- Classification into Video Story vs Photo Story based on duration and pacing preferences.
- FFmpeg extraction of 10-15s vertical 9:16 Video Story (1080x1920, H.264, AAC, throttled).
- FFmpeg extraction of sharp vertical 9:16 Photo Story cover frame (1080x1920, JPEG, -q:v 2).
- Atomic temporary writes and immediate cleanup on failure to prevent disk bloat.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from app.config import STORAGE_MEDIA_DIR
from app.core.media.ffmpeg_path import ffmpeg_bin
from app.core.media.thumbnail import media_info

logger = logging.getLogger(__name__)

DEFAULT_STORIES_DIR = Path(STORAGE_MEDIA_DIR) / "stories"
STORY_SCALE_PAD_FILTER = (
    "scale=1080:1920:force_original_aspect_ratio=decrease,"
    "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def _nice_prefix() -> list[str]:
    """Prefix command with nice -n 19 on Linux/POSIX for CPU throttling."""
    if sys.platform != "win32" or shutil.which("nice"):
        return ["nice", "-n", "19"]
    return []


def classify_story_mode(duration: float, preferred_mode: str | None = None) -> str:
    """
    Classify content into 'video' or 'photo' story mode.

    Rules:
    - If duration > 30.0 -> 'video'; if duration <= 30.0 -> 'photo'.
    - If preferred_mode is provided and duration >= 10.0s, honor preferred_mode.
    - If preferred_mode == 'video' but duration < 10.0s, falls back to 'photo'.
    - If preferred_mode == 'photo', honors 'photo'.
    """
    pref = preferred_mode.strip().lower() if isinstance(preferred_mode, str) else None
    dur = float(duration or 0.0)

    if pref in ("video", "photo"):
        if pref == "video":
            if dur >= 10.0:
                return "video"
            return "photo"
        return "photo"

    if dur > 30.0:
        return "video"
    return "photo"


class StoryMediaExtractor:
    """Extracts Facebook-compliant 9:16 vertical Video and Photo Stories."""

    stories_dir: Path = DEFAULT_STORIES_DIR

    @classmethod
    def get_stories_dir(cls) -> Path:
        target = cls.stories_dir
        os.makedirs(target, exist_ok=True)
        return target

    @classmethod
    def generate_story_filename(
        cls,
        mode: str,
        material_id: int | str = 0,
        timestamp: int | None = None,
    ) -> str:
        """Deterministic filename: story_v_{id}_{timestamp}.mp4 or story_p_{id}_{timestamp}.jpg"""
        ts = int(time.time()) if timestamp is None else int(timestamp)
        clean_id = str(material_id).strip() or "0"
        if mode == "video":
            return f"story_v_{clean_id}_{ts}.mp4"
        return f"story_p_{clean_id}_{ts}.jpg"

    @classmethod
    def classify_story_mode(cls, duration: float, preferred_mode: str | None = None) -> str:
        """Classify story mode based on duration and optional preferred mode."""
        return classify_story_mode(duration, preferred_mode=preferred_mode)

    @classmethod
    def extract_video_story(
        cls,
        input_path: str,
        output_path: str | None = None,
        start_sec: float | None = None,
        duration: float = 15.0,
        material_id: int | str = 0,
    ) -> str:
        """
        Extracts 10-15s highlight clamped between 10.0s and 15.0s.

        Resolution: 1080x1920 (9:16 vertical canvas).
        Codecs: H.264 (libx264, yuv420p, CRF 23, fast preset), AAC audio (aac, 128k, 44100Hz).
        Audio fallback: -map 0:a? for silent videos.
        CPU throttling: -threads 2 and nice -n 19.
        Container: MP4 with -movflags +faststart.
        Atomic write: writes to .tmp and renames on success, unlinks on failure.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video not found: {input_path}")

        # Clamp duration to [10.0, 15.0]
        clip_duration = max(10.0, min(15.0, float(duration)))

        # Determine start time
        if start_sec is None:
            start_val = 0.0
        else:
            start_val = max(0.0, float(start_sec))

        # Output path
        if output_path is None:
            filename = cls.generate_story_filename("video", material_id=material_id)
            final_output = cls.get_stories_dir() / filename
        else:
            final_output = Path(output_path).resolve()
            os.makedirs(final_output.parent, exist_ok=True)

        final_output_str = str(final_output)
        tmp_output_str = f"{final_output_str}.tmp"

        if os.path.exists(tmp_output_str):
            try:
                os.unlink(tmp_output_str)
            except OSError:
                pass

        cmd = _nice_prefix() + [
            ffmpeg_bin(),
            "-y",
            "-ss", f"{start_val:.3f}",
            "-t", f"{clip_duration:.3f}",
            "-i", str(input_path),
            "-vf", STORY_SCALE_PAD_FILTER,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-movflags", "+faststart",
            "-threads", "2",
            "-f", "mp4",
            tmp_output_str,
        ]

        logger.info("[StoryMediaExtractor] Extracting video story: %s -> %s", input_path, final_output_str)
        success = False
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if res.returncode == 0 and os.path.exists(tmp_output_str) and os.path.getsize(tmp_output_str) > 0:
                os.replace(tmp_output_str, final_output_str)
                success = True
                return final_output_str
            err = (res.stderr or "").strip() or f"Process exited with code {res.returncode}"
            raise RuntimeError(f"FFmpeg video story extraction failed: {err}")
        finally:
            if not success and os.path.exists(tmp_output_str):
                try:
                    os.unlink(tmp_output_str)
                    logger.debug("[StoryMediaExtractor] Cleaned up temporary file: %s", tmp_output_str)
                except OSError:
                    pass

    @classmethod
    def extract_photo_story(
        cls,
        input_path: str,
        output_path: str | None = None,
        seek_sec: float = 2.0,
        material_id: int | str = 0,
    ) -> str:
        """
        Extracts sharp cover frame padded to vertical 9:16 (1080x1920), format JPEG, -q:v 2.
        Atomic write: writes to .tmp and renames on success, unlinks on failure.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input media not found: {input_path}")

        # Output path
        if output_path is None:
            filename = cls.generate_story_filename("photo", material_id=material_id)
            final_output = cls.get_stories_dir() / filename
        else:
            final_output = Path(output_path).resolve()
            os.makedirs(final_output.parent, exist_ok=True)

        final_output_str = str(final_output)
        tmp_output_str = f"{final_output_str}.tmp"

        if os.path.exists(tmp_output_str):
            try:
                os.unlink(tmp_output_str)
            except OSError:
                pass

        is_image = input_path.lower().endswith(IMAGE_EXTENSIONS)
        seek_val = max(0.0, float(seek_sec if seek_sec is not None else 2.0))

        cmd = _nice_prefix() + [ffmpeg_bin(), "-y"]
        if not is_image:
            cmd.extend(["-ss", f"{seek_val:.3f}"])
        cmd.extend([
            "-i", str(input_path),
            "-frames:v", "1",
            "-vf", STORY_SCALE_PAD_FILTER,
            "-q:v", "2",
            "-f", "image2",
            tmp_output_str,
        ])

        logger.info("[StoryMediaExtractor] Extracting photo story: %s -> %s", input_path, final_output_str)
        success = False
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode == 0 and os.path.exists(tmp_output_str) and os.path.getsize(tmp_output_str) > 0:
                os.replace(tmp_output_str, final_output_str)
                success = True
                return final_output_str
            err = (res.stderr or "").strip() or f"Process exited with code {res.returncode}"
            raise RuntimeError(f"FFmpeg photo story extraction failed: {err}")
        finally:
            if not success and os.path.exists(tmp_output_str):
                try:
                    os.unlink(tmp_output_str)
                    logger.debug("[StoryMediaExtractor] Cleaned up temporary file: %s", tmp_output_str)
                except OSError:
                    pass

    @classmethod
    def classify_and_extract(
        cls,
        input_path: str,
        output_dir: str | None = None,
        preferred_mode: str | None = None,
        material_id: int | str = 0,
    ) -> tuple[str, str]:
        """
        Probe input via media_info(input_path), select mode, extract, and return (output_path, mode).

        Handles alternative argument ordering where output_dir is passed as preferred_mode.
        """
        if isinstance(output_dir, str) and output_dir.lower() in ("video", "photo") and preferred_mode is None:
            preferred_mode = output_dir
            output_dir = None

        info = media_info(input_path)
        duration = float(info.get("duration", 0.0) or 0.0)
        mode = cls.classify_story_mode(duration, preferred_mode=preferred_mode)

        target_dir = Path(output_dir) if output_dir else cls.get_stories_dir()
        os.makedirs(target_dir, exist_ok=True)
        filename = cls.generate_story_filename(mode, material_id=material_id)
        target_path = str(target_dir / filename)

        if mode == "video":
            extracted_path = cls.extract_video_story(
                input_path,
                output_path=target_path,
                material_id=material_id,
            )
        else:
            # Pick a cover frame around 15% duration or default 2.0s
            seek = max(1.0, min(3.0, duration * 0.15)) if duration > 0 else 2.0
            extracted_path = cls.extract_photo_story(
                input_path,
                output_path=target_path,
                seek_sec=seek,
                material_id=material_id,
            )

        return extracted_path, mode
