"""
Phụ đề cho render: dời lời thoại theo đoạn cắt rồi dựng ASS.

Kiểu chữ giữ đúng như phụ đề reup cũ (``viral_intake/subtitle_layer.build_ass``: Be Vietnam Pro
Bold, viền 3, bóng 1, giữa đáy) để kênh chuyển sang Studio không đổi giao diện. Không import bản
cũ vì Studio không phụ thuộc feature khác (ADR-061); bản cũ bị xoá ở PLAN-106 P6.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata

import pysubs2
from PIL import ImageFont

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


# ── ngắt dòng (PLAN-120): theo cụm từ / dấu câu, dòng cân, không chữ lẻ, đo bằng font thật ──
_END = (".", "!", "?", "…", "。", "！", "？")
_SOFT = (",", ";", ":", "，", "；", "：")
# ngắt TRƯỚC các từ này là tự nhiên (đầu một cụm mới)
_LEAD = frozenset(
    "và nhưng thì là của ở từ với cho khi vì nên mà để rồi hay hoặc tuy dù nếu như trong trên dưới sau trước "
    "đến tới tại bởi do còn cũng lại đã sẽ đang các những một".split()
)
# dòng không nên kết thúc bằng các từ này (treo giữa cụm)
_TAIL = frozenset("và của ở từ với cho các những một là thì mà để rất càng như những tại bởi do the a an of to and".split())
MIN_EVENT_SEC = 0.7
SIDE_MARGIN = 60  # = marginl / marginr của style
OUTLINE = 3
# libass hiểu Fontsize là chiều cao cả dòng (theo metric win của font), Pillow hiểu là cỡ em → chữ thật trên khung =
# 0,65 × Pillow cùng cỡ (đo 31/10, Be Vietnam Pro Bold cỡ 64 trên 1080×1920: 600/921 px, 557/857 px).
LIBASS_SCALE = 0.65
READ_CAP = 32.0  # dòng dài hơn ~32 ký tự khó đọc trên video dọc dù khung còn chỗ
_SAMPLE = "Hôm nay mình chia sẻ ba bước phối đồ đẹp"  # câu tiếng Việt thường → bề rộng trung bình một ký tự


class _Measure:
    """
    Độ dài một dòng theo «ký tự trung bình». Có file font → đo bằng Pillow (chữ hoa / chữ rộng tính đúng: 26 chữ «M»
    rộng gấp ~1,6 lần 26 chữ thường), giới hạn = bề ngang khung hoặc ``READ_CAP``; không có font → đếm ký tự,
    giới hạn ``max_chars``.
    """

    def __init__(self, *, font_file: str | None, font_size: int, width: int, max_chars: int):
        self.font = ImageFont.truetype(font_file, font_size) if font_file and os.path.isfile(font_file) else None
        if self.font is None:
            self.char_px, self.limit = 1.0, float(max_chars)
        else:
            self.char_px = self.font.getlength(_SAMPLE) / len(_SAMPLE) * LIBASS_SCALE
            self.limit = min(READ_CAP, (width - 2 * SIDE_MARGIN - 2 * OUTLINE) / self.char_px)

    def __call__(self, words: list[str]) -> float:
        text = " ".join(words)
        return len(text) if self.font is None else self.font.getlength(text) * LIBASS_SCALE / self.char_px


def _bare(word: str) -> str:
    return word.strip("\"'“”‘’()[]«»").lower()


def _name_pair(last: str, nxt: str) -> bool:
    """Hai chữ viết hoa liền nhau, không dấu câu giữa → một tên riêng («John Allen», «Royal North Devon»)."""
    return last[:1].isupper() and nxt[:1].isupper() and last[-1:].isalnum()


def _break_cost(left: list[str], right: list[str], m: _Measure) -> float:
    """Điểm phạt khi ngắt dòng giữa ``left`` và ``right`` (càng thấp càng tốt)."""
    a, b = m(left), m(right)
    cost = abs(a - b) + max(0.0, a - m.limit) * 50 + max(0.0, b - m.limit) * 50
    last, nxt = left[-1], right[0]
    if last.endswith(_END):
        cost -= 14
    elif last.endswith(_SOFT):
        cost -= 9
    if _bare(nxt) in _LEAD:
        cost -= 5
    if _bare(last) in _TAIL:
        cost += 12
    if _name_pair(last, nxt):
        cost += 15
    if len(left) == 1 or len(right) == 1:
        cost += 10
    return cost


def _rows(words: list[str], m: _Measure) -> list[str]:
    """Một lượt → 1 dòng (vừa) hoặc 2 dòng ngắt ở chỗ phạt thấp nhất."""
    if m(words) <= m.limit or len(words) < 2:
        return [" ".join(words)]
    i = min(range(1, len(words)), key=lambda k: _break_cost(words[:k], words[k:], m))
    return [" ".join(words[:i]), " ".join(words[i:])]


def _fits(words: list[str], m: _Measure) -> bool:
    return len(words) == 1 or all(m([r]) <= m.limit for r in _rows(words, m))


def _clean(words: list[str], m: _Measure) -> bool:
    """Vừa khung **và** ngắt sạch: không ngắt giữa tên riêng, dòng trên không treo ở từ nối."""
    if not _fits(words, m):
        return False
    rows = _rows(words, m)
    if len(rows) == 1:
        return True
    k = len(rows[0].split())
    return not _name_pair(words[k - 1], words[k]) and _bare(words[k - 1]) not in _TAIL


def _event_split_cost(left: list[str], right_first: str, total: float, n_events: int, m: _Measure) -> float:
    """Điểm phạt khi cắt lượt sau ``left``: ưu tiên dấu câu + các lượt dài gần bằng nhau, không cắt giữa tên riêng."""
    cost = abs(m(left) - total / n_events) * 0.6
    last = left[-1]
    if last.endswith(_END):
        cost -= 25
    elif last.endswith(_SOFT):
        cost -= 14
    if _bare(last) in _TAIL:
        cost += 15
    if _name_pair(last, right_first):
        cost += 20
    return cost


def _sentences(words: list[str], m: _Measure) -> list[list[str]]:
    """
    Tách sau dấu kết câu; mẩu < 3 chữ («Do đó», «Anh.») nhập vào câu kề để khỏi thành lượt lẻ — nhưng chỉ khi gộp
    xong vẫn vừa 2 dòng (không thì gộp làm câu kia phải ngắt giữa cụm / tên riêng, tệ hơn một lượt ngắn).
    """
    parts: list[list[str]] = [[]]
    for w in words:
        parts[-1].append(w)
        if w.endswith(_END):
            parts.append([])
    parts = [p for p in parts if p]
    out: list[list[str]] = []
    for p in parts:
        if out and (len(p) < 3 or len(out[-1]) < 3) and _clean(out[-1] + p, m):
            out[-1] = out[-1] + p
        else:
            out.append(p)
    return out


def split_caption(text: str, m: _Measure, max_rows: int = 2) -> list[list[str]]:
    """
    Câu → các lượt hiện chữ, mỗi lượt ≤ ``max_rows`` dòng vừa khung. Mỗi câu (theo dấu kết câu) một lượt khi được —
    chuẩn phụ đề, khỏi phải nhồi hai câu vào hai dòng rồi ngắt giữa cụm. Câu dài thì tách lượt ở dấu câu / chỗ cân nhất;
    trong lượt ngắt dòng theo cụm từ (``_break_cost``). Không để lượt / dòng chỉ một chữ khi tránh được.
    """
    words = text.split()
    if not words:
        return []
    sentences = _sentences(words, m)
    if len(sentences) > 1:
        return [chunk for sent in sentences for chunk in split_caption(" ".join(sent), m, max_rows)]
    if _fits(words, m):
        return [_rows(words, m)]
    total = m(words)
    n_events = max(2, math.ceil(total / (m.limit * max_rows * 0.92)))
    best = None
    for k in range(2, len(words) - 1):  # mỗi phần ≥ 2 chữ
        left = words[:k]
        if not _fits(left, m):
            break
        cost = _event_split_cost(left, words[k], total, n_events, m)
        if best is None or cost < best[0]:
            best = (cost, k)
    if best is None:  # một chữ quá dài / không cắt được — để nguyên
        return [_rows(words, m)]
    k = best[1]
    return [_rows(words[:k], m), *split_caption(" ".join(words[k:]), m, max_rows)]


def _timed(chunks: list[list[str]], start: float, end: float) -> list[tuple[float, float, str]]:
    """Chia [start, end] cho các lượt theo số ký tự (≥ ``MIN_EVENT_SEC`` khi đủ chỗ), liền nhau không hở."""
    lens = [max(1, sum(len(r) for r in c)) for c in chunks]
    span = end - start
    floor = MIN_EVENT_SEC if span >= MIN_EVENT_SEC * len(chunks) else 0.0
    spare = span - floor * len(chunks)
    out, t = [], start
    for i, (chunk, n) in enumerate(zip(chunks, lens)):
        e = end if i == len(chunks) - 1 else t + floor + spare * n / sum(lens)
        out.append((t, e, "\\N".join(chunk)))
        t = e
    return out


def build_ass(
    lines: list[dict], *, width: int, height: int, font_size: int, margin_v: int, max_chars: int,
    font_file: str | None = None,
) -> str:
    """Tối đa 2 dòng mỗi lần hiện; câu dài hơn chia thành nhiều lần, chia đều thời gian."""
    subs = pysubs2.SSAFile()
    measure = _Measure(font_file=font_file, font_size=font_size, width=width, max_chars=max_chars)
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
        for s, e, rows in _timed(split_caption(text, measure), start, end):
            subs.append(pysubs2.SSAEvent(start=pysubs2.make_time(s=s), end=pysubs2.make_time(s=e), text=rows))
    return subs.to_string("ass")
