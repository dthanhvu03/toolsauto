"""Mô hình DocState POC — lưu JSON trong ``studio_analysis`` kind=``doc``."""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactStatus(StrEnum):
    VERIFIED = "FACT_VERIFIED"
    CONFLICT = "FACT_CONFLICT"
    OPINION = "OPINION"
    UNVERIFIED = "UNVERIFIED"


class RightsStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    MATCH_REVIEWED = "MATCH_REVIEWED"
    RIGHTS_VERIFIED = "RIGHTS_VERIFIED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    UNKNOWN = "RIGHTS_UNKNOWN"
    RESTRICTED = "RIGHTS_RESTRICTED"


Motion = Literal["static", "slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right"]


class TranscriptSeg(_Strict):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    raw_text: str = ""
    reviewed_text: str = ""


class StoryBeat(_Strict):
    beat_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    fact_status: FactStatus = FactStatus.UNVERIFIED
    image_hint: str = ""


class ImageRef(_Strict):
    asset_id: int
    source_page: str = ""
    credit: str = ""
    license: str = ""
    rights_status: RightsStatus = RightsStatus.UNKNOWN
    illustration: bool = False
    proof_note: str = ""
    provider: str = "upload"  # upload | wikimedia | openverse | pexels | pixabay | google
    license_url: str = ""
    author: str = ""


class Candidate(_Strict):
    """Một ảnh gợi ý từ internet (PLAN-157) — chưa tải về, chỉ là kết quả tìm."""

    provider: str
    image_url: str
    thumb_url: str = ""
    source_page: str = ""
    title: str = ""
    author: str = ""
    license: str = ""  # đã chuẩn hoá: cc0 | pdm | cc-by | cc-by-sa | cc-by-nc… | pexels | pixabay | unknown
    license_url: str = ""
    width: int = 0
    height: int = 0


class Shot(_Strict):
    shot_id: str
    beat_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    narration: str = ""
    motion: Motion = "slow_zoom_in"
    selected: ImageRef | None = None
    status: str = "EMPTY"  # EMPTY | HAS_IMAGE | APPROVED
    keywords: list[str] = Field(default_factory=list)  # từ khóa tìm ảnh (AI đề xuất, sửa được)
    candidates: list[Candidate] = Field(default_factory=list)  # kết quả tìm gần nhất
    search_note: str = ""  # nguồn nào lỗi / thiếu key ở lần tìm gần nhất


class DocState(_Strict):
    v: Literal[1] = 1
    audio_asset_id: int
    project_id: int | None = None
    duration_ms: int = 0
    language: str | None = None
    transcript: list[TranscriptSeg] = Field(default_factory=list)
    beats: list[StoryBeat] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    preview_end_ms: int = 0  # mốc cuối bản dựng (ms); ghi lại từ cấu hình doc.preview_sec mỗi lần dựng
    audit: list[dict] = Field(default_factory=list)
