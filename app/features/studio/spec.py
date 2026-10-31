"""
ADR-061 — ``ProjectSpec``: bản mô tả một video ra. Hợp đồng giữa compose (sinh), trình edit (sửa)
và render (dựng).

Mốc giây trong ``clips`` là giây **của asset gốc**. Mốc giây trong ``texts``, ``subtitles.lines``
và ``audio.tracks[].start`` là giây **của video ra**. ``extra="forbid"``: trình edit gửi sai tên
trường thì báo lỗi ngay, không âm thầm bỏ qua.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Canvas(_Strict):
    w: int = Field(1080, ge=240, le=4096)
    h: int = Field(1920, ge=240, le=4096)
    fps: int = Field(30, ge=1, le=60)
    # blur_pad: hình gốc giữa khung, nền là chính nó phóng to làm mờ. crop: lấp đầy, cắt mép. pad: viền đen.
    fit: Literal["blur_pad", "crop", "pad"] = "blur_pad"


class ClipAudio(_Strict):
    asset: int
    volume: float = Field(1.0, ge=0, le=4)


class Clip(_Strict):
    asset: int
    start: float = Field(0.0, ge=0)
    end: float | None = None  # None = tới hết asset; ảnh tĩnh bắt buộc có
    # Có thì tiếng của clip lấy từ các asset audio này, **cùng mốc giây với asset hình** (thay tiếng
    # gốc). Dùng cho lồng tiếng: giọng đọc + nền đã tách, dài đúng bằng video gốc.
    audio: list[ClipAudio] = Field(default_factory=list)

    @model_validator(mode="after")
    def _end_after_start(self) -> "Clip":
        if self.end is not None and self.end <= self.start:
            raise ValueError(f"clip asset {self.asset}: end ({self.end}) phải lớn hơn start ({self.start})")
        return self


class SubLine(_Strict):
    start: float = Field(ge=0)
    end: float
    text: str


class Subtitles(_Strict):
    enabled: bool = False
    # transcript: lời thoại đã phân tích của asset; dub: câu đã dịch của bước lồng tiếng — cả hai tự dời
    # theo đoạn cắt. lines: dùng ``lines`` (giây video ra).
    source: Literal["transcript", "dub", "lines"] = "transcript"
    lines: list[SubLine] = Field(default_factory=list)
    # Sửa tay theo số thứ tự dòng sau khi dời (0-based); chuỗi rỗng = bỏ dòng đó.
    edits: dict[int, str] = Field(default_factory=dict)
    font_size: int = Field(64, ge=16, le=200)
    margin_v: int = Field(260, ge=0, le=1500)
    max_chars: int = Field(22, ge=8, le=80)


class TextOverlay(_Strict):
    text: str = Field(min_length=1)
    start: float = Field(0.0, ge=0)
    end: float | None = None  # None = tới hết video
    pos: Literal["top", "center", "bottom"] = "top"
    size: int = Field(72, ge=12, le=300)


class AudioTrack(_Strict):
    asset: int
    volume: float = Field(1.0, ge=0, le=4)
    start: float = Field(0.0, ge=0)
    loop: bool = False


class Audio(_Strict):
    original: float = Field(1.0, ge=0, le=4)  # âm lượng tiếng gốc của các clip
    tracks: list[AudioTrack] = Field(default_factory=list)


class Logo(_Strict):
    asset: int
    pos: Literal["tl", "tr", "bl", "br"] = "tr"
    width: float = Field(0.16, gt=0, le=1)  # tỉ lệ theo chiều ngang khung


class ProjectSpec(_Strict):
    v: Literal[1] = 1
    canvas: Canvas = Field(default_factory=Canvas)
    clips: list[Clip] = Field(min_length=1)
    subtitles: Subtitles = Field(default_factory=Subtitles)
    texts: list[TextOverlay] = Field(default_factory=list)
    audio: Audio = Field(default_factory=Audio)
    logo: Logo | None = None
    credit: str | None = None

    def asset_ids(self) -> set[int]:
        ids = {c.asset for c in self.clips} | {t.asset for t in self.audio.tracks}
        ids |= {a.asset for c in self.clips for a in c.audio}
        if self.logo:
            ids.add(self.logo.asset)
        return ids
