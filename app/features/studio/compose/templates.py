"""
Mẫu edit = hàm thuần ``(ComposeInput) -> ProjectSpec``. Không đọc DB, không chạy ffmpeg.

Thêm mẫu: viết hàm, đăng ký vào ``TEMPLATES``. ``StudioTemplate.kind`` trỏ tới tên ở đây,
``StudioTemplate.params`` là tham số anh chỉnh trên web.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

from app.features.studio.spec import (
    Audio,
    AudioTrack,
    Canvas,
    Clip,
    ClipAudio,
    Logo,
    ProjectSpec,
    Subtitles,
    TextOverlay,
)

MAX_CUT_CLIPS = 60  # own_footage: quá số đoạn này thì gộp bớt — mỗi đoạn là một input ffmpeg


@dataclass(frozen=True)
class ComposeInput:
    asset_id: int
    duration: float
    has_audio: bool
    has_transcript: bool
    credit: str | None = None
    params: dict = field(default_factory=dict)
    transcript_lang: str | None = None  # None = không rõ (coi như đúng ngôn ngữ phụ đề)
    dub: dict | None = None  # phân tích ``dub`` của asset (bước lồng tiếng)
    silences: list[dict] = field(default_factory=list)  # [{"start", "end"}] giây asset
    # nhận diện kênh (asset id) — None khi kênh chưa có
    intro_asset_id: int | None = None
    outro_asset_id: int | None = None
    logo_asset_id: int | None = None
    show_credit: bool = True


def basic(inp: ComposeInput) -> ProjectSpec:
    """
    Một video gốc → một video dọc 9:16: cắt đầu / độ dài tối đa, phụ đề lời thoại, chữ hook,
    nhạc nền, intro / outro / logo của kênh, ghi nguồn.

    params: ``trim_head`` (giây bỏ đầu, 0), ``max_len`` (giây, 0 = không cắt), ``subtitles`` (True),
    ``subtitle_lang`` (vi — lời thoại tiếng khác thì không đốt phụ đề), ``fit`` (blur_pad), ``hook``
    (chữ 3 giây đầu), ``hook_sec`` (3), ``music_asset_id``, ``music_volume`` (0.12),
    ``original_volume`` (1.0), ``font_size``, ``margin_v``.
    """
    p = inp.params
    start = max(0.0, float(p.get("trim_head") or 0.0))
    if inp.duration and start >= inp.duration:
        start = 0.0
    end = None
    max_len = float(p.get("max_len") or 0.0)
    if max_len > 0 and (not inp.duration or start + max_len < inp.duration):
        end = start + max_len
    return _finish(inp, [Clip(asset=inp.asset_id, start=start, end=end)], _subtitles(inp, "transcript"))


def _subtitles(inp: ComposeInput, source: str) -> Subtitles:
    p = inp.params
    if source == "dub":
        on = True
    else:
        want = p.get("subtitle_lang", "vi")
        on = inp.has_transcript and (not want or not inp.transcript_lang or inp.transcript_lang == want)
    subtitles = Subtitles(enabled=bool(p.get("subtitles", True)) and on, source=source)
    if p.get("font_size"):
        subtitles.font_size = int(p["font_size"])
    if p.get("margin_v") is not None:
        subtitles.margin_v = int(p["margin_v"])
    return subtitles


def _finish(inp: ComposeInput, clips: list[Clip], subtitles: Subtitles, *, original: float | None = None) -> ProjectSpec:
    """Phần chung mọi mẫu: intro / outro / logo của kênh, chữ hook, nhạc nền, ghi nguồn."""
    p = inp.params
    if inp.intro_asset_id:
        clips.insert(0, Clip(asset=inp.intro_asset_id))
    if inp.outro_asset_id:
        clips.append(Clip(asset=inp.outro_asset_id))

    texts = []
    hook = str(p.get("hook") or "").strip()
    if hook:
        texts.append(TextOverlay(text=hook, start=0.0, end=float(p.get("hook_sec") or 3.0), pos="top"))

    tracks = []
    if p.get("music_asset_id"):
        tracks.append(AudioTrack(asset=int(p["music_asset_id"]), volume=float(p.get("music_volume", 0.12)), loop=True))

    if original is None:
        original = float(p.get("original_volume", 1.0)) if inp.has_audio else 0.0
    return ProjectSpec(
        canvas=Canvas(fit=p.get("fit") or "blur_pad"),
        clips=clips,
        subtitles=subtitles,
        texts=texts,
        audio=Audio(original=original, tracks=tracks),
        logo=Logo(asset=inp.logo_asset_id) if inp.logo_asset_id else None,
        credit=f"Nguồn: {inp.credit}" if (inp.show_credit and inp.credit) else None,
    )


def reup_dub(inp: ComposeInput) -> ProjectSpec:
    """
    Như ``basic`` nhưng tiếng là bản lồng tiếng Việt (bước ``dub``): giọng đọc + nền đã tách giọng gốc,
    phụ đề là câu đã dịch. Không lồng được (đã là tiếng Việt, không có lời…) → y như ``basic``.

    params thêm: ``dub_lang`` (vi), ``dub_voice`` (female/male), ``voice_volume`` (1.0),
    ``background_volume`` (nhân với mức bước dub gợi ý: 1.0 khi tách được giọng, 0.15 khi không).
    """
    spec = basic(inp)
    dub = inp.dub or {}
    if not dub.get("ok"):
        return spec
    p = inp.params
    audio = [
        ClipAudio(asset=int(dub["voice_asset"]), volume=float(p.get("voice_volume", 1.0))),
        ClipAudio(
            asset=int(dub["background_asset"]),
            volume=float(p.get("background_volume", 1.0)) * float(dub.get("background_volume", 1.0)),
        ),
    ]
    clips = [c.model_copy(update={"audio": audio}) if c.asset == inp.asset_id else c for c in spec.clips]
    return spec.model_copy(update={"clips": clips, "subtitles": _subtitles(inp, "dub")})


def speech_ranges(duration: float, silences: list[dict], *, min_gap: float, pad: float) -> list[tuple[float, float]]:
    """
    Các đoạn có tiếng giữa những khoảng lặng dài ≥ ``min_gap``; mỗi đoạn nới ``pad`` hai đầu để
    không cụt hơi. Quá ``MAX_CUT_CLIPS`` đoạn thì gộp các khe ngắn nhất trước.
    """
    gaps = sorted(
        (max(0.0, float(s["start"])), min(duration, float(s["end"])))
        for s in silences if float(s["end"]) - float(s["start"]) >= min_gap
    )
    ranges: list[tuple[float, float]] = []
    cursor = 0.0
    for g_start, g_end in gaps:
        if g_start - cursor > 0.05:
            ranges.append((cursor, g_start))
        cursor = max(cursor, g_end)
    if duration - cursor > 0.05:
        ranges.append((cursor, duration))
    while len(ranges) > MAX_CUT_CLIPS:
        k = min(range(len(ranges) - 1), key=lambda i: ranges[i + 1][0] - ranges[i][1])
        ranges[k:k + 2] = [(ranges[k][0], ranges[k + 1][1])]
    padded = [(max(0.0, a - pad), min(duration, b + pad)) for a, b in ranges]
    merged: list[tuple[float, float]] = []
    for a, b in padded:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return [(round(a, 3), round(b, 3)) for a, b in merged if b - a >= 0.2]


def own_footage(inp: ComposeInput) -> ProjectSpec:
    """
    Video anh tự quay: cắt bỏ khoảng lặng (jump cut), phụ đề lời nói, không ghi nguồn.

    params thêm: ``cut_silence`` (True), ``min_silence`` (0.6 giây — lặng ngắn hơn thì giữ),
    ``pad`` (0.12 giây nới mỗi đầu), ``trim_head`` / ``max_len`` áp lên video **sau** khi cắt.
    Không có tiếng / không thấy khoảng lặng → giữ nguyên như ``basic``.
    """
    inp = replace(inp, show_credit=False)
    p = inp.params
    ranges: list[tuple[float, float]] = []
    if p.get("cut_silence", True) and inp.has_audio and inp.duration and inp.silences:
        ranges = speech_ranges(
            inp.duration, inp.silences,
            min_gap=float(p.get("min_silence", 0.6)), pad=float(p.get("pad", 0.12)),
        )

    skip = max(0.0, float(p.get("trim_head") or 0.0))
    budget = float(p.get("max_len") or 0.0) or float("inf")
    clips: list[Clip] = []
    for a, b in ranges:
        if skip > 0:
            take = min(skip, b - a)
            a, skip = a + take, skip - take
        if b - a < 0.2 or budget <= 0:
            continue
        b = min(b, a + budget)
        budget -= b - a
        clips.append(Clip(asset=inp.asset_id, start=a, end=b))
    if not clips:
        return basic(inp)
    return _finish(inp, clips, _subtitles(inp, "transcript"))


TEMPLATES: dict[str, Callable[[ComposeInput], ProjectSpec]] = {
    "basic": basic,
    "reup_dub": reup_dub,
    "own_footage": own_footage,
}
