"""
Chia audio thành đoạn ý (beat) và cảnh (shot) theo đúng audio tải lên (PLAN-157).

- Cảnh bám câu Whisper: gộp câu liền nhau tới gần ``shot_sec``; câu dài hơn ``shot_max_sec`` cắt đều;
  cảnh ngắn hơn ``shot_min_sec`` gộp vào cảnh bên cạnh. Dòng thời gian liền mạch: cảnh đầu từ 0, cảnh cuối tới hết audio,
  khoảng không lời nằm trong cảnh đứng trước.
- Đoạn ý mới khi hai câu cách nhau ≥ ``beat_pause_sec`` hoặc đoạn ý đã dài ≥ ``beat_max_sec``.
- Audio không có lời: chia đều theo ``shot_sec``.
Mọi ngưỡng đọc từ ``DocConfig`` (Cài đặt vận hành → Studio — Audio→Doc).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.features.studio.doc.config import DocConfig
from app.features.studio.doc.schema import DocState, FactStatus, Shot, StoryBeat, TranscriptSeg

SUMMARY_CHARS = 120


@dataclass
class _Group:
    start: int
    end: int
    texts: list[str] = field(default_factory=list)
    new_beat: bool = False


def lines_to_segments(lines: list[dict]) -> list[TranscriptSeg]:
    segs: list[TranscriptSeg] = []
    for line in lines:
        text = str(line.get("text") or "").strip()
        start_ms = int(round(float(line.get("start") or 0) * 1000))
        end_ms = int(round(float(line.get("end") or 0) * 1000))
        if end_ms < start_ms:
            end_ms = start_ms
        segs.append(TranscriptSeg(start_ms=start_ms, end_ms=end_ms, raw_text=text, reviewed_text=text))
    return segs


def _units(segs: list[TranscriptSeg], duration_ms: int, max_ms: int) -> list[tuple[int, int, str]]:
    """Câu có lời, cắt trong [0, duration]; câu dài hơn ``max_ms`` chia đều (chữ chia theo số từ)."""
    out: list[tuple[int, int, str]] = []
    for seg in sorted(segs, key=lambda x: x.start_ms):
        s, e = max(0, seg.start_ms), min(duration_ms, seg.end_ms)
        text = (seg.reviewed_text or seg.raw_text).strip()
        if e <= s or not text:
            continue
        n = max(1, -(-(e - s) // max_ms))  # ceil
        words = text.split()
        for k in range(n):
            ps, pe = s + (e - s) * k // n, s + (e - s) * (k + 1) // n
            chunk = " ".join(words[len(words) * k // n: len(words) * (k + 1) // n])
            out.append((ps, pe, chunk))
    return out


def _group(units: list[tuple[int, int, str]], cfg: DocConfig) -> list[_Group]:
    target, max_ms = int(cfg.shot_sec * 1000), int(cfg.shot_max_sec * 1000)
    pause_ms, beat_max = int(cfg.beat_pause_sec * 1000), int(cfg.beat_max_sec * 1000)
    groups: list[_Group] = []
    cur: _Group | None = None
    beat_start = 0
    prev_end: int | None = None
    for s, e, text in units:
        if cur is None:
            cur = _Group(start=s, end=e, texts=[text], new_beat=True)
        else:
            new_beat = (prev_end is not None and s - prev_end >= pause_ms) or s - beat_start >= beat_max
            if new_beat or e - cur.start > max_ms or cur.end - cur.start >= target:
                groups.append(cur)
                cur = _Group(start=s, end=e, texts=[text], new_beat=new_beat)
                if new_beat:
                    beat_start = s
            else:
                cur.end = e
                cur.texts.append(text)
        prev_end = e
    if cur is not None:
        groups.append(cur)
    return groups


def _timeline(groups: list[_Group], duration_ms: int, cfg: DocConfig) -> list[_Group]:
    """Nối liền: mỗi cảnh kéo tới đầu cảnh sau; gộp cảnh quá ngắn; cắt cảnh quá dài (khoảng lặng dài)."""
    min_ms, max_ms = int(cfg.shot_min_sec * 1000), int(cfg.shot_max_sec * 1000)
    if not groups:
        return []
    groups[0].start = 0
    for a, b in zip(groups, groups[1:]):
        a.end = b.start
    groups[-1].end = duration_ms

    merged: list[_Group] = []
    for g in groups:
        if merged and (g.end - g.start < min_ms or merged[-1].end - merged[-1].start < min_ms) and not g.new_beat:
            merged[-1].end = g.end
            merged[-1].texts += g.texts
        else:
            merged.append(g)
    if len(merged) > 1 and merged[-1].end - merged[-1].start < min_ms:  # đuôi ngắn → gộp vào cảnh trước
        tail = merged.pop()
        merged[-1].end = tail.end
        merged[-1].texts += tail.texts

    out: list[_Group] = []
    for g in merged:
        span = g.end - g.start
        n = max(1, -(-span // max_ms)) if span > max_ms else 1
        for k in range(n):
            out.append(_Group(
                start=g.start + span * k // n,
                end=g.start + span * (k + 1) // n,
                texts=g.texts if k == 0 else [],
                new_beat=g.new_beat and k == 0,
            ))
    return out


def _even(duration_ms: int, cfg: DocConfig) -> list[_Group]:
    step = max(1, int(cfg.shot_sec * 1000))
    beat_ms = max(step, int(cfg.beat_max_sec * 1000))
    out = [_Group(start=s, end=min(s + step, duration_ms), new_beat=(s % beat_ms) < step)
           for s in range(0, duration_ms, step)]
    if len(out) > 1 and out[-1].end - out[-1].start < int(cfg.shot_min_sec * 1000):
        out[-2].end = out.pop().end
    return out


def plan(duration_ms: int, segs: list[TranscriptSeg], cfg: DocConfig) -> tuple[list[StoryBeat], list[Shot]]:
    if duration_ms <= 0:
        return [], []
    units = _units(segs, duration_ms, max(1, int(cfg.shot_max_sec * 1000)))
    groups = _timeline(_group(units, cfg), duration_ms, cfg) if units else _even(duration_ms, cfg)
    if groups:
        groups[0].new_beat = True

    beats: list[StoryBeat] = []
    shots: list[Shot] = []
    local = 0
    motions = cfg.motions or ("static",)
    for g in groups:
        if g.new_beat:
            beats.append(StoryBeat(
                beat_id=f"BEAT-{len(beats) + 1:02d}", start_ms=g.start, end_ms=g.end,
                fact_status=FactStatus.UNVERIFIED,
            ))
            local = 0
        beat = beats[-1]
        beat.end_ms = g.end
        local += 1
        text = " ".join(t for t in g.texts if t).strip()
        shots.append(Shot(
            shot_id=f"SHOT-{beat.beat_id[-2:]}-{local:02d}",
            beat_id=beat.beat_id,
            start_ms=g.start,
            end_ms=g.end,
            narration=text,
            motion=motions[(len(shots)) % len(motions)],  # type: ignore[arg-type]
        ))
    for beat in beats:
        text = " ".join(s.narration for s in shots if s.beat_id == beat.beat_id and s.narration)
        beat.summary = text[:SUMMARY_CHARS]
    return beats, shots


def build_initial_state(
    *,
    audio_asset_id: int,
    duration_ms: int,
    transcript_lines: list[dict],
    lang: str | None,
    cfg: DocConfig,
) -> DocState:
    duration_ms = max(0, int(duration_ms))
    segs = lines_to_segments(transcript_lines)
    beats, shots = plan(duration_ms, segs, cfg)
    return DocState(
        audio_asset_id=audio_asset_id,
        duration_ms=duration_ms,
        language=lang,
        transcript=segs,
        beats=beats,
        shots=shots,
        preview_end_ms=duration_ms if cfg.preview_ms <= 0 else min(cfg.preview_ms, duration_ms),
        audit=[{"action": "seed", "beats": len(beats), "shots": len(shots)}],
    )
