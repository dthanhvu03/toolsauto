"""
Lồng tiếng: video nói tiếng khác → 2 file tiếng theo đúng mốc giây của video gốc:

- ``voice.wav``: giọng đọc bản dịch (chỉ có giọng, chỗ khác im lặng);
- ``background.wav``: nhạc / tiếng nền đã tách giọng gốc (Demucs). Demucs hỏng → tiếng gốc,
  và ``background_volume`` gợi ý hạ còn 0,15 để giọng gốc chỉ nghe lí nhí.

Port từ ``viral_intake.dub_layer`` (ADR-060), khác một chỗ: **không trộn, không mux** — render
của Studio trộn hai file này cùng hình trong một lượt encode, và trình edit chỉnh được âm lượng
từng file. Bản cũ giữ nguyên tới PLAN-106 P6.

AI và TTS được tiêm vào (``translate``, ``synthesize``) nên module không gọi mạng; ``make_tracks``
không bao giờ raise.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from app import config as app_config
from app.core.media import ffmpeg_path, speech

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
class DubTracks:
    ok: bool
    reason: str = ""
    source_lang: Optional[str] = None
    # câu đã dịch theo giây của video gốc — phụ đề dùng thẳng, khỏi Whisper lần hai
    lines: list[dict] = field(default_factory=list)
    voice_wav: Optional[str] = None
    background_wav: Optional[str] = None
    background_volume: float = 1.0


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
        logger.warning("[studio.dub] audio extract failed: %s", e)
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
        logger.warning("[studio.dub] decode failed: %s", e)
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


# ─── 1. Tách giọng ───


def separate(audio_wav: str, vocals_wav: str, background_wav: str, *, duration: float = 0.0) -> bool:
    """Demucs qua tiến trình riêng. False khi chưa cài / lỗi / quá giờ."""
    timeout = int(180 + 4 * (duration or 90.0))
    cmd = [
        sys.executable, "-m", "app.features.studio.dub.separate",
        audio_wav, vocals_wav, background_wav,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(app_config.BASE_DIR),
        )
    except subprocess.TimeoutExpired:
        logger.warning("[studio.dub] demucs timeout (>%ss)", timeout)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("[studio.dub] demucs failed to start: %s", e)
        return False
    if result.returncode != 0:
        logger.warning("[studio.dub] demucs exit %s: %s", result.returncode, (result.stderr or "")[-240:])
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
            logger.warning("[studio.dub] translate raised: %s", e)
            return None
        lines = parse_translation(reply, len(batch))
        if lines is None:
            logger.warning("[studio.dub] translate batch %d: bad reply", i // TRANSLATE_BATCH)
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




# ─── 4. Hai file tiếng ───


def make_tracks(
    input_path: str,
    workdir: str,
    *,
    target_lang: str = "vi",
    translate: TranslateFn,
    synthesize: SynthesizeFn,
    voice_gender: str = "female",
    model: Any = None,
    hint_segments: list[dict] | None = None,
    hint_lang: str | None = None,
) -> DubTracks:
    """
    Ghi ``voice.wav`` + ``background.wav`` vào ``workdir`` (dài đúng bằng video gốc).

    ``ok=False`` khi không cần / không làm được (không tiếng, không lời, trùng ngôn ngữ, dịch
    hay đọc hỏng) — ``reason`` nói vì sao; người gọi giữ tiếng gốc.

    ``hint_segments`` / ``hint_lang``: lời thoại bước ``analyze`` đã nghe (PLAN-118). Demucs hỏng → dùng luôn, khỏi
    chạy Whisper lần hai trên tiếng gốc (máy vừa cạn RAM thì lần nghe đó cũng hỏng, ra «không có lời thoại» sai).
    Demucs được → vẫn nghe lại trên giọng đã tách (mốc giờ sạch hơn); ra rỗng thì cũng lùi về gợi ý.
    """
    if target_lang not in LANGUAGES:
        return DubTracks(False, f"không hỗ trợ ngôn ngữ đích {target_lang}")
    result = DubTracks(False)
    try:
        duration = _probe_duration(input_path)
        audio = os.path.join(workdir, "audio.wav")
        if not _extract_audio(input_path, audio):
            result.reason = "không có tiếng"
            return result

        vocals = os.path.join(workdir, "vocals.wav")
        background = os.path.join(workdir, "background.wav")
        hint = [s for s in (hint_segments or []) if str(s.get("text") or "").strip()]
        if separate(audio, vocals, background, duration=duration):
            result.background_volume = 1.0
            segments, source_lang = speech.transcribe(vocals, model=model, language=None)
            if not segments and hint:
                logger.warning("[studio.dub] nghe lại giọng đã tách ra rỗng — dùng lời thoại của bước phân tích")
                segments, source_lang = hint, hint_lang
        else:
            logger.warning("[studio.dub] không tách được giọng, nền là tiếng gốc hạ nhỏ")
            os.replace(audio, background)
            result.background_volume = FALLBACK_BACKGROUND_VOLUME
            if hint:
                segments, source_lang = hint, hint_lang
            else:
                segments, source_lang = speech.transcribe(background, model=model, language=None)
        result.source_lang = source_lang
        if not segments:
            result.reason = "không có lời thoại"
            return result
        if source_lang == target_lang:
            result.reason = "đã đúng ngôn ngữ đích"
            return result

        ends = slot_ends(segments, duration)
        lines = translate_segments(segments, ends, source_lang or "", target_lang, translate)
        if lines is None:
            result.reason = "dịch hỏng"
            return result

        total = int(round((duration or ends[-1]) * SAMPLE_RATE))
        track = np.zeros((2, max(1, total)), dtype=np.float32)
        voice = voice_for(target_lang, voice_gender)
        video_end = duration or ends[-1]
        spoken: list[dict] = []
        cursor = 0.0
        for i, (seg, text) in enumerate(zip(segments, lines)):
            if not text:
                continue
            mp3 = os.path.join(workdir, f"line_{i:03d}.mp3")
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
            spoken.append({"start": round(begin, 3), "end": round(end, 3), "text": text})
            cursor = end + GAP_SEC

        if len(spoken) < max(1, int(len(segments) * MIN_TTS_OK_RATIO)):
            result.reason = f"đọc hỏng ({len(spoken)}/{len(segments)} câu)"
            return result

        peak = float(np.abs(track).max() or 0.0)
        if peak > 0.99:
            track *= 0.99 / peak
        voice_wav = os.path.join(workdir, "voice.wav")
        _write_wav(voice_wav, track)
        result.ok = True
        result.lines = spoken
        result.voice_wav = voice_wav
        result.background_wav = background
        result.reason = f"{source_lang}→{target_lang}, {len(spoken)}/{len(segments)} câu"
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("[studio.dub] hỏng, giữ tiếng gốc: %s", e)
        result.ok = False
        result.reason = f"lỗi: {e}"
        return result
