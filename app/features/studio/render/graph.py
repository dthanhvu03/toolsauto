"""
spec → một lệnh ffmpeg (``filter_complex``), **một lượt encode**. Hàm thuần: không đọc DB, không
chạy gì, không ghi file — file phụ (ASS, chữ) trả về trong ``RenderPlan.files`` để runner ghi.

Sơ đồ:
    mỗi clip → khớp khung (fit) + fps + yuv420p  ┐
    mỗi clip → tiếng gốc × original (thiếu → im;  ┘→ concat
               clip có ``audio`` → trộn các file đó, cùng mốc giây) → [phụ đề → chữ → ghi nguồn → logo] → [vout]
    concat audio + các track (trễ / lặp / âm lượng) → amix → [aout]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.features.studio.render.subtitles import apply_edits, build_ass, shift_lines
from app.features.studio.spec import ProjectSpec

IMAGE_DEFAULT_SEC = 3.0
_SR = 48000
_AFMT = f"aresample={_SR},aformat=sample_fmts=fltp:channel_layouts=stereo"
_TEXT_Y = {"top": "h*0.12", "center": "(h-text_h)/2", "bottom": "h*0.72"}
_LOGO_XY = {"tl": ("40", "40"), "tr": ("W-w-40", "40"), "bl": ("40", "H-h-40"), "br": ("W-w-40", "H-h-40")}


@dataclass(frozen=True)
class Media:
    path: str
    kind: str  # video | audio | image
    duration: float
    has_audio: bool


@dataclass
class RenderPlan:
    argv: list[str]
    duration: float
    files: dict[str, str] = field(default_factory=dict)  # đường dẫn → nội dung, runner ghi trước khi chạy


class SpecError(ValueError):
    """Spec trỏ tới asset không có / không dùng được."""


def _q(value: str) -> str:
    """Giá trị trong filtergraph: bọc nháy đơn để ``:`` ``,`` trong đường dẫn không cắt ngang filter."""
    return "'" + str(value).replace("\\", "\\\\").replace("'", "'\\''") + "'"


def _num(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def clip_ranges(spec: ProjectSpec, media: dict[int, Media]) -> list[tuple[int, float, float]]:
    """``(asset, start, end)`` đã chốt: end thiếu → hết asset (ảnh: 3 giây), end quá dài → cắt về hết asset."""
    out = []
    for clip in spec.clips:
        m = media.get(clip.asset)
        if m is None:
            raise SpecError(f"clip trỏ tới asset #{clip.asset} không có")
        if m.kind == "audio":
            raise SpecError(f"asset #{clip.asset} là audio, không làm clip hình được")
        if m.kind == "image":
            end = clip.end if clip.end is not None else clip.start + IMAGE_DEFAULT_SEC
        else:
            end = m.duration if clip.end is None else min(clip.end, m.duration)
        if end - clip.start < 0.1:
            raise SpecError(f"clip asset #{clip.asset}: đoạn {clip.start}–{end}s rỗng")
        out.append((clip.asset, clip.start, end))
    return out


def _fit_chain(src: str, out: str, i: int, spec: ProjectSpec) -> str:
    c = spec.canvas
    tail = f"setsar=1,fps={c.fps},format=yuv420p[{out}]"
    cover = f"scale={c.w}:{c.h}:force_original_aspect_ratio=increase,crop={c.w}:{c.h}"
    contain = f"scale={c.w}:{c.h}:force_original_aspect_ratio=decrease:force_divisible_by=2"
    if c.fit == "crop":
        return f"[{src}]{cover},{tail}"
    if c.fit == "pad":
        return f"[{src}]{contain},pad={c.w}:{c.h}:(ow-iw)/2:(oh-ih)/2:color=black,{tail}"
    # Nền mờ làm ở 1/4 kích thước rồi phóng lên: nhìn như nhau, nhanh hơn nhiều lần so với blur full-HD.
    qw, qh = c.w // 8 * 2, c.h // 8 * 2
    return (
        f"[{src}]split=2[bg{i}][fg{i}];"
        f"[bg{i}]scale={qw}:{qh}:force_original_aspect_ratio=increase,crop={qw}:{qh},"
        f"boxblur=10:1,scale={c.w}:{c.h}[bgb{i}];"
        f"[fg{i}]{contain}[fgs{i}];"
        f"[bgb{i}][fgs{i}]overlay=(W-w)/2:(H-h)/2,{tail}"
    )


def build(
    spec: ProjectSpec,
    media: dict[int, Media],
    *,
    output: str,
    workdir: str,
    font_file: str,
    fonts_dir: str,
    transcripts: dict[int, list[dict]] | None = None,  # câu thoại theo giây asset, theo ``subtitles.source``
    ffmpeg: str = "ffmpeg",
    crf: int = 21,
    preset: str = "veryfast",
) -> RenderPlan:
    ranges = clip_ranges(spec, media)
    total = sum(end - start for _, start, end in ranges)
    work = Path(workdir)
    files: dict[str, str] = {}
    inputs: list[str] = []
    graph: list[str] = []
    n_in = 0

    # ── clip: hình + tiếng gốc ──
    for i, (asset_id, start, end) in enumerate(ranges):
        m = media[asset_id]
        dur = end - start
        if m.kind == "image":
            inputs += ["-loop", "1", "-framerate", str(spec.canvas.fps), "-t", _num(dur), "-i", m.path]
        else:
            inputs += ["-ss", _num(start), "-t", _num(dur), "-i", m.path]
        graph.append(_fit_chain(f"{n_in}:v", f"v{i}", i, spec))
        own_audio = m.has_audio and m.kind == "video" and spec.audio.original > 0
        n_in += 1
        subs = spec.clips[i].audio
        if subs:
            parts = []
            for j, ca in enumerate(subs):
                am = media.get(ca.asset)
                if am is None or am.kind != "audio":
                    raise SpecError(f"tiếng của clip phải là asset audio (#{ca.asset})")
                inputs += ["-ss", _num(start), "-t", _num(dur), "-i", am.path]
                graph.append(f"[{n_in}:a]{_AFMT},volume={_num(ca.volume)},apad,atrim=0:{_num(dur)}[a{i}s{j}]")
                parts.append(f"[a{i}s{j}]")
                n_in += 1
            if len(parts) == 1:
                graph.append(f"{parts[0]}anull[a{i}]")
            else:
                graph.append(f"{''.join(parts)}amix=inputs={len(parts)}:duration=first:normalize=0[a{i}]")
        elif own_audio:
            graph.append(f"[{n_in - 1}:a]{_AFMT},volume={_num(spec.audio.original)},apad,atrim=0:{_num(dur)}[a{i}]")
        else:
            graph.append(f"aevalsrc=0:c=stereo:s={_SR}:d={_num(dur)}[a{i}]")

    pairs = "".join(f"[v{i}][a{i}]" for i in range(len(ranges)))
    graph.append(f"{pairs}concat=n={len(ranges)}:v=1:a=1[vcat][acat]")

    # ── lớp trên hình ──
    post: list[str] = []
    sub = spec.subtitles
    if sub.enabled:
        if sub.source == "lines":
            lines = [line.model_dump() for line in sub.lines]
        else:
            lines = shift_lines(ranges, transcripts or {})
        lines = apply_edits(lines, sub.edits)
        if lines:
            ass_path = str(work / "subs.ass")
            files[ass_path] = build_ass(
                lines, width=spec.canvas.w, height=spec.canvas.h,
                font_size=sub.font_size, margin_v=sub.margin_v, max_chars=sub.max_chars,
            )
            post.append(f"ass={_q(ass_path)}:fontsdir={_q(fonts_dir)}")

    def drawtext(text_path: str, *, size: int, x: str, y: str, enable: str | None = None, alpha: str = "1") -> str:
        f = (
            f"drawtext=fontfile={_q(font_file)}:textfile={_q(text_path)}:expansion=none:"
            f"fontsize={size}:fontcolor=white@{alpha}:borderw=4:bordercolor=black@{alpha}:x={x}:y={y}"
        )
        return f + (f":enable={_q(enable)}" if enable else "")

    for k, t in enumerate(spec.texts):
        text_path = str(work / f"text{k}.txt")
        files[text_path] = t.text
        end = total if t.end is None else min(t.end, total)
        post.append(drawtext(text_path, size=t.size, x="(w-text_w)/2", y=_TEXT_Y[t.pos],
                             enable=f"between(t,{_num(t.start)},{_num(end)})"))

    if spec.credit:
        credit_path = str(work / "credit.txt")
        files[credit_path] = spec.credit
        post.append(drawtext(credit_path, size=max(24, spec.canvas.w // 32), x="40", y="h-text_h-50", alpha="0.85"))

    chain = ",".join(post) if post else "null"
    if spec.logo:
        lm = media.get(spec.logo.asset)
        if lm is None or lm.kind != "image":
            raise SpecError(f"logo phải là asset ảnh (#{spec.logo.asset})")
        inputs += ["-i", lm.path]
        x, y = _LOGO_XY[spec.logo.pos]
        graph.append(f"[vcat]{chain}[vpost]")
        graph.append(f"[{n_in}:v]scale={int(spec.canvas.w * spec.logo.width)}:-2[logo]")
        graph.append(f"[vpost][logo]overlay={x}:{y}:eof_action=repeat[vout]")
        n_in += 1
    else:
        graph.append(f"[vcat]{chain}[vout]")

    # ── tiếng: gốc + các track ──
    mix = ["[acat]"]
    for k, track in enumerate(spec.audio.tracks):
        tm = media.get(track.asset)
        if tm is None or not tm.has_audio:
            raise SpecError(f"track trỏ tới asset #{track.asset} không có tiếng")
        inputs += (["-stream_loop", "-1"] if track.loop else []) + ["-i", tm.path]
        delay = int(round(track.start * 1000))
        graph.append(
            f"[{n_in}:a]{_AFMT},volume={_num(track.volume)}"
            + (f",adelay={delay}|{delay}" if delay else "")
            + f",atrim=0:{_num(total)}[t{k}]"
        )
        mix.append(f"[t{k}]")
        n_in += 1
    if len(mix) > 1:
        graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        graph.append("[acat]anull[aout]")

    argv = [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        *inputs,
        "-filter_complex", ";".join(graph),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", str(_SR),
        "-t", _num(total), "-movflags", "+faststart",
        output,
    ]
    return RenderPlan(argv=argv, duration=total, files=files)
