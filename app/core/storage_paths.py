"""Resolve persisted media paths across legacy and storage/ layouts."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_media_path(raw: str | None) -> str:
    if not raw:
        return ""
    p = Path(raw)
    if p.is_file():
        return str(p.resolve())

    from app import config

    norm = raw.replace("\\", "/")
    prefixes: list[tuple[str, Path]] = [
        ("reup_videos/", config.REUP_DIR),
        ("storage/media/reup/", config.REUP_DIR),
        ("content/", config.CONTENT_DIR),
        ("storage/media/content/", config.CONTENT_DIR),
        ("thumbnails/", config.THUMB_DIR),
        ("storage/media/thumbs/", config.THUMB_DIR),
        ("storage/media/threads/", config.THREADS_MEDIA_DIR),
    ]
    for prefix, base in prefixes:
        if prefix not in norm:
            continue
        suffix = norm.split(prefix, 1)[1]
        candidate = base / suffix.replace("/", os.sep)
        if candidate.is_file():
            return str(candidate.resolve())
    return raw
