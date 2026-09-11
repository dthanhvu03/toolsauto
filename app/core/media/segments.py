"""
ADR-041 — tín hiệu để chọn chỗ cắt trong một video dài.

Ba tín hiệu, xếp từ "hiểu nội dung" xuống "chỉ thấy bề mặt":

1. ``transcript_segments`` — lời thoại **kèm mốc giây từng câu** (Whisper, dùng lại model đã
   cache cho caption). Đây là tín hiệu duy nhất biết *đang kể tới đâu*.
2. ``silences`` — khoảng lặng (``silencedetect``): ranh giới câu / hơi thở, cắt ở đây không
   đứt lời.
3. ``scene_changes`` — đổi cảnh (``scdet``): ranh giới hình.

Mọi hàm ở đây **không raise**: tín hiệu thiếu thì trả rỗng, tầng trên tự lùi về cách thô hơn
và nói rõ mình đã lùi. Không được im lặng trả kết quả "đẹp" từ dữ liệu không có.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass

from app.core.media import ffmpeg_path

logger = logging.getLogger(__name__)

_SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)")
_SCENE_PTS_RE = re.compile(r"pts_time:([0-9.]+)")


@dataclass(frozen=True)
class Silence:
    start: float
    end: float

    @property
    def mid(self) -> float:
        return (self.start + self.end) / 2.0


@dataclass(frozen=True)
class Line:
    """Một câu lời thoại: nói từ ``start`` tới ``end``."""

    start: float
    end: float
    text: str


def silences(video_path: str, *, noise_db: int = -30, min_sec: float = 0.35, timeout: int = 300) -> list[Silence]:
    """Khoảng lặng dài ≥ ``min_sec`` giây. Chỉ giải mã audio nên nhanh."""
    if not video_path or not os.path.isfile(video_path):
        return []
    try:
        proc = subprocess.run(
            [
                ffmpeg_path.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", video_path, "-vn",
                "-af", f"silencedetect=noise={noise_db}dB:d={min_sec}", "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as exc:
        logger.warning("[SEGMENTS] silencedetect hỏng (%s) — coi như không có khoảng lặng.", exc)
        return []
    out: list[Silence] = []
    for m in _SILENCE_END_RE.finditer(proc.stderr or ""):
        end, dur = float(m.group(1)), float(m.group(2))
        out.append(Silence(start=max(0.0, end - dur), end=end))
    return out


def scene_changes(video_path: str, *, threshold: float = 0.35, timeout: int = 600) -> list[float]:
    """Mốc đổi cảnh. Thu nhỏ khung trước khi so để không giải mã full-HD cả video."""
    if not video_path or not os.path.isfile(video_path):
        return []
    try:
        proc = subprocess.run(
            [
                ffmpeg_path.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", video_path, "-an",
                "-vf", f"scale=160:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as exc:
        logger.warning("[SEGMENTS] scdet hỏng (%s) — coi như không có đổi cảnh.", exc)
        return []
    return [float(m.group(1)) for m in _SCENE_PTS_RE.finditer(proc.stderr or "")]


def transcript_segments(video_path: str, *, timeout: int = 60) -> list[Line]:
    """
    Lời thoại kèm mốc giây từng câu. Dùng lại Whisper đã cache trong ``ContentOrchestrator``
    (cùng một model, khỏi nạp lần hai — nạp ``medium`` mất hàng chục giây).

    Rỗng khi: không có audio, không có ``faster_whisper``, hay Whisper hỏng.
    """
    if not video_path or not os.path.isfile(video_path):
        return []
    audio_path = video_path + ".split-audio.mp3"
    try:
        subprocess.run(
            [ffmpeg_path.ffmpeg_bin(), "-y", "-loglevel", "error", "-i", video_path,
             "-vn", "-q:a", "4", "-map", "a", audio_path],
            capture_output=True, timeout=timeout,
        )
        if not os.path.isfile(audio_path) or os.path.getsize(audio_path) == 0:
            return []
        from app.core.orchestrator import ContentOrchestrator

        model = ContentOrchestrator._get_whisper_model()
        segs, _info = model.transcribe(audio_path, beam_size=2, vad_filter=True)
        out: list[Line] = []
        for seg in segs:
            text = (getattr(seg, "text", "") or "").strip()
            if text:
                out.append(Line(start=float(seg.start), end=float(seg.end), text=text))
        return out
    except Exception as exc:
        logger.warning("[SEGMENTS] Whisper hỏng (%s) — không có lời thoại để chọn chỗ cắt.", exc)
        return []
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


def snap_to_boundary(t: float, *, silence_list: list[Silence], scenes: list[float], window: float = 6.0) -> float | None:
    """
    Kéo mốc ``t`` về ranh giới gần nhất trong ±``window`` giây: **ưu tiên khoảng lặng** (cắt ở
    giữa khoảng lặng là không đứt lời), không có thì đổi cảnh. Không có gì ⇒ ``None`` — người
    gọi tự quyết, hàm này không đoán.
    """
    best: float | None = None
    best_d = window + 1e-9
    for s in silence_list:
        d = abs(s.mid - t)
        if d < best_d:
            best, best_d = s.mid, d
    if best is not None:
        return best
    for sc in scenes:
        d = abs(sc - t)
        if d < best_d:
            best, best_d = sc, d
    return best
