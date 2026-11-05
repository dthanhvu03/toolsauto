"""Seed beats/shots theo BRD §9.2 (MU–Roma). Mốc ms cắt theo duration thực tế của audio."""
from __future__ import annotations

from app.features.studio.doc.schema import (
    DocState,
    FactStatus,
    Shot,
    StoryBeat,
    TranscriptSeg,
)

# (start_ms, end_ms, summary, entities, fact_status, image_hint, motion)
_BEATS: list[tuple[int, int, str, list[str], FactStatus, str, str]] = [
    (0, 59_000, "Hook: đêm ngược dòng, áp lực Carrick",
     ["Manchester United", "Carrick", "Old Trafford"], FactStatus.UNVERIFIED,
     "Old Trafford đêm thi đấu, Carrick, cầu thủ MU", "slow_zoom_in"),
    (59_000, 79_000, "Giới thiệu kênh và CTA",
     [], FactStatus.OPINION, "Ảnh rộng sân/khán đài hoặc nhận diện kênh", "static"),
    (79_000, 177_000, "MU bị dẫn 0–2, tâm lý và bối cảnh",
     ["Carrick", "Manchester United", "AS Roma"], FactStatus.UNVERIFIED,
     "Carrick đường biên, cầu thủ MU cuối hiệp một", "pan_left"),
    (177_000, 279_000, "Roma ghi hai bàn, lỗi phòng ngự",
     ["Matías Soulé", "Donyell Malen", "AS Roma"], FactStatus.UNVERIFIED,
     "Soulé 11', Malen pen 17'", "slow_zoom_in"),
    (279_000, 397_000, "HLV điều chỉnh, nhân sự, pressing",
     ["Carrick", "Matheus Cunha", "Bruno Fernandes"], FactStatus.OPINION,
     "Carrick, Cunha, Bruno, toàn cảnh đội hình", "pan_right"),
    (397_000, 468_000, "Penalty Bruno, Cunha gỡ hòa và ấn định 3–2",
     ["Bruno Fernandes", "Matheus Cunha"], FactStatus.UNVERIFIED,
     "Bruno pen 58', Cunha 83' và 86'", "slow_zoom_in"),
    (468_000, 539_000, "Cunha thẻ đỏ; ý nghĩa chiến thắng",
     ["Matheus Cunha", "Carrick"], FactStatus.UNVERIFIED,
     "Cunha trong trận, Carrick, đội bóng", "slow_zoom_out"),
    (539_000, 564_036, "Câu hỏi khán giả, CTA và kết",
     ["Carrick", "Old Trafford"], FactStatus.OPINION,
     "Carrick, toàn cảnh Old Trafford", "static"),
]

_SHOT_TARGET_MS = 7_000  # ~4–10s; mặc định 7s


def _clamp_beats(duration_ms: int) -> list[StoryBeat]:
    out: list[StoryBeat] = []
    for i, (a, b, summary, entities, fact, hint, _motion) in enumerate(_BEATS, start=1):
        start = min(a, duration_ms)
        end = min(b, duration_ms)
        if end <= start:
            continue
        out.append(StoryBeat(
            beat_id=f"BEAT-{i:02d}",
            start_ms=start,
            end_ms=end,
            summary=summary,
            entities=entities,
            fact_status=fact,
            image_hint=hint,
        ))
    if not out and duration_ms > 0:
        out.append(StoryBeat(
            beat_id="BEAT-01", start_ms=0, end_ms=duration_ms,
            summary="Toàn bộ audio", fact_status=FactStatus.UNVERIFIED,
        ))
    return out


def _shots_for_beats(beats: list[StoryBeat]) -> list[Shot]:
    shots: list[Shot] = []
    n = 0
    motions = ["slow_zoom_in", "pan_left", "slow_zoom_out", "pan_right", "static"]
    for beat in beats:
        pos = beat.start_ms
        local = 0
        while pos < beat.end_ms:
            local += 1
            n += 1
            end = min(pos + _SHOT_TARGET_MS, beat.end_ms)
            if end - pos < 1_500 and local > 1:
                break
            shots.append(Shot(
                shot_id=f"SHOT-{beat.beat_id[-2:]}-{local:02d}",
                beat_id=beat.beat_id,
                start_ms=pos,
                end_ms=end,
                narration=beat.summary if local == 1 else "",
                motion=motions[(n - 1) % len(motions)],  # type: ignore[arg-type]
            ))
            pos = end
    return shots


def lines_to_segments(lines: list[dict]) -> list[TranscriptSeg]:
    segs: list[TranscriptSeg] = []
    for line in lines:
        text = str(line.get("text") or "").strip()
        start_ms = int(round(float(line.get("start") or 0) * 1000))
        end_ms = int(round(float(line.get("end") or 0) * 1000))
        if end_ms < start_ms:
            end_ms = start_ms
        segs.append(TranscriptSeg(
            start_ms=start_ms, end_ms=end_ms, raw_text=text, reviewed_text=text,
        ))
    return segs


def build_initial_state(
    *,
    audio_asset_id: int,
    duration_ms: int,
    transcript_lines: list[dict],
    lang: str | None,
) -> DocState:
    duration_ms = max(0, int(duration_ms))
    beats = _clamp_beats(duration_ms)
    return DocState(
        audio_asset_id=audio_asset_id,
        duration_ms=duration_ms,
        language=lang,
        transcript=lines_to_segments(transcript_lines),
        beats=beats,
        shots=_shots_for_beats(beats),
        preview_end_ms=min(60_000, duration_ms or 60_000),
        audit=[{"action": "seed", "beats": len(beats)}],
    )
