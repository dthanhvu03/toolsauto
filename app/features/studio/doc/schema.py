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


class Shot(_Strict):
    shot_id: str
    beat_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    narration: str = ""
    motion: Motion = "slow_zoom_in"
    selected: ImageRef | None = None
    status: str = "EMPTY"  # EMPTY | HAS_IMAGE | APPROVED


class DocState(_Strict):
    v: Literal[1] = 1
    audio_asset_id: int
    project_id: int | None = None
    duration_ms: int = 0
    language: str | None = None
    transcript: list[TranscriptSeg] = Field(default_factory=list)
    beats: list[StoryBeat] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    preview_end_ms: int = 60_000  # POC: preview tối đa 60s
    audit: list[dict] = Field(default_factory=list)


# Trạng thái quyền cho phép đưa vào bản xuất / preview phát hành
EXPORTABLE_RIGHTS = frozenset({RightsStatus.RIGHTS_VERIFIED, RightsStatus.APPROVED})
