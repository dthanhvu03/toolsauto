"""Danh sách nhạc trong xe (PLAN-127): bài tự sinh + file anh thả vào thư mục.

- Bài tự sinh («gen:N»): overlay tự chơi bằng Web Audio (ngũ cung, đàn tranh / sáo / trống / mõ) — nhạc của mình, không
  vướng bản quyền khi phát trên TikTok LIVE.
- File của anh: mp3 / ogg / m4a / wav trong `storage/media/xe_tet/music/` (anh tự chịu trách nhiệm quyền dùng). Tải lên
  ngay trên /control (hoặc chép thẳng vào thư mục) là có trong danh sách, không cần khởi động lại server.
"""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# XE_TET_MUSIC_DIR: máy chủ thử (8811) dùng thư mục riêng — tải lên / xoá thử không đụng nhạc của anh
MUSIC_DIR = Path(os.getenv("XE_TET_MUSIC_DIR") or ROOT / "storage" / "media" / "xe_tet" / "music")
EXTS = {".mp3", ".ogg", ".m4a", ".wav"}
MAX_BYTES = 200 * 1024 * 1024  # một file tối đa 200 MB: đủ cho mix nhạc dài / WAV (ghi thẳng xuống đĩa, không giữ RAM)
_UNSAFE = re.compile(r"[^\w\-. ()]+")  # giữ chữ (kể cả tiếng Việt), số, - . khoảng trắng, ngoặc

# Thứ tự = số bài trong overlay (src/music.ts → PRESETS); thêm bài thì thêm cả hai chỗ.
GENERATED = (
    "Xuân về trên phố",
    "Đàn tranh mùa xuân",
    "Sáo trúc đồng quê",
    "Trống hội làng",
    "Đường xa về nhà",
    "Giao thừa bên bếp lửa",
)

_cache: tuple[float, list[dict]] = (-1.0, [])


def upload_target(raw: str) -> Path:
    """Chỗ lưu bài tải lên: bỏ đường dẫn / ký tự lạ (không thoát khỏi thư mục), đuôi phải là nhạc, trùng tên thì thêm (2)."""
    name = Path(raw.replace("\\", "/")).name
    ext = Path(name).suffix.lower()
    if ext not in EXTS:
        raise ValueError(f"Chỉ nhận file nhạc {', '.join(sorted(EXTS))}")
    stem = _UNSAFE.sub("", Path(name).stem).strip(" .")[:80] or "bai-nhac"
    target, n = MUSIC_DIR / f"{stem}{ext}", 2
    while target.exists():
        target, n = MUSIC_DIR / f"{stem} ({n}){ext}", n + 1
    return target


def remove(name: str) -> None:
    """Xoá một bài của anh (chỉ file nhạc nằm ngay trong thư mục nhạc)."""
    path = MUSIC_DIR / Path(name).name
    if path.suffix.lower() not in EXTS or not path.is_file():
        raise FileNotFoundError(name)
    path.unlink()


def tracks() -> list[dict]:
    """[{id, title, url?}] — bài tự sinh trước, rồi file theo tên. Quét lại thư mục khi nó đổi (so mtime)."""
    global _cache
    try:
        stamp = MUSIC_DIR.stat().st_mtime
    except FileNotFoundError:
        stamp = 0.0
    if stamp != _cache[0]:
        files = sorted(p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in EXTS) if stamp else []
        _cache = (stamp, [{"id": f"gen:{i}", "title": title} for i, title in enumerate(GENERATED)]
                  + [{"id": f"file:{p.name}", "title": p.stem.replace("_", " "), "url": f"/music/{p.name}"} for p in files])
    return _cache[1]
