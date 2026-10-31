"""
Thư mục của Studio: ``storage/media/studio/{assets,renders,work,inbox}``.

``inbox/`` giữ file vừa nhận (upload web, hộp thư Drive, reup) tới khi bước intake đưa vào kho.

``work/`` chỉ chứa file tạm của một lượt render — xoá trong ``finally`` ngay khi xong (RULES).
"""
from __future__ import annotations

from pathlib import Path

import app.config as config

ROOT: Path = config.STORAGE_MEDIA_DIR / "studio"


def _dir(name: str) -> Path:
    path = ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def assets_dir() -> Path:
    return _dir("assets")


def renders_dir() -> Path:
    return _dir("renders")


def work_dir() -> Path:
    return _dir("work")


def inbox_dir() -> Path:
    return _dir("inbox")


def luts_dir() -> Path:
    """Bảng màu .cube anh tự bỏ vào (không tạo thư mục — chưa có thì coi như không có LUT nào)."""
    return config.STORAGE_MEDIA_DIR / "luts"


def lut_names() -> list[str]:
    folder = luts_dir()
    return sorted(p.name for p in folder.glob("*.cube") if p.is_file()) if folder.is_dir() else []


def fonts_dir() -> Path:
    return Path(config.BASE_DIR) / "app" / "static" / "fonts"
