"""
dub_layer — thuyết minh lại video reup sang ngôn ngữ khác (ADR-060).

Đường đi (mỗi bước hỏng thì cả lớp trả ``ok=False``, ReupProcessor giữ video bước trước):

    1. ffmpeg bóc audio 44,1 kHz stereo.
    2. Demucs tách giọng / nhạc nền — chạy ở tiến trình riêng
       (``demucs_separate``) để torch không ở lại RAM worker. Demucs hỏng hoặc
       chưa cài → dùng audio gốc hạ nhỏ làm nền (giọng gốc vẫn nghe lí nhí).
    3. Whisper tự nhận ngôn ngữ trên phần giọng đã tách
       (``subtitle_layer.transcribe_segments(language=None)``). Trùng ngôn ngữ
       đích → bỏ qua, không thuyết minh.
    4. AI dịch theo lô, mỗi câu có trần ký tự tính từ khe thời gian của nó để
       đọc lên vừa khít.
    5. TTS từng câu, gọt khoảng lặng edge-tts tự chèn đầu/cuối; câu dài hơn khe
       (đã chừa ``GAP_SEC`` nghỉ) thì tăng tốc nhẹ (``atempo`` ≤ ``MAX_SPEEDUP``),
       vẫn dài thì câu sau lùi lại — không cắt chữ, chỉ cắt khi chạm hết video.
    6. Trộn các câu lên nền bằng numpy, mux lại với video (``-c:v copy``).

Hàm thuần, không biết DB. AI và TTS được TIÊM vào (``translate``, ``synthesize``)
— cùng kiểu ``split.py`` nhận ``ask_ai`` — nên lớp không import AI hay
``audio_layer``. Phụ thuộc một chiều duy nhất: dùng lại đường Whisper + bộ lọc
câu bịa của ``subtitle_layer``.

``apply()`` không bao giờ raise.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from app import config as app_config
from app.core.media import ffmpeg_path
from app.features.viral_intake import subtitle_layer

logger = logging.getLogger(__name__)

SAMPLE_RATE = 44100
MAX_SPEEDUP = 1.2  # trên mức này nghe rõ là đọc vội (Owner nghe thử 27/10)
GAP_SEC = 0.25  # nghỉ giữa hai câu, để câu không dính vào nhau
# edge-tts chèn ~0,2 s lặng đầu và ~0,9 s lặng cuối mỗi file — gọt trước khi tính tốc độ.
TRIM_SILENCE = (
    "silenceremove=start_periods=1:start_threshold=-45dB,"
    "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse"
)
FALLBACK_BACKGROUND_VOLUME = 0.15  # Demucs hỏng: audio gốc làm nền, giọng gốc bị đè nhỏ
TRANSLATE_BATCH = 30
MIN_TTS_OK_RATIO = 0.5
FADE_SEC = 0.06
MIN_OUTPUT_BYTES = 1024

# mã Whisper → (tên ngôn ngữ cho prompt, giọng nữ, giọng nam, ký tự đọc được mỗi giây)
LANGUAGES: dict[str, tuple[str, str, str, float]] = {
    "vi": ("Vietnamese", "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", 14.0),
    "en": ("English", "en-US-AriaNeural", "en-US-GuyNeural", 15.0),
    "ja": ("Japanese", "ja-JP-NanamiNeural", "ja-JP-KeitaNeural", 7.0),
    "ko": ("Korean", "ko-KR-SunHiNeural", "ko-KR-InJoonNeural", 7.0),
    "zh": ("Simplified Chinese", "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", 5.0),
    "es": ("Spanish", "es-ES-ElviraNeural", "es-ES-AlvaroNeural", 15.0),
    "th": ("Thai", "th-TH-PremwadeeNeural", "th-TH-NiwatNeural", 12.0),
    "id": ("Indonesian", "id-ID-GadisNeural", "id-ID-ArdiNeural", 15.0),
    "fr": ("French", "fr-FR-DeniseNeural", "fr-FR-HenriNeural", 15.0),
    "de": ("German", "de-DE-KatjaNeural", "de-DE-ConradNeural", 14.0),
    "pt": ("Portuguese", "pt-BR-FranciscaNeural", "pt-BR-AntonioNeural", 15.0),
    "ru": ("Russian", "ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural", 13.0),
    "hi": ("Hindi", "hi-IN-SwaraNeural", "hi-IN-MadhurNeural", 12.0),
}

TranslateFn = Callable[[str], Optional[str]]
SynthesizeFn = Callable[[str, str, str], bool]  # (text, out_path, voice) -> ok


@dataclass
class DubResult:
    ok: bool
    reason: str = ""
    source_lang: Optional[str] = None
    # Câu đã dịch theo thời gian của video ra — lớp phụ đề đốt thẳng, khỏi Whisper lần hai.
    segments: list[dict] = field(default_factory=list)


def voice_for(lang: str, gender: str = "female") -> str:
    _name, female, male, _cps = LANGUAGES.get(lang, LANGUAGES["vi"])
    return male if (gender or "").strip().lower() == "male" else female


# ─── ffmpeg ───


def _probe_duration(path: str) -> float:
    try:
        result = subprocess.run(
            [
                ffmpeg_path.ffprobe_bin(), "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        return max(0.0, float((result.stdout or "0").strip() or 0))
    except Exception:
        return 0.0


def _extract_audio(video_path: str, wav_path: str) -> bool:
    cmd = [
        ffmpeg_path.ffmpeg_bin(), "-y", "-i", video_path,
        "-vn", "-ac", "2", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", wav_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        logger.warning("[dub_layer] audio extract failed: %s", e)
        return False
    return result.returncode == 0 and os.path.isfile(wav_path) and os.path.getsize(wav_path) > MIN_OUTPUT_BYTES


def _decode(path: str, audio_filter: Optional[str] = None) -> Optional[np.ndarray]:
    """Mọi file audio → float32 (2, n) ở 44,1 kHz. ``audio_filter`` vd ``atempo=1.2``."""
    cmd = [ffmpeg_path.ffmpeg_bin(), "-v", "error", "-i", path]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += ["-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        logger.warning("[dub_layer] decode failed: %s", e)
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    data = np.frombuffer(result.stdout, dtype=np.float32)
    return data[: len(data) // 2 * 2].reshape(-1, 2).T.copy()


def _write_wav(path: str, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).T.copy()
    with wave.open(path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def _mux(video_path: str, audio_wav: str, output_path: str, duration: float) -> bool:
    cmd = [
        ffmpeg_path.ffmpeg_bin(), "-y", "-i", video_path, "-i", audio_wav,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
    ]
    if duration > 0:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-movflags", "+faststart", output_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as e:  # noqa: BLE001
        logger.warning("[dub_layer] mux failed: %s", e)
        return False
    if result.returncode != 0:
        logger.warning("[dub_layer] mux failed: %s", (result.stderr or "")[-240:])
        return False
    return os.path.isfile(output_path) and os.path.getsize(output_path) >= MIN_OUTPUT_BYTES


# ─── 1. Tách giọng ───


def separate(audio_wav: str, vocals_wav: str, background_wav: str, *, duration: float = 0.0) -> bool:
    """Demucs qua tiến trình riêng. False khi chưa cài / lỗi / quá giờ."""
    timeout = int(180 + 4 * (duration or 90.0))
    cmd = [
        sys.executable, "-m", "app.features.viral_intake.demucs_separate",
        audio_wav, vocals_wav, background_wav,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(app_config.BASE_DIR),
        )
    except subprocess.TimeoutExpired:
        logger.warning("[dub_layer] demucs timeout (>%ss)", timeout)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("[dub_layer] demucs failed to start: %s", e)
        return False
    if result.returncode != 0:
        logger.warning("[dub_layer] demucs exit %s: %s", result.returncode, (result.stderr or "")[-240:])
        return False
    return all(os.path.isfile(p) and os.path.getsize(p) > MIN_OUTPUT_BYTES for p in (vocals_wav, background_wav))


# ─── 2. Dịch ───


def slot_ends(segments: list[dict], duration: float) -> list[float]:
    """Mỗi câu được nói tới đầu câu sau (hoặc hết video) — rộng hơn ``end`` của Whisper."""
    ends: list[float] = []
    for i, seg in enumerate(segments):
        nxt = float(segments[i + 1]["start"]) if i + 1 < len(segments) else (duration or float(seg["end"]))
        ends.append(max(float(seg["end"]), min(nxt, duration or nxt)))
    return ends


def build_translate_prompt(lines: list[dict], source_lang: str, target_lang: str) -> str:
    src = LANGUAGES.get(source_lang, (source_lang or "the original language",))[0]
    dst = LANGUAGES[target_lang][0]
    return (
        f"Translate each line of this short video's dialogue from {src} to {dst}.\n"
        "Write natural spoken language for a voice-over, keep names, keep the meaning.\n"
        "Each translation is read aloud inside a fixed time slot, so it MUST stay within "
        "its max_chars characters — shorten freely to fit.\n"
        f"Return ONLY a JSON array of exactly {len(lines)} strings in the same order. No notes, no markdown.\n"
        "Lines:\n"
        + json.dumps(lines, ensure_ascii=False)
    )


def parse_translation(text: Optional[str], expected: int) -> Optional[list[str]]:
    """Lấy mảng JSON đầu tiên trong câu trả lời; sai số phần tử → None."""
    if not text:
        return None
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, list) or len(data) != expected:
        return None
    out = [re.sub(r"\s+", " ", str(x or "")).strip() for x in data]
    return out if any(out) else None


def translate_segments(
    segments: list[dict], ends: list[float], source_lang: str, target_lang: str, translate: TranslateFn,
) -> Optional[list[str]]:
    """Dịch theo lô ``TRANSLATE_BATCH`` câu. Lô nào hỏng (AI lỗi / sai số câu) → None cả lớp."""
    cps = LANGUAGES[target_lang][3]
    out: list[str] = []
    for i in range(0, len(segments), TRANSLATE_BATCH):
        batch = [
            {
                "i": j,
                "text": segments[j]["text"],
                "max_chars": max(4, int((ends[j] - float(segments[j]["start"]) - GAP_SEC) * cps)),
            }
            for j in range(i, min(i + TRANSLATE_BATCH, len(segments)))
        ]
        try:
            reply = translate(build_translate_prompt(batch, source_lang, target_lang))
        except Exception as e:  # noqa: BLE001
            logger.warning("[dub_layer] translate raised: %s", e)
            return None
        lines = parse_translation(reply, len(batch))
        if lines is None:
            logger.warning("[dub_layer] translate batch %d: bad reply", i // TRANSLATE_BATCH)
            return None
        out.extend(lines)
    return out


# ─── 3. Đọc + ghép ───


def fit_clip(clip: np.ndarray, slot_sec: float) -> np.ndarray:
    """Cắt ``clip`` cho vừa khe, fade cuối để khỏi tiếng bụp. Ngắn hơn khe thì giữ nguyên."""
    limit = int(max(0.0, slot_sec) * SAMPLE_RATE)
    if clip.shape[1] <= limit:
        return clip
    clip = clip[:, :limit].copy()
    fade = min(limit, int(FADE_SEC * SAMPLE_RATE))
    if fade > 0:
        clip[:, -fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return clip


def tempo_for(clip_sec: float, slot_sec: float) -> float:
    if clip_sec <= 0 or clip_sec <= slot_sec:
        return 1.0
    if slot_sec <= 0:
        return MAX_SPEEDUP
    return min(clip_sec / slot_sec, MAX_SPEEDUP)


def plan_line(seg_start: float, cursor: float, slot_end: float, clip_sec: float) -> tuple[float, float]:
    """
    ``(bắt đầu, tempo)`` cho một câu.

    Bắt đầu ở đầu câu gốc, hoặc muộn hơn nếu câu trước còn đang nói (``cursor``).
    Tempo tính trên khe còn lại sau khi chừa ``GAP_SEC`` nghỉ trước câu sau.
    """
    begin = max(seg_start, cursor)
    return begin, tempo_for(clip_sec, slot_end - GAP_SEC - begin)


def place(track: np.ndarray, clip: np.ndarray, start_sec: float) -> None:
    """Cộng ``clip`` vào ``track`` tại ``start_sec`` (tràn cuối thì cắt)."""
    at = int(max(0.0, start_sec) * SAMPLE_RATE)
    if at >= track.shape[1]:
        return
    n = min(clip.shape[1], track.shape[1] - at)
    track[:, at:at + n] += clip[:, :n]


# ─── 4. Apply ───


def apply(
    input_path: str,
    output_path: str,
    *,
    target_lang: str = "vi",
    translate: TranslateFn,
    synthesize: SynthesizeFn,
    voice_gender: str = "female",
    background_volume: float = 1.0,
    model: Any = None,
) -> DubResult:
    """
    Thuyết minh ``input_path`` sang ``target_lang``, ghi ``output_path``.

    Trả ``DubResult``; ``ok=False`` thì KHÔNG để lại ``output_path``.
    """
    if target_lang not in LANGUAGES:
        return DubResult(False, f"unsupported target {target_lang}")
    work = tempfile.mkdtemp(prefix="dub_", dir=os.path.dirname(os.path.abspath(output_path)) or None)
    result = DubResult(False)
    try:
        duration = _probe_duration(input_path)
        audio = os.path.join(work, "audio.wav")
        if not _extract_audio(input_path, audio):
            result.reason = "no audio"
            return result

        vocals = os.path.join(work, "vocals.wav")
        background = os.path.join(work, "background.wav")
        if separate(audio, vocals, background, duration=duration):
            speech_src, bg_src, bg_gain = vocals, background, float(background_volume)
        else:
            logger.warning("[dub_layer] no separation, dub over ducked original")
            speech_src, bg_src, bg_gain = audio, audio, FALLBACK_BACKGROUND_VOLUME

        segments, source_lang = subtitle_layer.transcribe_segments(speech_src, model=model, language=None)
        result.source_lang = source_lang
        if not segments:
            result.reason = "no speech"
            return result
        if source_lang == target_lang:
            result.reason = "same language"
            return result

        ends = slot_ends(segments, duration)
        lines = translate_segments(segments, ends, source_lang or "", target_lang, translate)
        if lines is None:
            result.reason = "translate failed"
            return result

        bg = _decode(bg_src)
        if bg is None:
            result.reason = "background decode failed"
            return result
        track = bg * max(0.0, bg_gain)
        voice = voice_for(target_lang, voice_gender)
        video_end = duration or ends[-1]
        spoken: list[dict] = []
        cursor = 0.0
        for i, (seg, text) in enumerate(zip(segments, lines)):
            if not text:
                continue
            mp3 = os.path.join(work, f"line_{i:03d}.mp3")
            if not synthesize(text, mp3, voice):
                continue
            clip = _decode(mp3, TRIM_SILENCE)
            if clip is None or clip.shape[1] == 0:
                continue
            begin, tempo = plan_line(float(seg["start"]), cursor, ends[i], clip.shape[1] / SAMPLE_RATE)
            if tempo > 1.0:
                clip = _decode(mp3, f"{TRIM_SILENCE},atempo={tempo:.3f}")
                if clip is None:
                    continue
            clip = fit_clip(clip, video_end - begin)  # chỉ cắt khi chạm hết video
            if clip.shape[1] == 0:
                continue
            place(track, clip, begin)
            end = begin + clip.shape[1] / SAMPLE_RATE
            spoken.append({"start": begin, "end": end, "text": text})
            cursor = end + GAP_SEC

        if len(spoken) < max(1, int(len(segments) * MIN_TTS_OK_RATIO)):
            result.reason = f"tts failed ({len(spoken)}/{len(segments)})"
            return result

        peak = float(np.abs(track).max() or 0.0)
        if peak > 0.99:
            track *= 0.99 / peak
        mixed = os.path.join(work, "mixed.wav")
        _write_wav(mixed, track)
        if not _mux(input_path, mixed, output_path, duration):
            result.reason = "mux failed"
            return result

        result.ok = True
        result.segments = spoken
        result.reason = f"{source_lang}→{target_lang}, {len(spoken)}/{len(segments)} lines"
        logger.info("[dub_layer] dubbed %s → %s", result.reason, os.path.basename(output_path))
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("[dub_layer] apply failed, keep previous video: %s", e)
        result.ok = False
        result.reason = f"error: {e}"
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if not result.ok:
            try:
                if os.path.isfile(output_path):
                    os.remove(output_path)
            except OSError:
                pass
