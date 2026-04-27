"""
MediaProcessor — FFmpeg video processing service.

Features:
  - Profile-based processing (reels, feed, compress_only)
  - Watermark/logo overlay (configurable position + opacity)
  - Atomic temp file writes (crash-safe)
  - Skip re-processing on retry (idempotent)
  - CPU control via nice (lowest priority)
  - FFmpeg error classification (RETRYABLE vs FATAL)
"""

import os
import subprocess
import logging
import mimetypes
import tempfile
from dataclasses import dataclass
from typing import Optional

from app.config import (
    FFMPEG_CRF, CONTENT_DIR,
    FFMPEG_WATERMARK_PATH, FFMPEG_WATERMARK_POSITION, FFMPEG_WATERMARK_OPACITY,
    DRM_ENABLED, DRM_WATERMARK_TEXT
)
from app.services.video_protector import VideoProtector

logger = logging.getLogger(__name__)

PROCESSED_DIR = CONTENT_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Video MIME types we process
VIDEO_MIMES = {"video/mp4", "video/avi", "video/x-msvideo", "video/quicktime", 
               "video/x-matroska", "video/webm", "video/mpeg", "video/3gpp"}

# FFmpeg errors that indicate corrupt/unsupported input (FATAL — no retry value)
FATAL_PATTERNS = [
    "Invalid data found",
    "No such file or directory",
    "does not contain any stream",
    "Unsupported codec",
    "Cannot determine format",
    "moov atom not found",
]

# Watermark position mapping → FFmpeg overlay coordinates (10px margin)
WATERMARK_POSITIONS = {
    "top_left":     "10:10",
    "top_right":    "main_w-overlay_w-10:10",
    "bottom_left":  "10:main_h-overlay_h-10",
    "bottom_right": "main_w-overlay_w-10:main_h-overlay_h-10",
}


@dataclass
class ProcessResult:
    success: bool
    output_path: Optional[str] = None
    error: Optional[str] = None
    is_fatal: bool = False


class MediaProcessor:
    """Stateless FFmpeg processor. All methods are classmethod for easy testing."""

    # --- Profile Definitions ---
    PROFILES = {
        "reels": {
            "vf": "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "crf": 18,
            "pix_fmt": "yuv420p",
            "profile": "high",
            "level": "4.1",
            "preset": "medium",
        },
        "feed": {
            "vf": "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2:black",
            "crf": max(FFMPEG_CRF - 2, 18),
        },
        "compress_only": {
            "vf": None,
            "crf": FFMPEG_CRF,
        },
    }

    @classmethod
    def is_video(cls, file_path: str) -> bool:
        """Check if file is a video using mime type detection."""
        if not file_path or not os.path.exists(file_path):
            return False
        mime, _ = mimetypes.guess_type(file_path)
        return mime in VIDEO_MIMES if mime else False

    @classmethod
    def extract_thumbnail(cls, video_path: str, job_id: int) -> Optional[str]:
        """
        Extract one frame from video via FFmpeg → path to JPEG.
        Returns None on failure (caller may fall back to text-only).
        """
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
            subprocess.run(
                cmd, capture_output=True, timeout=10,
                check=True,
            )
            if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                return thumb_path
        except Exception as e:
            logger.debug("[MediaProcessor] Thumbnail extraction failed for job %s: %s", job_id, e)

        return None

    @classmethod
    def cleanup_thumbnail(cls, thumb_path: Optional[str]) -> None:
        """Remove temporary thumbnail after send."""
        if thumb_path and os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
            except OSError:
                pass

    @classmethod
    def telegram_video_within_size_limit(cls, video_path: str, max_mb: float = 50.0) -> bool:
        """True if file exists and is at or below Telegram Bot API video size limit."""
        if not video_path or not os.path.exists(video_path):
            return False
        return os.path.getsize(video_path) / (1024 * 1024) <= max_mb

    @classmethod
    def _has_watermark(cls) -> bool:
        """Check if watermark is configured and file exists."""
        return bool(FFMPEG_WATERMARK_PATH) and os.path.exists(FFMPEG_WATERMARK_PATH)

    @classmethod
    def _build_ffmpeg_cmd(cls, input_path: str, profile_cfg: dict, temp_output: str) -> list:
        """
        Build the full FFmpeg command with optional static watermark and dynamic DRM watermark.
        """
        cmd = ["nice", "-n", "19", "ffmpeg", "-y", "-i", input_path]

        has_wm = cls._has_watermark()
        vf = profile_cfg["vf"]

        # Determine DRM dynamic filter if enabled
        drm_filter = ""
        if DRM_ENABLED:
            drm_filter = VideoProtector.get_dynamic_watermark_filter(DRM_WATERMARK_TEXT)

        if has_wm:
            # Add watermark as second input
            cmd += ["-i", FFMPEG_WATERMARK_PATH]
            
            pos = WATERMARK_POSITIONS.get(FFMPEG_WATERMARK_POSITION, WATERMARK_POSITIONS["bottom_right"])
            opacity = max(0.0, min(1.0, FFMPEG_WATERMARK_OPACITY))

            # Build complex filter graph
            if vf:
                # Resize + Static Watermark
                filter_complex = (
                    f"[0:v]{vf}[resized];"
                    f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[logo];"
                    f"[resized][logo]overlay={pos}[with_logo]"
                )
            else:
                # Static Watermark only
                filter_complex = (
                    f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[logo];"
                    f"[0:v][logo]overlay={pos}[with_logo]"
                )
            
            # Append DRM dynamic watermark if enabled
            if drm_filter:
                filter_complex += f";[with_logo]{drm_filter}[out]"
            else:
                filter_complex = filter_complex.replace("[with_logo]", "[out]")
            
            cmd += ["-filter_complex", filter_complex, "-map", "[out]", "-map", "0:a?"]
        else:
            # No static watermark
            combined_vf = ""
            if vf and drm_filter:
                combined_vf = f"{vf},{drm_filter}"
            elif vf:
                combined_vf = vf
            elif drm_filter:
                combined_vf = drm_filter
            
            if combined_vf:
                cmd += ["-vf", combined_vf]

        # Encoding settings
        cmd += [
            "-c:v", "libx264",
            "-crf", str(profile_cfg["crf"]),
            "-preset", profile_cfg.get("preset", "fast"),
            "-profile:v", profile_cfg.get("profile", "high"),
            "-level", profile_cfg.get("level", "4.1"),
            "-pix_fmt", profile_cfg.get("pix_fmt", "yuv420p"),
            "-threads", "2",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            temp_output
        ]

        return cmd

    @classmethod
    def process(cls, input_path: str, profile: str = "reels", job=None) -> ProcessResult:
        """
        Process a video file with FFmpeg.
        
        - Applies profile-based resize + compression
        - Overlays static watermark if configured
        - Overlays dynamic DRM watermark if DRM_ENABLED
        - Extracts pHash evidence if DRM_ENABLED
        - Writes output to a .tmp.mp4 file first, then renames atomically
        - Uses nice -n 19 to avoid starving the Worker CPU
        - Classifies FFmpeg errors as RETRYABLE or FATAL
        """
        if not os.path.exists(input_path):
            return ProcessResult(success=False, error=f"Input file not found: {input_path}", is_fatal=True)

        if not cls.is_video(input_path):
            return ProcessResult(success=False, error="Not a video file, skipping", is_fatal=False)

        profile_cfg = cls.PROFILES.get(profile)
        if not profile_cfg:
            return ProcessResult(success=False, error=f"Unknown profile: {profile}", is_fatal=True)

        # Output paths
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = str(PROCESSED_DIR / f"{base_name}_processed.mp4")
        temp_output = str(PROCESSED_DIR / f"{base_name}_processing.mp4")

        # Skip if already processed (idempotent)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info("[MediaProcessor] Already processed, skipping: %s", output_path)
            return ProcessResult(success=True, output_path=output_path)

        # Build command
        cmd = cls._build_ffmpeg_cmd(input_path, profile_cfg, temp_output)
        
        wm_status = f", watermark={FFMPEG_WATERMARK_POSITION}" if cls._has_watermark() else ""
        logger.info("[MediaProcessor] Processing: %s (profile=%s%s)", input_path, profile, wm_status)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute max per video
            )

            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "Unknown FFmpeg error"
                is_fatal = any(p in error_msg for p in FATAL_PATTERNS)
                
                if os.path.exists(temp_output):
                    os.unlink(temp_output)
                
                logger.error("[MediaProcessor] FFmpeg failed (fatal=%s): %s", is_fatal, error_msg[:200])
                return ProcessResult(success=False, error=error_msg[:200], is_fatal=is_fatal)

            # Validate output
            if not os.path.exists(temp_output) or os.path.getsize(temp_output) == 0:
                return ProcessResult(success=False, error="FFmpeg produced empty output", is_fatal=True)

            # Atomic rename
            os.rename(temp_output, output_path)

            # Extract pHash and audio fingerprint, then save evidence if DRM is enabled
            if DRM_ENABLED and job and job.account and getattr(job.account, 'name', None):
                try:
                    phash_data = VideoProtector.extract_phash(output_path)
                    audio_data = VideoProtector.extract_audio_fingerprint(output_path)
                    VideoProtector.save_evidence(
                        job_id=job.id,
                        account_name=job.account.name, 
                        video_path=output_path, 
                        phash_data=phash_data,
                        audio_data=audio_data
                    )
                except Exception as e:
                    logger.error("[MediaProcessor] VideoProtector DRM L2/L4 failed: %s", e)
            
            input_size = os.path.getsize(input_path) / 1024 / 1024
            output_size = os.path.getsize(output_path) / 1024 / 1024
            logger.info(
                "[MediaProcessor] Done: %.1fMB → %.1fMB (%.0f%% reduction) → %s",
                input_size, output_size, (1 - output_size/input_size) * 100, output_path
            )

            return ProcessResult(success=True, output_path=output_path)

        except subprocess.TimeoutExpired:
            if os.path.exists(temp_output):
                os.unlink(temp_output)
            return ProcessResult(success=False, error="FFmpeg timeout (>10 min)", is_fatal=False)

        except Exception as e:
            if os.path.exists(temp_output):
                os.unlink(temp_output)
            return ProcessResult(success=False, error=str(e), is_fatal=False)
