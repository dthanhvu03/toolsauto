"""
Phụ đề cho render: dời lời thoại theo đoạn cắt rồi dựng ASS.

Kiểu chữ giữ đúng như phụ đề reup cũ (``viral_intake/subtitle_layer.build_ass``: Be Vietnam Pro
Bold, viền 3, bóng 1, giữa đáy) để kênh chuyển sang Studio không đổi giao diện. Không import bản
cũ vì Studio không phụ thuộc feature khác (ADR-061); bản cũ bị xoá ở PLAN-106 P6.
"""
from __future__ import annotations

import math
import re
import unicodedata

import pysubs2

FONT_NAME = "Be Vietnam Pro"
_WS_RE = re.compile(r"\s+")


def shift_lines(
    clips: list[tuple[int, float, float]],
    transcripts: dict[int, list[dict]],
) -> list[dict]:
    """
    ``clips``: ``(asset_id, start, end)`` theo thứ tự trên video ra. Câu nào nằm (một phần) trong
    đoạn được giữ thì dời sang giây của video ra và cắt gọn trong đoạn đó.
    """
    out: list[dict] = []
    offset = 0.0
    for asset_id, start, end in clips:
        for line in transcripts.get(asset_id) or []:
            s, e = float(line["start"]), float(line["end"])
            if e <= start or s >= end:
                continue
            ns, ne = offset + max(s, start) - start, offset + min(e, end) - start
            if ne - ns >= 0.2:
                out.append({"start": round(ns, 3), "end": round(ne, 3), "text": line["text"]})
        offset += end - start
    return out


def apply_edits(lines: list[dict], edits: dict[int, str]) -> list[dict]:
    out = []
    for i, line in enumerate(lines):
        if i in edits:
            text = edits[i].strip()
            if not text:
                continue
            line = {**line, "text": text}
        out.append(line)
    return out


def _wrap(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return lines


def build_ass(lines: list[dict], *, width: int, height: int, font_size: int, margin_v: int, max_chars: int) -> str:
    """Tối đa 2 dòng mỗi lần hiện; câu dài hơn chia thành nhiều lần, chia đều thời gian."""
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"] = str(width)
    subs.info["PlayResY"] = str(height)
    subs.info["WrapStyle"] = "2"
    subs.info["ScaledBorderAndShadow"] = "yes"
    subs.styles["Default"] = pysubs2.SSAStyle(
        fontname=FONT_NAME,
        fontsize=float(font_size),
        primarycolor=pysubs2.Color(255, 255, 255),
        secondarycolor=pysubs2.Color(255, 255, 255),
        outlinecolor=pysubs2.Color(0, 0, 0),
        backcolor=pysubs2.Color(0, 0, 0, 128),
        bold=True,
        borderstyle=1,
        outline=3.0,
        shadow=1.0,
        alignment=pysubs2.Alignment.BOTTOM_CENTER,
        marginl=60,
        marginr=60,
        marginv=margin_v,
    )
    for line in lines:
        text = _WS_RE.sub(" ", unicodedata.normalize("NFC", str(line.get("text") or ""))).strip()
        start, end = float(line["start"]), float(line["end"])
        if not text or not (math.isfinite(start) and math.isfinite(end)) or start < 0 or end <= start:
            continue
        rows = _wrap(text, max_chars)
        chunks = [rows[i:i + 2] for i in range(0, len(rows), 2)]
        slot = (end - start) / len(chunks)
        for i, chunk in enumerate(chunks):
            s = start + i * slot
            e = end if i == len(chunks) - 1 else s + slot
            subs.append(pysubs2.SSAEvent(start=pysubs2.make_time(s=s), end=pysubs2.make_time(s=e), text="\\N".join(chunk)))
    return subs.to_string("ass")
