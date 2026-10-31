"""
Lời thoại từ Whisper, đã lọc câu bịa — dùng chung cho Studio (phân tích, lồng tiếng) và về sau
bước giọng đọc AI (ADR-061).

Port nguyên văn từ ``viral_intake.subtitle_layer`` (ADR-016 bộ lọc R1/R2, ADR-060 tự nhận ngôn
ngữ). Bản cũ giữ nguyên cho tới khi xoá hệ cũ ở PLAN-106 P6; sửa bộ lọc thì sửa ở đây.

Không raise vì thiếu audio: trả ``([], None)``.
"""
from __future__ import annotations

import logging
import math
import os
import re
import subprocess
import tempfile
import unicodedata
from typing import Any, Optional

from app.core.media import ffmpeg_path
from app.core.orchestrator import ContentOrchestrator

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    """
    Loại bỏ dấu tiếng Việt sang ký tự base ASCII.
    Đảm bảo tính chất bất biến độ dài codepoint 1:1 với chuỗi NFC:
    len(strip_accents(text_nfc)) == len(text_nfc).
    """
    nfc = unicodedata.normalize("NFC", text or "")
    nfd = unicodedata.normalize("NFD", nfc)
    out: list[str] = []
    for ch in nfd:
        if unicodedata.category(ch) != "Mn":
            if ch == "đ":
                out.append("d")
            elif ch == "Đ":
                out.append("D")
            else:
                out.append(ch)
    return "".join(out)


_SEP = r"[\s\-_.,/–—]*"

_LEAD_CONNECTOR = r"(?:\b(?:va|hoac|cung|dong\s+thoi)\s+)?"
_LEAD_POLITE = r"(?:\b(?:xin(?:\s+vui\s+long)?|vui\s+long)\s+)?"
_LEAD_AUDIENCE = (
    r"(?:\b(?:cac\s+ban|moi\s+nguoi|ca\s+nha|quy\s+vi|khan\s+gia)\s+(?:hay|nho|dung\s+quen|vui\s+long|nhe|nha)\s+|"
    r"\b(?:cac\s+ban|moi\s+nguoi|ca\s+nha|quy\s+vi|khan\s+gia)\s+(?=(?:bam|nhan|sub|dang\s*k[yi]|chia\s*se)\b))?"
)
_LEAD_REQUEST = r"(?:\b(?:hay|nho|dung\s+quen|vui\s+long)\s+)?"
_LEAD_CTA = rf"(?:{_LEAD_CONNECTOR}{_LEAD_POLITE}{_LEAD_AUDIENCE}{_LEAD_REQUEST})"
_TRAIL_CTA = (
    r"(?:\s*(?:de\b\s+)?(?:ung\s*ho\b(?:\s+(?:kenh|minh|tui\s*minh|chung\s*minh)\b)?)?"
    r"(?:\s*(?:giup\b(?:\s+(?:minh|tui\s*minh)\b)?)?)?"
    r"(?:\s*(?:nhe|nha|a)\b)?"
    r"(?:\s*(?:cac\s+ban|moi\s+nguoi|ca\s+nha)\b)?"
    r"(?:\s*oi\b)?)?"
)

_P_GHIEN_MI_GO = (
    rf"(?:(?:\b(?:kenh|phim|nhom|tai){_SEP}+)?#?\bghien{_SEP}m[iy]{_SEP}go\b|#?ghienm[iy]go\b)"
)
_P_LALA_SCHOOL = (
    rf"(?:(?:\b(?:hoc{_SEP}vien|phim){_SEP}+)?#?(?:la{_SEP}la{_SEP}(?:school|skool|scool)|"
    r"lalaschool|lalaskool|lalascool)\b)"
)
_P_LIKE_SHARE = (
    rf"(?:(?:\b(?:bam|nhan){_SEP}(?:nut{_SEP})?)?\blike{_SEP}(?:and|&+|\+|va|/)?{_SEP}share\b)"
)
_P_LIKE_ALONE = rf"(?:(?:\b(?:bam|nhan){_SEP}(?:nut{_SEP})?)?\blike\b)"
_P_SUB_KENH = (
    rf"(?:\b(?:bam|nhan){_SEP}(?:nut{_SEP})?"
    rf"(?:sub(?:scribe|cribe)?(?:{_SEP}(?:kenh|channel))?|"
    rf"dang{_SEP}k[yi]{_SEP}(?:kenh|channel))\b)"
)
_P_DANG_KY_KENH = rf"(?:\bdang{_SEP}k[yi]{_SEP}(?:kenh|channel|sub)\b)"
_P_SUBSCRIBE_ALONE = rf"(?:\bsub(?:scribe|cribe)?{_SEP}(?:kenh|channel)\b|\bsub(?:scribe|cribe)\b)"

_CTA_ACTIONS = rf"(?:{_P_LIKE_SHARE}|{_P_SUB_KENH}|{_P_DANG_KY_KENH}|{_P_SUBSCRIBE_ALONE})"
_CTA_CHAIN = rf"(?:{_CTA_ACTIONS}(?:{_SEP}(?:,|&+|\+|va|dong\s*thoi){_SEP}(?:{_CTA_ACTIONS}|{_P_LIKE_ALONE}))*|{_P_LIKE_ALONE}{_SEP}(?:,|&+|\+|va|dong\s*thoi){_SEP}{_CTA_ACTIONS})"
_FULL_CTA_PATTERN = rf"(?:{_LEAD_CTA}{_CTA_CHAIN}{_TRAIL_CTA}[\s\.\!\?]*)"

_HALLUCINATION_PATTERNS = [
    _P_GHIEN_MI_GO,
    _P_LALA_SCHOOL,
    _FULL_CTA_PATTERN,
]

_HALLUCINATION_RE = re.compile("|".join(rf"(?:{p})" for p in _HALLUCINATION_PATTERNS), re.IGNORECASE)
_DANGLING_STOPWORDS = {"va", "hoac", "de", "nhe", "nha", "a", "oi", "thi", "ma", "la", "cua", "cho", "voi", "xin"}

_AUDIO_TAG_RE = re.compile(
    r"[\[\(]\s*(?:nh[ạa]c|âm\s*nh[ạa]c|ti[ếe]ng\s*(?:đ[ộo]ng|c(?:[ườu]ời|ười|ươi|uoi)|v[ỗo]\s*tay|nh[ạa]c)|nh[ạa]c\s*n[ềe]n|music)\s*[\]\)]",
    re.IGNORECASE,
)


def clean_hallucinations_from_text(text: str) -> str:
    """
    Gọt bỏ cụm từ ảo giác khỏi một chuỗi văn bản phụ đề:
    - Nếu chuỗi chỉ toàn ảo giác -> trả về chuỗi rỗng "".
    - Nếu chuỗi hỗn hợp -> cắt bỏ ảo giác, giữ nguyên dấu và chữ của lời thoại thật.
    - Dọn dẹp khoảng trắng, dấu câu thừa, và viết hoa lại chữ cái đầu câu khi bị cắt đầu.
    """
    text = unicodedata.normalize("NFC", str(text or "")).strip()
    if not text or not re.search(r"\w", text):
        return ""

    new_text, tag_count = _AUDIO_TAG_RE.subn("", text)
    had_matches = tag_count > 0
    text = new_text

    while True:
        stripped = strip_accents(text)
        m = _HALLUCINATION_RE.search(stripped)
        if not m:
            break
        had_matches = True
        start, end = m.span()
        text = text[:start] + " " + text[end:]
        text = re.sub(r"[\s\u00a0]+", " ", text).strip()

    if had_matches:
        # Dọn dẹp cặp ngoặc rỗng sót lại sau khi gọt bỏ ảo giác bên trong
        text = re.sub(r"[\(\[\{][\s\.,;:–—\-_\!\?]*[\)\]\}]", " ", text)
        text = re.sub(r"[\s\u00a0]+", " ", text)
        text = re.sub(r"\s*([.!?])(?:\s*[.!?])+", r"\1", text)
        text = re.sub(r"\s*([,;:])\s*([.!?])", r"\2", text)
        text = re.sub(r"([,;:–—\-])(?:\s*[,;:–—\-])+", r"\1", text)
        text = re.sub(r"^[\s,;:–—\-\.\!\?\(\)\[\]]+", "", text)
        text = re.sub(r"[\s,;:–—\-\(\)\[\]]+$", "", text)

        # Nếu có gọt bỏ ảo giác, dọn dẹp các từ nối mồ côi ở cuối chuỗi do bị cắt
        while True:
            prev = text
            text = re.sub(
                r"[\s,;:–—\-]+(?:và|hoặc|để|đồng\s+thời)[\s,;:–—\-\.\!\?]*$",
                "",
                text,
                flags=re.IGNORECASE,
            )
            text = text.strip()
            if text == prev:
                break

        words = re.findall(r"\w+", text)
        if not words:
            return ""

        words_stripped = [strip_accents(w).lower() for w in words]
        if all(w in _DANGLING_STOPWORDS for w in words_stripped):
            return ""

        text = text.strip()
        if text:
            text = text[0].upper() + text[1:]

    # Bảo vệ vô điều kiện: Không bao giờ trả về chuỗi không chứa ký tự chữ/số nào
    if not re.search(r"\w", text):
        return ""

    return text




def filter_hallucination_segments(segments: list[dict]) -> list[dict]:
    """
    Lọc danh sách segment phụ đề:
    - Loại bỏ hoàn toàn segment chỉ chứa cụm từ ảo giác hoặc rỗng.
    - Gọt tỉa cụm từ rác trong segment hỗn hợp, giữ nguyên start/end timestamp.
    """
    cleaned: list[dict] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        clean_text = clean_hallucinations_from_text(text)
        if not clean_text:
            continue
        item = dict(seg)
        item["text"] = clean_text
        cleaned.append(item)
    return cleaned




# ─── 1. Transcribe ───


def _extract_audio(video_path: str, audio_path: str) -> bool:
    """Bóc audio 16 kHz mono WAV (đúng đầu vào Whisper). False nếu không có audio."""
    cmd = [
        ffmpeg_path.ffmpeg_bin(), "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", audio_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        logger.warning("[speech] ffmpeg audio extract failed: %s", e)
        return False
    if result.returncode != 0:
        return False
    return os.path.isfile(audio_path) and os.path.getsize(audio_path) > 1024


def keep_speech_segments(segments: list[dict]) -> list[dict]:
    """Bỏ đoạn rõ là nhạc hoặc ảo giác rác Whisper. Thiếu điểm thì giữ đoạn."""
    filtered = filter_hallucination_segments(segments)
    kept: list[dict] = []
    for seg in filtered:
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        try:
            start = float(seg.get("start"))
            end = float(seg.get("end"))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(start) and math.isfinite(end)) or start < 0 or end <= start:
            continue
        no_speech = seg.get("no_speech_prob")
        if no_speech is not None:
            try:
                if float(no_speech) >= 0.6:
                    continue
            except (TypeError, ValueError):
                pass
        ratio = seg.get("compression_ratio")
        if ratio is not None:
            try:
                if float(ratio) > 2.4:
                    continue
            except (TypeError, ValueError):
                pass
        kept.append(seg)
    return kept


def transcribe(
    media_path: str, model: Any = None, *, language: Optional[str] = None,
) -> tuple[list[dict], Optional[str]]:
    """
    Whisper → ``([{"start", "end", "text", …}], mã ngôn ngữ)``, đã bỏ đoạn nhạc / câu bịa.

    ``language=None`` → Whisper tự nhận ngôn ngữ. Không có audio → ``([], None)``.
    ``model=None`` → model đã cache của ``ContentOrchestrator`` (khỏi nạp lần hai).
    """
    fd, audio_path = tempfile.mkstemp(prefix="sub_", suffix=".wav")
    os.close(fd)
    try:
        if not _extract_audio(media_path, audio_path):
            logger.info("[speech] no audio track: %s", os.path.basename(media_path))
            return [], None
        if model is None:
            model = ContentOrchestrator._get_whisper_model()
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
        )
        detected = getattr(info, "language", None) or language
        out: list[dict] = []
        for seg in segments:
            text = _WS_RE.sub(" ", unicodedata.normalize("NFC", seg.text or "")).strip()
            if not text:
                continue
            start = float(seg.start)
            end = float(seg.end)
            if end <= start:
                continue
            item = {"start": start, "end": end, "text": text}
            no_speech = getattr(seg, "no_speech_prob", None)
            if no_speech is not None:
                item["no_speech_prob"] = float(no_speech)
            ratio = getattr(seg, "compression_ratio", None)
            if ratio is not None:
                item["compression_ratio"] = float(ratio)
            out.append(item)
        return keep_speech_segments(out), detected
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


