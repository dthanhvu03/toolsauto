"""
ADR-061 — thứ duy nhất các bước Studio dùng chung: tên bước, trạng thái, kết quả, lỗi.

Mỗi bước là một hàm ``run(db, task) -> StageResult``. Bước không biết bước nào chạy trước hay
sau nó — chỉ ``pipeline.py`` biết. Bước muốn dừng quy trình (trùng, chờ duyệt) thì trả
``stop=True``; muốn báo lỗi thì ném ``StageError``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Stage(StrEnum):
    FETCH = "fetch"  # tải video từ link (PLAN-113) — đứng đầu nên hạng thấp nhất: dự án đang dở làm xong trước
    INTAKE = "intake"
    ANALYZE = "analyze"
    DUB = "dub"
    COMPOSE = "compose"
    RENDER = "render"
    CAPTION = "caption"
    REVIEW = "review"
    PUBLISH = "publish"


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    RENDERING = "RENDERING"
    RENDERED = "RENDERED"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    POSTED = "POSTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class Lane(StrEnum):
    HEAVY = "heavy"  # ffmpeg / Whisper / Demucs — 1 việc mỗi lần
    LIGHT = "light"


HEAVY_STAGES = frozenset({Stage.ANALYZE, Stage.DUB, Stage.RENDER, Stage.CAPTION})


# Thứ tự bước trong quy trình — hàng việc ưu tiên bước sau để làm XONG từng dự án trước khi bắt đầu dự án khác
# (8 biến thể xếp cùng lúc: bản đầu có sau ~1 phút thay vì chờ render hết cả lô).
STAGE_RANK: dict[str, int] = {s.value: i for i, s in enumerate(Stage)}


def lane_for(stage: Stage | str) -> Lane:
    return Lane.HEAVY if Stage(stage) in HEAVY_STAGES else Lane.LIGHT


@dataclass
class StageResult:
    """
    ``asset_id`` / ``project_id``: bước vừa tạo ra hoặc làm việc trên cái nào — bước sau nhận lại.
    ``payload``: gộp vào payload của bước sau (ví dụ ``channel_id`` đi suốt quy trình).
    ``stop``: dừng quy trình ở đây, không xếp bước sau.
    """

    asset_id: int | None = None
    project_id: int | None = None
    payload: dict = field(default_factory=dict)
    stop: bool = False
    note: str = ""


class StageError(Exception):
    """Lỗi có chủ đích. ``retryable=False`` → không thử lại (file không có, spec sai…)."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable
