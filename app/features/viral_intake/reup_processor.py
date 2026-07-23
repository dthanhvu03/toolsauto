"""
ReupProcessor — Pre-processing pipeline for reup videos.

Chạy TRƯỚC MediaProcessor để:
1. Xóa watermark TikTok (crop vùng logo bottom-right)
2. Anti-duplicate transforms theo preset (safe / aggressive / reels_short)
3. Cắt video > 90s thành 90s cho Reels
4. Phase C: audio head-trim nhẹ + brand logo overlay opt-in

Usage:
    processor = ReupProcessor()
    result = processor.process(input_path, platform="tiktok", preset="safe")
"""
from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.features.viral_intake.reup_config import load_reup_config, normalize_preset

logger = logging.getLogger(__name__)


@dataclass
class ReupResult:
    success: bool
    output_path: Optional[str] = None
    error: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None


class ReupProcessor:
    """Pre-processing pipeline cho video reup trước khi đưa qua MediaProcessor."""

    MAX_REELS_DURATION = 90
    MIN_OUTPUT_DURATION_SEC = 1.5
    MIN_OUTPUT_EDGE_PX = 180
    MIN_OUTPUT_BYTES = 64 * 1024

    # Preset knobs: (speed_lo, speed_hi, hue, sat_lo, sat_hi, bright, zoom_lo, zoom_hi, crf)
    PRESET_KNOBS: dict[str, dict[str, float]] = {
        "safe": {
            "speed_lo": 0.98,
            "speed_hi": 1.02,
            "hue": 5.0,
            "sat_lo": 0.97,
            "sat_hi": 1.03,
            "bright": 0.02,
            "zoom_lo": 0.97,
            "zoom_hi": 0.99,
            "crf": 26,
        },
        "aggressive": {
            "speed_lo": 0.95,
            "speed_hi": 1.05,
            "hue": 12.0,
            "sat_lo": 0.92,
            "sat_hi": 1.08,
            "bright": 0.04,
            "zoom_lo": 0.94,
            "zoom_hi": 0.97,
            "crf": 25,
        },
        "reels_short": {
            "speed_lo": 1.02,
            "speed_hi": 1.08,
            "hue": 6.0,
            "sat_lo": 0.96,
            "sat_hi": 1.04,
            "bright": 0.025,
            "zoom_lo": 0.96,
            "zoom_hi": 0.98,
            "crf": 26,
            "max_duration": 45,
        },
    }

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
            data = json.loads(result.stdout)
            video_stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                {},
            )
            audio_stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "audio"),
                {},
            )
            return {
                "duration": float(data.get("format", {}).get("duration", 0)),
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "has_audio": bool(audio_stream),
            }
        except Exception:
            logger.exception("[ReupProcessor] ffprobe failed")
            return {"duration": 0, "width": 0, "height": 0, "has_audio": False}

    @classmethod
    def _validate_output(
        cls,
        *,
        input_info: dict[str, Any],
        output_info: dict[str, Any],
        output_path: str,
        max_duration: float,
    ) -> Optional[str]:
        """Quality gate for processed output before the original gets deleted."""
        if not os.path.exists(output_path):
            return "Output file missing after processing"

        out_size = os.path.getsize(output_path)
        if out_size < cls.MIN_OUTPUT_BYTES:
            return f"Output too small ({out_size} bytes)"

        out_w = int(output_info.get("width") or 0)
        out_h = int(output_info.get("height") or 0)
        if out_w < cls.MIN_OUTPUT_EDGE_PX or out_h < cls.MIN_OUTPUT_EDGE_PX:
            return f"Output resolution too small ({out_w}x{out_h})"

        out_duration = float(output_info.get("duration") or 0)
        if out_duration < cls.MIN_OUTPUT_DURATION_SEC:
            return f"Output duration too short ({out_duration:.2f}s)"

        in_duration = float(input_info.get("duration") or 0)
        if in_duration > max_duration and out_duration > (max_duration + 1.0):
            return f"Output duration exceeds cap ({out_duration:.2f}s > {max_duration}s)"

        return None

    @classmethod
    def _promote_temp(
        cls,
        *,
        temp_path: str,
        output_path: str,
        input_info: dict[str, Any],
        max_duration: float,
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Validate temp first, then replace output so a failed gate keeps the old file."""
        output_info = cls._get_video_info(temp_path)
        gate_error = cls._validate_output(
            input_info=input_info,
            output_info=output_info,
            output_path=temp_path,
            max_duration=max_duration,
        )
        if gate_error:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            return None, gate_error
        try:
            os.replace(temp_path, output_path)
        except OSError as e:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            return None, f"Cannot replace output: {e}"
        return output_info, None

    @classmethod
    def _resolve_logo_path(cls) -> Optional[str]:
        cfg = load_reup_config()
        if not cfg.get("brand_logo_enabled"):
            return None
        raw = (cfg.get("brand_logo_path") or "").strip()
        if not raw:
            return None
        p = Path(raw)
        if not p.is_absolute():
            from app import config as app_config

            p = Path(app_config.BASE_DIR) / raw
        if p.is_file():
            return str(p)
        logger.warning("[ReupProcessor] brand logo enabled but file missing: %s", p)
        return None

    @classmethod
    def _build_filter_chain(
        cls,
        platform: str,
        width: int,
        height: int,
        preset: str,
        logo_path: Optional[str] = None,
    ) -> tuple[str, float, dict[str, Any]]:
        """
        Build FFmpeg video filter chain.
        Returns (vf, speed_factor, applied_knobs).
        """
        knobs = dict(cls.PRESET_KNOBS.get(preset) or cls.PRESET_KNOBS["safe"])
        filters: list[str] = []

        if platform == "tiktok" and height > 200:
            crop_bottom = 50
            crop_right = 60
            new_w = width - crop_right
            new_h = height - crop_bottom
            filters.append(f"crop={new_w}:{new_h}:0:0")

        speed_factor = random.uniform(float(knobs["speed_lo"]), float(knobs["speed_hi"]))
        pts_factor = 1.0 / speed_factor
        filters.append(f"setpts={pts_factor:.4f}*PTS")

        hue_max = float(knobs["hue"])
        hue_shift = random.uniform(-hue_max, hue_max)
        sat_shift = random.uniform(float(knobs["sat_lo"]), float(knobs["sat_hi"]))
        brightness = random.uniform(-float(knobs["bright"]), float(knobs["bright"]))
        filters.append(f"eq=brightness={brightness:.3f}:saturation={sat_shift:.3f}")
        filters.append(f"hue=h={hue_shift:.1f}")

        zoom = random.uniform(float(knobs["zoom_lo"]), float(knobs["zoom_hi"]))
        filters.append(f"crop=iw*{zoom:.3f}:ih*{zoom:.3f}")

        applied = {
            "preset": preset,
            "speed_factor": round(speed_factor, 4),
            "hue_shift": round(hue_shift, 2),
            "sat_shift": round(sat_shift, 3),
            "brightness": round(brightness, 3),
            "zoom": round(zoom, 3),
            "logo": bool(logo_path),
        }

        # Logo overlay needs filter_complex — handled separately in process()
        return ",".join(filters), speed_factor, applied

    @classmethod
    def process(
        cls,
        input_path: str,
        platform: str = "unknown",
        output_dir: Optional[str] = None,
        preset: Optional[str] = None,
        force: bool = False,
        output_path: Optional[str] = None,
    ) -> ReupResult:
        """
        Pre-process video reup: watermark crop + anti-dupe + duration cap.

        Args:
            input_path: Path to downloaded video
            platform: Source platform (tiktok/youtube/facebook/instagram)
            output_dir: Output directory (default: same as input)
            preset: safe | aggressive | reels_short
            force: overwrite existing _reup output
            output_path: explicit output path (optional)
        """
        started_at = time.time()
        preset_key = normalize_preset(preset)
        knobs = dict(cls.PRESET_KNOBS.get(preset_key) or cls.PRESET_KNOBS["safe"])
        max_duration = float(knobs.get("max_duration") or cls.MAX_REELS_DURATION)
        crf = int(knobs.get("crf") or 26)
        cfg = load_reup_config()
        head_trim = float(cfg.get("audio_head_trim_sec") or 0)
        if head_trim < 0:
            head_trim = 0
        if head_trim > 0.5:
            head_trim = 0.5

        if not os.path.exists(input_path):
            return ReupResult(success=False, error=f"File not found: {input_path}")

        info = cls._get_video_info(input_path)
        duration = info["duration"]
        width = info["width"]
        height = info["height"]

        if width == 0 or height == 0:
            return ReupResult(success=False, error="Cannot read video dimensions")

        logger.info(
            "[ReupProcessor] Input: %s (%s) preset=%s — %dx%d, %.1fs",
            os.path.basename(input_path), platform, preset_key, width, height, duration,
        )

        if not output_dir:
            output_dir = os.path.dirname(input_path)
        base = os.path.splitext(os.path.basename(input_path))[0]
        # Avoid nesting _reup_reup when reprocessing a _reup source
        if base.endswith("_reup"):
            base = base[: -len("_reup")]
        if output_path is None:
            output_path = os.path.join(output_dir, f"{base}_reup.mp4")
        temp_path = os.path.join(output_dir, f"{base}_reup.tmp.mp4")

        if not force and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info("[ReupProcessor] Already processed, skipping: %s", output_path)
            return ReupResult(
                success=True,
                output_path=output_path,
                metrics={"mode": "skip_existing", "preset": preset_key},
            )

        logo_path = cls._resolve_logo_path()
        vf, speed_factor, applied = cls._build_filter_chain(
            platform, width, height, preset_key, logo_path=logo_path,
        )

        if sys.platform.startswith("win"):
            cmd = ["ffmpeg", "-y"]
        else:
            cmd = ["nice", "-n", "19", "ffmpeg", "-y"]

        # Phase C: micro head-trim changes audio fingerprint slightly
        if head_trim > 0 and duration > (head_trim + 2.0):
            cmd += ["-ss", f"{head_trim:.3f}"]

        cmd += ["-i", input_path]

        if logo_path:
            cmd += ["-i", logo_path]

        # Duration limit (after -ss, remaining length)
        effective_duration = duration - head_trim if head_trim > 0 else duration
        if effective_duration > max_duration:
            cmd += ["-t", str(max_duration)]
            logger.info(
                "[ReupProcessor] Cắt video → %ds (preset=%s)",
                int(max_duration),
                preset_key,
            )

        audio_filter = ""
        if abs(speed_factor - 1.0) > 0.001:
            audio_filter = f"atempo={speed_factor:.4f}"

        if logo_path:
            # Small brand mark, bottom-right (opt-in via reup_presets.json)
            complex_filter = (
                f"[0:v]{vf}[base];"
                f"[1:v]scale=120:-1[logo];"
                f"[base][logo]overlay=W-w-24:H-h-24[vout]"
            )
            cmd += ["-filter_complex", complex_filter, "-map", "[vout]"]
            if audio_filter:
                cmd += ["-af", audio_filter]
            cmd += ["-map", "0:a?"]
        elif audio_filter:
            cmd += ["-vf", vf, "-af", audio_filter]
        else:
            cmd += ["-vf", vf]

        cmd += [
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "ultrafast",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            temp_path,
        ]

        logger.info("[ReupProcessor] Filters preset=%s: %s", preset_key, vf)

        def _fast_trim_fallback() -> ReupResult:
            if duration <= max_duration:
                return ReupResult(success=False, error="Fallback not needed")

            logger.info("[ReupProcessor] Emergency fast-trim > %.0fs...", max_duration)
            trim_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-t", str(max_duration),
                "-c", "copy",
                temp_path,
            ]
            try:
                subprocess.run(trim_cmd, capture_output=True, timeout=60)
                if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                    output_info, gate_error = cls._promote_temp(
                        temp_path=temp_path,
                        output_path=output_path,
                        input_info=info,
                        max_duration=max_duration,
                    )
                    if gate_error:
                        return ReupResult(success=False, error=f"Quality gate failed: {gate_error}")
                    return ReupResult(
                        success=True,
                        output_path=output_path,
                        metrics={
                            "mode": "fast_trim",
                            "preset": preset_key,
                            "runtime_ms": int((time.time() - started_at) * 1000),
                            "input_duration": round(duration, 2),
                            "output_duration": round(float((output_info or {}).get("duration") or 0), 2),
                            "output_width": int((output_info or {}).get("width") or 0),
                            "output_height": int((output_info or {}).get("height") or 0),
                            "head_trim_sec": head_trim,
                        },
                    )
            except Exception:
                logger.exception("[ReupProcessor] Fast-trim failed")
            return ReupResult(success=False, error="Both processing and fast-trim failed")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )

            if result.returncode != 0:
                error = result.stderr[-300:] if result.stderr else "Unknown error"
                logger.error("[ReupProcessor] FFmpeg failed: %s", error[:200])
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                if duration > max_duration:
                    return _fast_trim_fallback()
                return ReupResult(success=False, error=error[:200])

            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                if duration > max_duration:
                    return _fast_trim_fallback()
                return ReupResult(success=False, error="FFmpeg produced empty output")

            output_info, gate_error = cls._promote_temp(
                temp_path=temp_path,
                output_path=output_path,
                input_info=info,
                max_duration=max_duration,
            )
            if gate_error:
                return ReupResult(success=False, error=f"Quality gate failed: {gate_error}")

            in_size = os.path.getsize(input_path) / 1024 / 1024
            out_size = os.path.getsize(output_path) / 1024 / 1024
            runtime_ms = int((time.time() - started_at) * 1000)
            metrics = {
                "mode": "anti_dupe",
                "preset": preset_key,
                "runtime_ms": runtime_ms,
                "input_duration": round(duration, 2),
                "output_duration": round(float((output_info or {}).get("duration") or 0), 2),
                "input_width": width,
                "input_height": height,
                "output_width": int((output_info or {}).get("width") or 0),
                "output_height": int((output_info or {}).get("height") or 0),
                "input_has_audio": bool(info.get("has_audio")),
                "output_has_audio": bool((output_info or {}).get("has_audio")),
                "input_size_mb": round(in_size, 2),
                "output_size_mb": round(out_size, 2),
                "filters": vf,
                "head_trim_sec": head_trim,
                "max_duration": max_duration,
                **applied,
            }
            logger.info(
                "[ReupProcessor] Done preset=%s runtime=%sms: %.1fMB → %.1fMB | %s",
                preset_key,
                runtime_ms,
                in_size,
                out_size,
                os.path.basename(output_path),
            )
            return ReupResult(success=True, output_path=output_path, metrics=metrics)

        except subprocess.TimeoutExpired:
            logger.warning("[ReupProcessor] FFmpeg timeout (>5 min)")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            if duration > max_duration:
                return _fast_trim_fallback()
            return ReupResult(success=False, error="FFmpeg timeout (>5 min)")
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            if duration > max_duration:
                return _fast_trim_fallback()
            return ReupResult(success=False, error=str(e))
