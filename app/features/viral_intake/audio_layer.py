"""
Lớp âm thanh cho video reup: voice-over tiếng Việt + nhạc nền (ADR-016).

Hàm thuần, không DB, không import lớp khác. Mỗi bước là một lần re-encode
audio (video luôn ``-c:v copy``), lỗi ở bước nào thì ghi warning và giữ video
của bước trước — lớp không bao giờ làm hỏng reup.

Voice-over:
    - Ưu tiên ``edge-tts`` (giọng ``vi-VN-HoaiMyNeural`` / ``vi-VN-NamMinhNeural``).
      edge-tts dùng endpoint của Microsoft Edge, KHÔNG có ToS chính thức cho việc
      này nên có thể bị chặn bất cứ lúc nào → luôn có ``piper-tts`` dự phòng
      offline (giọng ``vi_VN-vais1000-medium``, GPL-3 chỉ ràng buộc khi phân phối).
    - Model piper nằm ở ``storage/media/tts_models/<tên>.onnx`` (+ ``.onnx.json``).
      Tải bằng ``python -m piper.download_voices vi_VN-vais1000-medium`` trong
      thư mục đó.

Nhạc nền:
    - Tool KHÔNG tự tải nhạc. Owner tự bỏ file ``.mp3/.m4a/.wav`` vào
      ``storage/media/music/`` (thư mục nằm trong ``/storage/`` bị gitignore nên
      không được commit — hướng dẫn nguồn nhạc nằm ở README trong đó và lặp lại
      ở đây): Meta Sound Collection (facebook.com/sound) CHỈ được dùng cho nội
      dung đăng trên Facebook/Instagram; Pixabay Music dùng được rộng hơn. Không
      mass-download. Tool chọn ngẫu nhiên một file mỗi lần.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import subprocess
import unicodedata
import wave
from pathlib import Path
from typing import Any, Optional

from app import config as app_config
from app.core.media import ffmpeg_path

try:  # phụ thuộc tuỳ chọn — thiếu thì lớp chỉ báo False, không làm vỡ import
    import edge_tts
except ImportError:  # pragma: no cover - phụ thuộc vào môi trường
    edge_tts = None

try:
    from piper import PiperVoice
    from piper.config import SynthesisConfig
except ImportError:  # pragma: no cover - phụ thuộc vào môi trường
    PiperVoice = None
    SynthesisConfig = None

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_PIPER_MODEL = "vi_VN-vais1000-medium"
MAX_TEXT_CHARS = 1500
EDGE_TIMEOUT_SEC = 60
FFMPEG_TIMEOUT_SEC = 300
MUSIC_EXTS = (".mp3", ".m4a", ".wav")
MIN_OUTPUT_BYTES = 1024


def _ffmpeg_bin() -> str:
    return ffmpeg_path.ffmpeg_bin()


def _ffprobe_bin() -> str:
    return ffmpeg_path.ffprobe_bin()


def _piper_models_dir() -> Path:
    return Path(app_config.STORAGE_MEDIA_DIR) / "tts_models"


def _normalize_text(text: str) -> str:
    cleaned = unicodedata.normalize("NFC", str(text or "")).strip()
    return cleaned[:MAX_TEXT_CHARS]


def _rate_to_length_scale(rate: str) -> float:
    """edge-tts rate '+10%' → piper length_scale (nhanh hơn = scale nhỏ hơn)."""
    try:
        pct = float(str(rate or "+0%").strip().rstrip("%"))
    except ValueError:
        pct = 0.0
    pct = max(-50.0, min(100.0, pct))
    return round(1.0 / (1.0 + pct / 100.0), 3)


def _probe(path: str) -> dict[str, Any]:
    """duration + has_audio qua ffprobe; lỗi → duration 0, has_audio False."""
    empty = {"duration": 0.0, "has_audio": False}
    try:
        result = subprocess.run(
            [
                _ffprobe_bin(), "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout or "{}")
        has_audio = any(
            s.get("codec_type") == "audio" for s in data.get("streams", [])
        )
        return {
            "duration": float(data.get("format", {}).get("duration", 0) or 0),
            "has_audio": has_audio,
        }
    except Exception as e:  # noqa: BLE001 - lớp tuỳ chọn, không được raise
        logger.warning("[AudioLayer] ffprobe failed for %s: %s", path, e)
        return empty


def _run_ffmpeg(cmd: list[str], output_path: str, what: str) -> bool:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SEC,
        )
        if result.returncode != 0:
            err = (result.stderr or f"ffmpeg {what} failed")[-240:]
            logger.warning("[AudioLayer] %s failed: %s", what, err)
            _remove_quiet(output_path)
            return False
        if not os.path.isfile(output_path) or os.path.getsize(output_path) < MIN_OUTPUT_BYTES:
            logger.warning("[AudioLayer] %s produced empty file", what)
            _remove_quiet(output_path)
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning("[AudioLayer] %s timeout (>%ss)", what, FFMPEG_TIMEOUT_SEC)
        _remove_quiet(output_path)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("[AudioLayer] %s error: %s", what, e)
        _remove_quiet(output_path)
        return False


def _remove_quiet(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Voice-over
# ---------------------------------------------------------------------------

def _synth_edge(text: str, out_path: str, voice: str, rate: str) -> bool:
    if edge_tts is None:
        logger.warning("[AudioLayer] edge-tts not installed")
        return False

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await asyncio.wait_for(communicate.save(out_path), timeout=EDGE_TIMEOUT_SEC)

    try:
        asyncio.run(_run())
    except Exception as e:  # noqa: BLE001 - mạng/chặn/timeout đều rơi về piper
        logger.warning("[AudioLayer] edge-tts failed (%s): %s", type(e).__name__, e)
        _remove_quiet(out_path)
        return False
    if not os.path.isfile(out_path) or os.path.getsize(out_path) < MIN_OUTPUT_BYTES:
        logger.warning("[AudioLayer] edge-tts produced empty file")
        _remove_quiet(out_path)
        return False
    return True


def _synth_piper(
    text: str,
    out_path: str,
    rate: str,
    model_name: str = DEFAULT_PIPER_MODEL,
) -> bool:
    if PiperVoice is None:
        logger.warning("[AudioLayer] piper-tts not installed")
        return False
    model_path = _piper_models_dir() / f"{model_name}.onnx"
    if not model_path.is_file():
        logger.warning(
            "[AudioLayer] piper model missing: %s (run `python -m piper.download_voices %s` there)",
            model_path, model_name,
        )
        return False

    wav_tmp = out_path + ".piper.tmp.wav"
    try:
        voice_model = PiperVoice.load(str(model_path))
        syn_config = None
        if SynthesisConfig is not None:
            syn_config = SynthesisConfig(length_scale=_rate_to_length_scale(rate))
        with wave.open(wav_tmp, "wb") as wav_file:
            voice_model.synthesize_wav(text, wav_file, syn_config=syn_config)
    except Exception as e:  # noqa: BLE001
        logger.warning("[AudioLayer] piper failed (%s): %s", type(e).__name__, e)
        _remove_quiet(wav_tmp)
        return False

    if out_path.lower().endswith(".wav"):
        try:
            os.replace(wav_tmp, out_path)
            return True
        except OSError as e:
            logger.warning("[AudioLayer] piper cannot move wav: %s", e)
            _remove_quiet(wav_tmp)
            return False

    cmd = [_ffmpeg_bin(), "-y", "-i", wav_tmp, "-b:a", "128k", out_path]
    ok = _run_ffmpeg(cmd, out_path, "piper wav→audio")
    _remove_quiet(wav_tmp)
    return ok


def _try_engine(name: str, fn, *args) -> bool:
    """Một engine raise cũng chỉ là 'thất bại' — không được chặn engine kế tiếp."""
    try:
        return bool(fn(*args))
    except Exception as e:  # noqa: BLE001
        logger.warning("[AudioLayer] %s raised (%s): %s", name, type(e).__name__, e)
        return False


def synthesize_voice(
    text: str,
    out_path: str,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    engine: str = "auto",
) -> bool:
    """
    Đọc ``text`` thành file audio tại ``out_path`` (mp3/m4a/wav theo đuôi).

    ``engine``: ``auto`` (edge → piper), ``edge``, ``piper``. Không raise;
    trả False + warning khi mọi engine đều hỏng.
    """
    try:
        cleaned = _normalize_text(text)
        if not cleaned:
            logger.warning("[AudioLayer] synthesize_voice: empty text")
            return False
        engine_key = (engine or "auto").strip().lower()
        if engine_key not in ("auto", "edge", "piper"):
            engine_key = "auto"

        if engine_key in ("auto", "edge"):
            if _try_engine("edge-tts", _synth_edge, cleaned, out_path, voice, rate):
                logger.info("[AudioLayer] voice via edge-tts (%s)", voice)
                return True
            if engine_key == "edge":
                return False

        if _try_engine("piper", _synth_piper, cleaned, out_path, rate):
            logger.info("[AudioLayer] voice via piper (%s)", DEFAULT_PIPER_MODEL)
            return True
        logger.warning("[AudioLayer] synthesize_voice: all engines failed")
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("[AudioLayer] synthesize_voice error: %s", e)
        return False


def mix_voice(
    input_video: str,
    voice_path: str,
    output_path: str,
    *,
    original_volume: float = 0.25,
    voice_volume: float = 1.0,
) -> bool:
    """Trộn voice-over lên video; audio gốc hạ xuống ``original_volume``."""
    try:
        info = _probe(input_video)
        orig = max(0.0, float(original_volume))
        vol = max(0.0, float(voice_volume))
        cmd = [_ffmpeg_bin(), "-y", "-i", input_video, "-i", voice_path]
        if info.get("has_audio"):
            filter_complex = (
                f"[0:a]volume={orig:.3f}[a0];"
                f"[1:a]volume={vol:.3f}[a1];"
                "[a0][a1]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
            )
            cmd += ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[a]"]
        else:
            # Video câm: chỉ lấy voice, cắt theo video
            cmd += [
                "-filter_complex", f"[1:a]volume={vol:.3f}[a]",
                "-map", "0:v", "-map", "[a]", "-shortest",
            ]
        cmd += [
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]
        return _run_ffmpeg(cmd, output_path, "mix_voice")
    except Exception as e:  # noqa: BLE001
        logger.warning("[AudioLayer] mix_voice error: %s", e)
        return False


# ---------------------------------------------------------------------------
# Nhạc nền
# ---------------------------------------------------------------------------

def pick_music(music_dir: Optional[str], *, seed: Optional[int] = None) -> Optional[str]:
    """Chọn ngẫu nhiên một file nhạc trong thư mục; không có → None."""
    if not music_dir:
        return None
    try:
        folder = Path(music_dir)
        if not folder.is_dir():
            return None
        files = sorted(
            str(p) for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in MUSIC_EXTS
        )
        if not files:
            return None
        rng = random.Random(seed) if seed is not None else random
        return rng.choice(files)
    except Exception as e:  # noqa: BLE001
        logger.warning("[AudioLayer] pick_music error: %s", e)
        return None


def mix_music(
    input_video: str,
    music_path: str,
    output_path: str,
    *,
    music_volume: float = 0.12,
    fade_sec: float = 1.5,
) -> bool:
    """Trộn nhạc nền (lặp nếu ngắn hơn video, fade-out ở cuối)."""
    try:
        info = _probe(input_video)
        duration = float(info.get("duration") or 0)
        vol = max(0.0, float(music_volume))
        fade = max(0.0, float(fade_sec))
        music_chain = f"[1:a]volume={vol:.3f}"
        if duration > 0 and fade > 0:
            fade = min(fade, duration / 2)
            music_chain += f",afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}"
        cmd = [
            _ffmpeg_bin(), "-y",
            "-i", input_video,
            "-stream_loop", "-1", "-i", music_path,
        ]
        if info.get("has_audio"):
            filter_complex = (
                "[0:a]volume=1.000[a0];"
                f"{music_chain}[a1];"
                "[a0][a1]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
            )
        else:
            filter_complex = f"{music_chain}[a]"
        cmd += ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[a]"]
        if duration > 0:
            cmd += ["-t", f"{duration:.3f}"]
        else:
            cmd += ["-shortest"]
        cmd += [
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]
        return _run_ffmpeg(cmd, output_path, "mix_music")
    except Exception as e:  # noqa: BLE001
        logger.warning("[AudioLayer] mix_music error: %s", e)
        return False


# ---------------------------------------------------------------------------
# Điểm vào duy nhất
# ---------------------------------------------------------------------------

def apply(
    input_path: str,
    output_path: str,
    *,
    voice_text: Optional[str] = None,
    voice: str = DEFAULT_VOICE,
    voice_rate: str = "+0%",
    voice_engine: str = "auto",
    music_dir: Optional[str] = None,
    music_volume: float = 0.12,
    original_volume: float = 0.25,
) -> bool:
    """
    Voice-over (nếu ``voice_text``) rồi nhạc nền (nếu ``music_dir`` có file).

    Mỗi bước hỏng → warning, tiếp tục với video hiện tại. Không bước nào thành
    công → False và KHÔNG tạo ``output_path``. File tạm nằm cạnh output, xoá sau.
    """
    voice_tmp = output_path + ".voice.tmp.mp3"
    step_voice = output_path + ".voice.tmp.mp4"
    step_music = output_path + ".music.tmp.mp4"
    temps = [voice_tmp, step_voice, step_music]
    try:
        if not os.path.isfile(input_path):
            logger.warning("[AudioLayer] input missing: %s", input_path)
            return False

        current = input_path
        applied: list[str] = []

        text = _normalize_text(voice_text or "")
        if text:
            if synthesize_voice(
                text, voice_tmp, voice=voice, rate=voice_rate, engine=voice_engine,
            ) and mix_voice(
                current, voice_tmp, step_voice, original_volume=original_volume,
            ):
                current = step_voice
                applied.append("voice")
            else:
                logger.warning("[AudioLayer] voice step skipped")

        music = pick_music(music_dir)
        if music:
            if mix_music(current, music, step_music, music_volume=music_volume):
                current = step_music
                applied.append("music")
            else:
                logger.warning("[AudioLayer] music step skipped")

        if not applied:
            return False

        os.replace(current, output_path)
        logger.info(
            "[AudioLayer] applied %s → %s", "+".join(applied), os.path.basename(output_path),
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[AudioLayer] apply error: %s", e)
        return False
    finally:
        for tmp in temps:
            _remove_quiet(tmp)
