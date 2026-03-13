"""
ReupProcessor — Pre-processing pipeline for reup videos.

Chạy TRƯỚC MediaProcessor để:
1. Xóa watermark TikTok (crop vùng logo bottom-right)
2. Anti-duplicate transforms (flip, speed, color shift) để tránh FB detect trùng
3. Cắt video > 90s thành 90s cho Reels

Usage:
    processor = ReupProcessor()
    result = processor.process(input_path, platform="tiktok")
    # result.output_path → file đã xử lý, sẵn sàng cho MediaProcessor.process()
"""
import os
import random
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ReupResult:
    success: bool
    output_path: Optional[str] = None
    error: Optional[str] = None


class ReupProcessor:
    """Pre-processing pipeline cho video reup trước khi đưa qua MediaProcessor."""

    # Max duration cho Facebook Reels (seconds)
    MAX_REELS_DURATION = 90

    @staticmethod
    def _get_video_info(video_path: str) -> dict:
        """Lấy thông tin video: duration, width, height."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-print_format", "json",
                    "-show_format", "-show_streams",
                    video_path,
                ],
                capture_output=True, text=True, timeout=15,
            )
            import json
            data = json.loads(result.stdout)
            video_stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                {}
            )
            return {
                "duration": float(data.get("format", {}).get("duration", 0)),
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
            }
        except Exception as e:
            logger.error("[ReupProcessor] ffprobe failed: %s", e)
            return {"duration": 0, "width": 0, "height": 0}

    @classmethod
    def _build_filter_chain(cls, platform: str, width: int, height: int) -> str:
        """
        Build FFmpeg video filter chain cho anti-duplicate.

        Transforms áp dụng:
        1. Crop watermark TikTok (nếu platform=tiktok)
        2. Random horizontal flip (50% chance)
        3. Slight speed change (0.97x - 1.03x)
        4. Color shift: hue/saturation/brightness nhẹ
        5. Slight zoom crop (2-4%) để thay đổi frame hash
        """
        filters = []

        # 1. Crop TikTok watermark
        #    TikTok logo: bottom-right corner ~50px, username: bottom ~60px
        if platform == "tiktok" and height > 200:
            crop_bottom = 50  # Crop 50px phía dưới (logo TikTok)
            crop_right = 60   # Crop 60px bên phải (username watermark)
            new_w = width - crop_right
            new_h = height - crop_bottom
            filters.append(f"crop={new_w}:{new_h}:0:0")

        # 2. XÓA Random horizontal flip - Gây ngược chữ (Subtitle), làm dở trải nghiệm người xem.
        # if random.random() > 0.5:
        #     filters.append("hflip")

        # 3. Slight speed change (0.97x - 1.03x) — thay đổi PTS
        speed_factor = random.uniform(0.97, 1.03)
        pts_factor = 1.0 / speed_factor
        filters.append(f"setpts={pts_factor:.4f}*PTS")

        # 4. Color shift — nhẹ nhàng, mắt thường không nhận ra
        hue_shift = random.uniform(-8, 8)        # ±8 degrees
        sat_shift = random.uniform(0.95, 1.05)    # ±5% saturation
        brightness = random.uniform(-0.03, 0.03)  # ±3% brightness
        filters.append(f"eq=brightness={brightness:.3f}:saturation={sat_shift:.3f}")
        filters.append(f"hue=h={hue_shift:.1f}")

        # 5. Subtle zoom crop (2-4%) — thay đổi frame edges
        zoom = random.uniform(0.96, 0.98)
        filters.append(f"crop=iw*{zoom:.3f}:ih*{zoom:.3f}")

        return ",".join(filters)

    @classmethod
    def process(
        cls,
        input_path: str,
        platform: str = "unknown",
        output_dir: Optional[str] = None,
    ) -> ReupResult:
        """
        Pre-process video reup: xóa watermark + anti-duplicate + cắt duration.

        Args:
            input_path: Path to downloaded video
            platform: Source platform (tiktok/youtube/facebook/instagram)
            output_dir: Output directory (default: same as input)

        Returns:
            ReupResult with processed file path
        """
        if not os.path.exists(input_path):
            return ReupResult(success=False, error=f"File not found: {input_path}")

        # Get video info
        info = cls._get_video_info(input_path)
        duration = info["duration"]
        width = info["width"]
        height = info["height"]

        if width == 0 or height == 0:
            return ReupResult(success=False, error="Cannot read video dimensions")

        logger.info(
            "[ReupProcessor] Input: %s (%s) — %dx%d, %.1fs",
            os.path.basename(input_path), platform, width, height, duration,
        )

        # Build output path
        if not output_dir:
            output_dir = os.path.dirname(input_path)
        base = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(output_dir, f"{base}_reup.mp4")
        temp_path = os.path.join(output_dir, f"{base}_reup.tmp.mp4")

        # Skip if already processed
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info("[ReupProcessor] Already processed, skipping: %s", output_path)
            return ReupResult(success=True, output_path=output_path)

        # Build FFmpeg command
        vf = cls._build_filter_chain(platform, width, height)

        cmd = ["nice", "-n", "19", "ffmpeg", "-y", "-i", input_path]

        # Duration limit
        if duration > cls.MAX_REELS_DURATION:
            cmd += ["-t", str(cls.MAX_REELS_DURATION)]
            logger.info("[ReupProcessor] Cắt video từ %.0fs → %ds", duration, cls.MAX_REELS_DURATION)

        # Audio speed sync (match video speed change)
        # atempo chỉ accepts 0.5-2.0, speed change nhỏ nên OK
        speed_pts = None
        for f in vf.split(","):
            if "setpts=" in f:
                # Extract PTS factor
                pts_str = f.replace("setpts=", "").replace("*PTS", "")
                try:
                    pts = float(pts_str)
                    speed_pts = 1.0 / pts  # Inverse for audio
                except ValueError:
                    pass

        audio_filter = ""
        if speed_pts and abs(speed_pts - 1.0) > 0.001:
            audio_filter = f"atempo={speed_pts:.4f}"

        if audio_filter:
            cmd += ["-vf", vf, "-af", audio_filter]
        else:
            cmd += ["-vf", vf]

        cmd += [
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            temp_path,
        ]

        logger.info("[ReupProcessor] Filters: %s", vf)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )

            if result.returncode != 0:
                error = result.stderr[-300:] if result.stderr else "Unknown error"
                logger.error("[ReupProcessor] FFmpeg failed: %s", error[:200])
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return ReupResult(success=False, error=error[:200])

            # Validate output
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                return ReupResult(success=False, error="FFmpeg produced empty output")

            # Atomic rename
            os.rename(temp_path, output_path)

            # Log size comparison
            in_size = os.path.getsize(input_path) / 1024 / 1024
            out_size = os.path.getsize(output_path) / 1024 / 1024
            logger.info(
                "[ReupProcessor] Done: %.1fMB → %.1fMB | %s → %s",
                in_size, out_size, platform, os.path.basename(output_path),
            )

            return ReupResult(success=True, output_path=output_path)

        except subprocess.TimeoutExpired:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return ReupResult(success=False, error="FFmpeg timeout (>5 min)")
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return ReupResult(success=False, error=str(e))
