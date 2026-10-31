"""
Đọc chữ thành giọng: VieNeu-TTS (server cục bộ trên GPU, PLAN-111) → ``edge-tts`` → ``piper-tts`` offline
(VieNeu và piper chỉ giọng Việt).

Port từ ``viral_intake.audio_layer`` (ADR-016) để Studio dùng chung — lồng tiếng (``studio/dub``)
và giọng đọc AI (P5). Bản cũ giữ nguyên tới PLAN-106 P6.

edge-tts dùng endpoint của Microsoft Edge, không có ToS chính thức, có thể bị chặn bất cứ lúc
nào — vì vậy luôn có piper. Model piper ở ``storage/media/tts_models/<tên>.onnx``.

VieNeu chạy ở venv riêng (``studio/dub/vieneu_server.py``, PM2 ``VieNeu_TTS``); ở đây chỉ gọi HTTP
``VIENEU_TTS_URL`` (mặc định ``http://127.0.0.1:8790``, rỗng = tắt). Server tắt thì rơi xuống edge ngay.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import unicodedata
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Optional

from app import config as app_config
from app.core.media import ffmpeg_path

try:  # phụ thuộc tuỳ chọn — thiếu thì chỉ báo False, không làm vỡ import
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
MIN_OUTPUT_BYTES = 1024
DEFAULT_VIENEU_URL = "http://127.0.0.1:8790"
VIENEU_TIMEOUT_SEC = 120
VIENEU_HEALTH_TIMEOUT_SEC = 3
# giọng edge tiếng Việt → giọng VieNeu cùng giới (bước dub chọn giọng theo tên edge)
VIENEU_FEMALE = "Ngọc Huyền"
VIENEU_MALE = "Hải Đăng"
_EDGE_VI_MALE = {"vi-VN-NamMinhNeural"}


def _ffmpeg_bin() -> str:
    return ffmpeg_path.ffmpeg_bin()


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


def _run_ffmpeg(cmd: list[str], output_path: str, what: str) -> bool:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SEC,
        )
        if result.returncode != 0:
            err = (result.stderr or f"ffmpeg {what} failed")[-240:]
            logger.warning("[tts] %s failed: %s", what, err)
            _remove_quiet(output_path)
            return False
        if not os.path.isfile(output_path) or os.path.getsize(output_path) < MIN_OUTPUT_BYTES:
            logger.warning("[tts] %s produced empty file", what)
            _remove_quiet(output_path)
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning("[tts] %s timeout (>%ss)", what, FFMPEG_TIMEOUT_SEC)
        _remove_quiet(output_path)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("[tts] %s error: %s", what, e)
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


def _synth_edge(text: str, out_path: str, voice: str, rate: str) -> bool:
    if edge_tts is None:
        logger.warning("[tts] edge-tts not installed")
        return False

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await asyncio.wait_for(communicate.save(out_path), timeout=EDGE_TIMEOUT_SEC)

    try:
        asyncio.run(_run())
    except Exception as e:  # noqa: BLE001 - mạng/chặn/timeout đều rơi về piper
        logger.warning("[tts] edge-tts failed (%s): %s", type(e).__name__, e)
        _remove_quiet(out_path)
        return False
    if not os.path.isfile(out_path) or os.path.getsize(out_path) < MIN_OUTPUT_BYTES:
        logger.warning("[tts] edge-tts produced empty file")
        _remove_quiet(out_path)
        return False
    return True


def _vieneu_url() -> str:
    return (os.environ.get("VIENEU_TTS_URL", DEFAULT_VIENEU_URL) or "").strip().rstrip("/")


def _vieneu_voice(voice: str) -> Optional[str]:
    """Tên giọng edge tiếng Việt → giọng VieNeu; giọng edge ngôn ngữ khác → None; tên khác coi là giọng VieNeu."""
    voice = unicodedata.normalize("NFC", str(voice or "")).strip()
    if not voice:
        return VIENEU_FEMALE
    if voice.endswith("Neural"):
        if not voice.startswith("vi-"):
            return None
        return VIENEU_MALE if voice in _EDGE_VI_MALE else VIENEU_FEMALE
    return voice


def vieneu_voices() -> list[dict]:
    """Giọng server VieNeu đang có (``name``, ``gender``, ``region``, ``description``). Server tắt → ``[]``."""
    base = _vieneu_url()
    if not base:
        return []
    try:
        with urllib.request.urlopen(base + "/health", timeout=VIENEU_HEALTH_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.info("[tts] vieneu health: %s", getattr(e, "reason", e))
        return []
    return [v for v in data.get("voices") or [] if isinstance(v, dict) and v.get("name")]


def _synth_vieneu(text: str, out_path: str, voice: str, vieneu_voice: Optional[str] = None) -> bool:
    base = _vieneu_url()
    vn_voice = vieneu_voice or _vieneu_voice(voice)
    if not base or vn_voice is None:
        return False
    req = urllib.request.Request(
        base + "/tts",
        data=json.dumps({"text": text, "voice": vn_voice}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=VIENEU_TIMEOUT_SEC) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        logger.warning("[tts] vieneu HTTP %s: %s", e.code, e.read()[:200].decode(errors="replace"))
        return False
    except (urllib.error.URLError, OSError) as e:  # server tắt / timeout
        logger.warning("[tts] vieneu unreachable: %s", getattr(e, "reason", e))
        return False
    if len(data) < MIN_OUTPUT_BYTES:
        logger.warning("[tts] vieneu returned empty audio")
        return False
    wav_tmp = out_path + ".vieneu.tmp.wav"
    with open(wav_tmp, "wb") as f:
        f.write(data)
    return _wav_to_output(wav_tmp, out_path, "vieneu")


def _wav_to_output(wav_tmp: str, out_path: str, what: str) -> bool:
    """WAV tạm → ``out_path`` (đổi tên nếu đuôi .wav, không thì ffmpeg đổi định dạng). Luôn xoá file tạm."""
    if out_path.lower().endswith(".wav"):
        try:
            os.replace(wav_tmp, out_path)
            return True
        except OSError as e:
            logger.warning("[tts] %s cannot move wav: %s", what, e)
            _remove_quiet(wav_tmp)
            return False

    cmd = [_ffmpeg_bin(), "-y", "-i", wav_tmp, "-b:a", "128k", out_path]
    ok = _run_ffmpeg(cmd, out_path, f"{what} wav→audio")
    _remove_quiet(wav_tmp)
    return ok


def _synth_piper(
    text: str,
    out_path: str,
    rate: str,
    model_name: str = DEFAULT_PIPER_MODEL,
) -> bool:
    if PiperVoice is None:
        logger.warning("[tts] piper-tts not installed")
        return False
    model_path = _piper_models_dir() / f"{model_name}.onnx"
    if not model_path.is_file():
        logger.warning(
            "[tts] piper model missing: %s (run `python -m piper.download_voices %s` there)",
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
        logger.warning("[tts] piper failed (%s): %s", type(e).__name__, e)
        _remove_quiet(wav_tmp)
        return False

    return _wav_to_output(wav_tmp, out_path, "piper")


def _try_engine(name: str, fn, *args) -> bool:
    """Một engine raise cũng chỉ là 'thất bại' — không được chặn engine kế tiếp."""
    try:
        return bool(fn(*args))
    except Exception as e:  # noqa: BLE001
        logger.warning("[tts] %s raised (%s): %s", name, type(e).__name__, e)
        return False


def synthesize(
    text: str,
    out_path: str,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    engine: str = "auto",
    vieneu_voice: Optional[str] = None,
) -> bool:
    """
    Đọc ``text`` thành file audio tại ``out_path`` (mp3/m4a/wav theo đuôi).

    ``engine``: ``auto`` (vieneu → edge → piper), ``vieneu``, ``edge``, ``piper``. ``vieneu_voice``: giọng VieNeu
    cụ thể; bỏ trống thì quy từ ``voice`` (edge) theo giới. Không raise;
    trả False + warning khi mọi engine đều hỏng.
    """
    try:
        cleaned = _normalize_text(text)
        if not cleaned:
            logger.warning("[tts] synthesize: empty text")
            return False
        engine_key = (engine or "auto").strip().lower()
        if engine_key not in ("auto", "vieneu", "edge", "piper"):
            engine_key = "auto"

        if engine_key in ("auto", "vieneu"):
            if _try_engine("vieneu", _synth_vieneu, cleaned, out_path, voice, vieneu_voice):
                logger.info("[tts] voice via vieneu (%s)", vieneu_voice or _vieneu_voice(voice))
                return True
            if engine_key == "vieneu":
                return False

        if engine_key in ("auto", "edge"):
            if _try_engine("edge-tts", _synth_edge, cleaned, out_path, voice, rate):
                logger.info("[tts] voice via edge-tts (%s)", voice)
                return True
            if engine_key == "edge":
                return False

        if _try_engine("piper", _synth_piper, cleaned, out_path, rate):
            logger.info("[tts] voice via piper (%s)", DEFAULT_PIPER_MODEL)
            return True
        logger.warning("[tts] synthesize: all engines failed")
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("[tts] synthesize error: %s", e)
        return False


