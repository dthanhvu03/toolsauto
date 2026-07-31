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

from app.core.media import ffmpeg_path
from app.features.viral_intake.reup_config import (
    load_reup_config,
    list_media_pool,
    normalize_preset,
    resolve_intro_path,
    resolve_outro_path,
    resolve_hook_text,
)

logger = logging.getLogger(__name__)


def _ffmpeg_bin() -> str:
    return ffmpeg_path.ffmpeg_bin()


def _ffprobe_bin() -> str:
    return ffmpeg_path.ffprobe_bin()


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
    def _parse_rate(raw: Any, default: float) -> float:
        """Parse ffprobe rate like '30/1' or '29.97' → float."""
        if raw is None or raw == "" or raw == "0/0":
            return default
        try:
            s = str(raw).strip()
            if "/" in s:
                a, b = s.split("/", 1)
                den = float(b)
                if den == 0:
                    return default
                return float(a) / den
            return float(s)
        except (TypeError, ValueError, ZeroDivisionError):
            return default

    @staticmethod
    def _get_video_info(video_path: str) -> dict:
        """Lấy thông tin video: duration, WxH, fps, sample_rate, has_audio."""
        empty = {
            "duration": 0.0,
            "width": 0,
            "height": 0,
            "has_audio": False,
            "fps": 30.0,
            "sample_rate": 44100,
        }
        try:
            result = subprocess.run(
                [
                    _ffprobe_bin(), "-v", "quiet",
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
            fps = ReupProcessor._parse_rate(
                video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"),
                30.0,
            )
            if fps < 12 or fps > 60:
                fps = 30.0
            sr = int(audio_stream.get("sample_rate") or 44100)
            if sr < 8000 or sr > 96000:
                sr = 44100
            return {
                "duration": float(data.get("format", {}).get("duration", 0)),
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "has_audio": bool(audio_stream),
                "fps": round(fps, 3),
                "sample_rate": sr,
            }
        except Exception:
            logger.exception("[ReupProcessor] ffprobe failed")
            return empty

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
        target_w: Optional[int] = None,
        target_h: Optional[int] = None,
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

        tw = int(target_w or 0)
        th = int(target_h or 0)
        reels_canvas = False
        if tw >= 640 and th >= 640 and tw % 2 == 0 and th % 2 == 0:
            # Cover → exact Reels canvas (lanczos). Không upscale 4K.
            filters.append(
                f"scale={tw}:{th}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={tw}:{th},setsar=1"
            )
            reels_canvas = True

        applied = {
            "preset": preset,
            "speed_factor": round(speed_factor, 4),
            "hue_shift": round(hue_shift, 2),
            "sat_shift": round(sat_shift, 3),
            "brightness": round(brightness, 3),
            "zoom": round(zoom, 3),
            "logo": bool(logo_path),
            "reels_1080": reels_canvas,
            "target_width": tw if reels_canvas else 0,
            "target_height": th if reels_canvas else 0,
        }

        # Logo overlay needs filter_complex — handled separately in process()
        return ",".join(filters), speed_factor, applied

    @classmethod
    def _prepend_intro(
        cls,
        main_path: str,
        intro_path: str,
        output_path: str,
        max_intro_sec: float = 3.0,
        fade_sec: float = 0.28,
        scale_mode: str = "cover",
    ) -> tuple[bool, str | None]:
        """
        Join [intro ≤ max_intro_sec] + main → output_path.

        Khớp theo video chính: WxH, fps, sample_rate, yuv420p, SAR=1.
        Scale intro cover (crop) hoặc contain (pad). Optional xfade/acrossfade.
        """
        main = cls._get_video_info(main_path)
        intro_info = cls._get_video_info(intro_path)
        w = int(main.get("width") or 0)
        h = int(main.get("height") or 0)
        if w < 16 or h < 16:
            return False, "main video has invalid dimensions"

        max_intro_sec = max(0.5, min(5.0, float(max_intro_sec or 3.0)))
        intro_src_dur = float(intro_info.get("duration") or 0)
        intro_dur = min(max_intro_sec, intro_src_dur) if intro_src_dur > 0.05 else max_intro_sec
        intro_dur = max(0.5, intro_dur)

        fps = float(main.get("fps") or 30.0)
        sr = int(main.get("sample_rate") or 44100)
        intro_has_audio = bool(intro_info.get("has_audio"))
        main_has_audio = bool(main.get("has_audio"))
        main_dur = float(main.get("duration") or 1.0)
        if main_dur < 0.5:
            main_dur = 1.0

        mode = (scale_mode or "cover").strip().lower()
        if mode == "contain":
            scale_chain = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
            )
        else:
            # cover: full-bleed, crop center — khớp khung hình body
            scale_chain = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}"
            )

        # Normalize both legs to identical geometry / timing base
        v_intro = (
            f"[0:v]trim=duration={intro_dur:.3f},setpts=PTS-STARTPTS,"
            f"{scale_chain},setsar=1,fps={fps:.3f},format=yuv420p[v0]"
        )
        v_main = (
            f"[1:v]setpts=PTS-STARTPTS,setsar=1,fps={fps:.3f},format=yuv420p[v1]"
        )

        a_fmt = f"aformat=sample_rates={sr}:channel_layouts=stereo"
        parts = [v_intro, v_main]
        if intro_has_audio:
            parts.append(
                f"[0:a]atrim=0:{intro_dur:.3f},asetpts=PTS-STARTPTS,{a_fmt}[a0]"
            )
        else:
            parts.append(
                f"anullsrc=channel_layout=stereo:sample_rate={sr},"
                f"atrim=0:{intro_dur:.3f},asetpts=PTS-STARTPTS[a0]"
            )
        if main_has_audio:
            parts.append(f"[1:a]asetpts=PTS-STARTPTS,{a_fmt}[a1]")
        else:
            parts.append(
                f"anullsrc=channel_layout=stereo:sample_rate={sr},"
                f"atrim=0:{main_dur:.3f},asetpts=PTS-STARTPTS[a1]"
            )

        fade = max(0.0, min(0.5, float(fade_sec or 0.0)))
        # Need headroom so xfade offset stays inside intro
        if fade > 0.04 and intro_dur > (fade + 0.12):
            offset = intro_dur - fade
            parts.append(
                f"[v0][v1]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}[outv]"
            )
            parts.append(
                f"[a0][a1]acrossfade=d={fade:.3f}:c1=tri:c2=tri[outa]"
            )
        else:
            parts.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]")

        filter_complex = ";".join(parts)

        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            intro_path,
            "-i",
            main_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-r",
            f"{fps:.3f}",
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            str(sr),
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            output_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                err = (result.stderr or "ffmpeg intro concat failed")[-240:]
                return False, err
            if not os.path.isfile(output_path) or os.path.getsize(output_path) < 1024:
                return False, "intro concat produced empty file"
            return True, None
        except subprocess.TimeoutExpired:
            return False, "intro concat timeout"
        except Exception as e:
            return False, str(e)

    @classmethod
    def _maybe_apply_intro(
        cls,
        body_path: str,
        *,
        page_url: Optional[str],
        niches: Optional[list[str]],
        account_id: Optional[int],
        intro_path: Optional[str],
        metrics: dict[str, Any],
    ) -> str:
        """If intro resolves, prepend onto body and return final path (else body_path)."""
        cfg = load_reup_config()
        max_sec = float(cfg.get("intro_max_sec") or 3.0)
        fade_sec = float(cfg.get("intro_fade_sec") if cfg.get("intro_fade_sec") is not None else 0.28)
        scale_mode = str(cfg.get("intro_scale_mode") or "cover")
        resolved = resolve_intro_path(
            page_url=page_url,
            niches=niches,
            account_id=account_id,
            explicit=intro_path,
        )
        metrics["intro_enabled"] = bool(cfg.get("intro_enabled"))
        metrics["intro_resolved"] = resolved
        if not resolved:
            metrics["intro_applied"] = False
            return body_path

        intro_out = body_path + ".with_intro.tmp.mp4"
        ok, err = cls._prepend_intro(
            main_path=body_path,
            intro_path=resolved,
            output_path=intro_out,
            max_intro_sec=max_sec,
            fade_sec=fade_sec,
            scale_mode=scale_mode,
        )
        if not ok:
            logger.warning("[ReupProcessor] intro skip: %s", err)
            metrics["intro_applied"] = False
            metrics["intro_error"] = (err or "")[:160]
            try:
                if os.path.isfile(intro_out):
                    os.remove(intro_out)
            except OSError:
                pass
            return body_path

        try:
            os.replace(intro_out, body_path)
            metrics["intro_applied"] = True
            metrics["intro_path"] = resolved
            metrics["intro_pool_size"] = len(
                list_media_pool(str(Path(resolved).parent))
            ) if resolved else 0
            metrics["intro_max_sec"] = max_sec
            metrics["intro_fade_sec"] = fade_sec
            metrics["intro_scale_mode"] = scale_mode
            logger.info(
                "[ReupProcessor] Intro applied (%ss fade=%.2fs mode=%s): %s → %s",
                max_sec,
                fade_sec,
                scale_mode,
                os.path.basename(resolved),
                os.path.basename(body_path),
            )
        except OSError as e:
            metrics["intro_applied"] = False
            metrics["intro_error"] = str(e)[:160]
            try:
                if os.path.isfile(intro_out):
                    os.remove(intro_out)
            except OSError:
                pass
        return body_path

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        # ffmpeg drawtext special chars
        return (
            (text or "")
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace("%", "\\%")
        )

    @classmethod
    def _maybe_apply_hook(
        cls,
        body_path: str,
        *,
        page_url: Optional[str],
        niches: Optional[list[str]],
        account_id: Optional[int],
        hook_text: Optional[str],
        metrics: dict[str, Any],
    ) -> str:
        """Burn hook text onto first N seconds of body (before intro)."""
        cfg = load_reup_config()
        max_sec = float(cfg.get("hook_max_sec") or 2.0)
        max_sec = max(0.5, min(4.0, max_sec))
        text = resolve_hook_text(
            page_url=page_url,
            niches=niches,
            account_id=account_id,
            explicit=hook_text,
        )
        metrics["hook_enabled"] = bool(cfg.get("hook_enabled"))
        metrics["hook_text"] = text
        if not text:
            metrics["hook_applied"] = False
            return body_path

        info = cls._get_video_info(body_path)
        w = int(info.get("width") or 0)
        h = int(info.get("height") or 0)
        if w < 16 or h < 16:
            metrics["hook_applied"] = False
            metrics["hook_error"] = "invalid dimensions"
            return body_path

        fontsize = max(28, min(64, int(w * 0.055)))
        escaped = cls._escape_drawtext(text)
        # Safe-ish upper third for Reels/TikTok
        y_expr = "h*0.16"
        from app.core.media.video_protector import VideoProtector

        font_arg = VideoProtector.ffmpeg_fontfile_arg()
        vf = (
            f"drawtext=text='{escaped}':fontsize={fontsize}:fontcolor=white:"
            f"borderw=3:bordercolor=black@0.85{font_arg}:x=(w-text_w)/2:y={y_expr}:"
            f"enable='between(t,0,{max_sec:.3f})'"
        )
        out = body_path + ".with_hook.tmp.mp4"
        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            body_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "veryfast",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            out,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) < 1024:
                err = (result.stderr or "hook drawtext failed")[-200:]
                logger.warning("[ReupProcessor] hook skip: %s", err)
                metrics["hook_applied"] = False
                metrics["hook_error"] = err[:160]
                try:
                    if os.path.isfile(out):
                        os.remove(out)
                except OSError:
                    pass
                return body_path
            os.replace(out, body_path)
            metrics["hook_applied"] = True
            metrics["hook_max_sec"] = max_sec
            logger.info("[ReupProcessor] Hook applied (%ss): %s", max_sec, text[:40])
        except Exception as e:
            metrics["hook_applied"] = False
            metrics["hook_error"] = str(e)[:160]
            try:
                if os.path.isfile(out):
                    os.remove(out)
            except OSError:
                pass
        return body_path

    @classmethod
    def _maybe_apply_outro(
        cls,
        body_path: str,
        *,
        page_url: Optional[str],
        niches: Optional[list[str]],
        account_id: Optional[int],
        outro_path: Optional[str],
        metrics: dict[str, Any],
    ) -> str:
        """If outro resolves, append after body and return final path."""
        cfg = load_reup_config()
        max_sec = float(cfg.get("outro_max_sec") or 2.5)
        fade_sec = float(cfg.get("outro_fade_sec") if cfg.get("outro_fade_sec") is not None else 0.28)
        scale_mode = str(cfg.get("outro_scale_mode") or "cover")
        resolved = resolve_outro_path(
            page_url=page_url,
            niches=niches,
            account_id=account_id,
            explicit=outro_path,
        )
        metrics["outro_enabled"] = bool(cfg.get("outro_enabled"))
        metrics["outro_resolved"] = resolved
        if not resolved:
            metrics["outro_applied"] = False
            return body_path

        # Reuse prepend filter stack but with body as [0] and outro as [1]
        # Easiest: call _prepend_intro with swapped roles via a dedicated append helper.
        outro_out = body_path + ".with_outro.tmp.mp4"
        ok, err = cls._append_outro(
            main_path=body_path,
            outro_path=resolved,
            output_path=outro_out,
            max_outro_sec=max_sec,
            fade_sec=fade_sec,
            scale_mode=scale_mode,
        )
        if not ok:
            logger.warning("[ReupProcessor] outro skip: %s", err)
            metrics["outro_applied"] = False
            metrics["outro_error"] = (err or "")[:160]
            try:
                if os.path.isfile(outro_out):
                    os.remove(outro_out)
            except OSError:
                pass
            return body_path

        try:
            os.replace(outro_out, body_path)
            metrics["outro_applied"] = True
            metrics["outro_path"] = resolved
            metrics["outro_max_sec"] = max_sec
            metrics["outro_fade_sec"] = fade_sec
            logger.info(
                "[ReupProcessor] Outro applied (%ss): %s",
                max_sec,
                os.path.basename(resolved),
            )
        except OSError as e:
            metrics["outro_applied"] = False
            metrics["outro_error"] = str(e)[:160]
            try:
                if os.path.isfile(outro_out):
                    os.remove(outro_out)
            except OSError:
                pass
        return body_path

    @classmethod
    def _append_outro(
        cls,
        main_path: str,
        outro_path: str,
        output_path: str,
        max_outro_sec: float = 2.5,
        fade_sec: float = 0.28,
        scale_mode: str = "cover",
    ) -> tuple[bool, str | None]:
        """Join main + [outro ≤ max] → output_path (match main WxH/fps/audio)."""
        main = cls._get_video_info(main_path)
        outro_info = cls._get_video_info(outro_path)
        w = int(main.get("width") or 0)
        h = int(main.get("height") or 0)
        if w < 16 or h < 16:
            return False, "main video has invalid dimensions"

        max_outro_sec = max(0.5, min(5.0, float(max_outro_sec or 2.5)))
        outro_src_dur = float(outro_info.get("duration") or 0)
        outro_dur = min(max_outro_sec, outro_src_dur) if outro_src_dur > 0.05 else max_outro_sec
        outro_dur = max(0.5, outro_dur)

        fps = float(main.get("fps") or 30.0)
        sr = int(main.get("sample_rate") or 44100)
        outro_has_audio = bool(outro_info.get("has_audio"))
        main_has_audio = bool(main.get("has_audio"))
        main_dur = float(main.get("duration") or 1.0)
        if main_dur < 0.5:
            main_dur = 1.0

        mode = (scale_mode or "cover").strip().lower()
        if mode == "contain":
            scale_chain = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
            )
        else:
            scale_chain = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}"
            )

        v_main = f"[0:v]setpts=PTS-STARTPTS,setsar=1,fps={fps:.3f},format=yuv420p[v0]"
        v_outro = (
            f"[1:v]trim=duration={outro_dur:.3f},setpts=PTS-STARTPTS,"
            f"{scale_chain},setsar=1,fps={fps:.3f},format=yuv420p[v1]"
        )
        a_fmt = f"aformat=sample_rates={sr}:channel_layouts=stereo"
        parts = [v_main, v_outro]
        if main_has_audio:
            parts.append(f"[0:a]asetpts=PTS-STARTPTS,{a_fmt}[a0]")
        else:
            parts.append(
                f"anullsrc=channel_layout=stereo:sample_rate={sr},"
                f"atrim=0:{main_dur:.3f},asetpts=PTS-STARTPTS[a0]"
            )
        if outro_has_audio:
            parts.append(
                f"[1:a]atrim=0:{outro_dur:.3f},asetpts=PTS-STARTPTS,{a_fmt}[a1]"
            )
        else:
            parts.append(
                f"anullsrc=channel_layout=stereo:sample_rate={sr},"
                f"atrim=0:{outro_dur:.3f},asetpts=PTS-STARTPTS[a1]"
            )

        fade = max(0.0, min(0.5, float(fade_sec or 0.0)))
        if fade > 0.04 and main_dur > (fade + 0.12) and outro_dur > (fade + 0.12):
            offset = main_dur - fade
            parts.append(
                f"[v0][v1]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}[outv]"
            )
            parts.append(f"[a0][a1]acrossfade=d={fade:.3f}:c1=tri:c2=tri[outa]")
        else:
            parts.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]")

        filter_complex = ";".join(parts)
        cmd = [
            _ffmpeg_bin(),
            "-y",
            "-i",
            main_path,
            "-i",
            outro_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-r",
            f"{fps:.3f}",
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            str(sr),
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            output_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                return False, (result.stderr or "ffmpeg outro concat failed")[-240:]
            if not os.path.isfile(output_path) or os.path.getsize(output_path) < 1024:
                return False, "outro concat produced empty file"
            return True, None
        except subprocess.TimeoutExpired:
            return False, "outro concat timeout"
        except Exception as e:
            return False, str(e)

    @classmethod
    def process(
        cls,
        input_path: str,
        platform: str = "unknown",
        output_dir: Optional[str] = None,
        preset: Optional[str] = None,
        force: bool = False,
        output_path: Optional[str] = None,
        page_url: Optional[str] = None,
        niches: Optional[list[str]] = None,
        account_id: Optional[int] = None,
        intro_path: Optional[str] = None,
        outro_path: Optional[str] = None,
        hook_text: Optional[str] = None,
    ) -> ReupResult:
        """
        Pre-process video reup: anti-dupe + hook text + brand intro + brand outro.

        Args:
            input_path: Path to downloaded video
            platform: Source platform (tiktok/youtube/facebook/instagram)
            output_dir: Output directory (default: same as input)
            preset: safe | aggressive | reels_short
            force: overwrite existing _reup output
            output_path: explicit output path (optional)
            page_url / niches / account_id: resolve brand intro/outro/hook
            intro_path / outro_path / hook_text: explicit overrides
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

        reels_1080 = bool(cfg.get("reels_1080_enabled"))
        target_w = target_h = None
        x264_preset = "ultrafast"
        if reels_1080:
            try:
                tw = int(cfg.get("reels_target_width") or 1080)
                th = int(cfg.get("reels_target_height") or 1920)
            except (TypeError, ValueError):
                tw, th = 1080, 1920
            # Even dims only; clamp to social-safe canvas (no 4K)
            tw = max(640, min(1080, tw - (tw % 2)))
            th = max(640, min(1920, th - (th % 2)))
            target_w, target_h = tw, th
            try:
                crf = int(cfg.get("reels_1080_crf") or 23)
            except (TypeError, ValueError):
                crf = 23
            crf = max(16, min(28, crf))
            x264_preset = str(cfg.get("reels_1080_x264_preset") or "veryfast").strip() or "veryfast"
            if x264_preset not in (
                "ultrafast", "superfast", "veryfast", "faster", "fast", "medium",
            ):
                x264_preset = "veryfast"

        if not os.path.exists(input_path):
            return ReupResult(success=False, error=f"File not found: {input_path}")

        info = cls._get_video_info(input_path)
        duration = info["duration"]
        width = info["width"]
        height = info["height"]

        if width == 0 or height == 0:
            return ReupResult(success=False, error="Cannot read video dimensions")

        logger.info(
            "[ReupProcessor] Input: %s (%s) preset=%s reels1080=%s — %dx%d, %.1fs",
            os.path.basename(input_path),
            platform,
            preset_key,
            reels_1080,
            width,
            height,
            duration,
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
            platform,
            width,
            height,
            preset_key,
            logo_path=logo_path,
            target_w=target_w,
            target_h=target_h,
        )

        if sys.platform.startswith("win"):
            cmd = [_ffmpeg_bin(), "-y"]
        else:
            cmd = ["nice", "-n", "19", _ffmpeg_bin(), "-y"]

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
            "-preset", x264_preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            temp_path,
        ]

        logger.info(
            "[ReupProcessor] Filters preset=%s crf=%s x264=%s: %s",
            preset_key,
            crf,
            x264_preset,
            vf,
        )

        def _fast_trim_fallback() -> ReupResult:
            if duration <= max_duration:
                return ReupResult(success=False, error="Fallback not needed")

            logger.info("[ReupProcessor] Emergency fast-trim > %.0fs...", max_duration)
            trim_cmd = [
                _ffmpeg_bin(), "-y", "-i", input_path,
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
                "crf": crf,
                "x264_preset": x264_preset,
                **applied,
            }
            output_path = cls._maybe_apply_hook(
                output_path,
                page_url=page_url,
                niches=niches,
                account_id=account_id,
                hook_text=hook_text,
                metrics=metrics,
            )
            output_path = cls._maybe_apply_intro(
                output_path,
                page_url=page_url,
                niches=niches,
                account_id=account_id,
                intro_path=intro_path,
                metrics=metrics,
            )
            output_path = cls._maybe_apply_outro(
                output_path,
                page_url=page_url,
                niches=niches,
                account_id=account_id,
                outro_path=outro_path,
                metrics=metrics,
            )
            if metrics.get("intro_applied") or metrics.get("outro_applied") or metrics.get("hook_applied"):
                # Refresh size/duration after VIP stages
                try:
                    out_info2 = cls._get_video_info(output_path)
                    metrics["output_duration"] = round(float(out_info2.get("duration") or 0), 2)
                    metrics["output_size_mb"] = round(
                        os.path.getsize(output_path) / 1024 / 1024, 2
                    )
                except OSError:
                    pass
                metrics["runtime_ms"] = int((time.time() - started_at) * 1000)
            logger.info(
                "[ReupProcessor] Done preset=%s runtime=%sms: %.1fMB → %.1fMB | %s",
                preset_key,
                metrics["runtime_ms"],
                in_size,
                metrics.get("output_size_mb", out_size),
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
