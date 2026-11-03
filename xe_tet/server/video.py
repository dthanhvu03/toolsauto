"""Video bảng quảng cáo bên đường (anh 03/11): anh tải video nổi bật lên /control, xe đang chạy dừng lại xem rồi chạy tiếp.

- File mp4 / webm trong `storage/media/xe_tet/videos/` (anh tự chịu trách nhiệm quyền dùng). Tải lên trên /control hoặc chép
  thẳng vào thư mục. Độ dài đo bằng ffprobe ở luồng riêng (như nhạc).
"""

import os
import re
import threading
from pathlib import Path
from urllib.parse import quote

from . import music

ROOT = Path(__file__).resolve().parents[2]
# XE_TET_VIDEO_DIR: máy chủ thử (8811) dùng thư mục riêng
VIDEO_DIR = Path(os.getenv("XE_TET_VIDEO_DIR") or ROOT / "storage" / "media" / "xe_tet" / "videos")
EXTS = {".mp4", ".webm"}  # Chrome / OBS phát được; .mov (iPhone) thường là HEVC — đổi sang mp4 trước khi tải
MAX_BYTES = 500 * 1024 * 1024
_UNSAFE = re.compile(r"[^\w\-. ()]+")

_cache: tuple[float, list[dict]] = (-1.0, [])
_measuring: set[str] = set()


def _measure(paths: list[Path]) -> None:
    global _cache
    for path in paths:
        try:
            music.length_of(path)
        except OSError:
            pass
        _measuring.discard(path.name)
    _cache = (-1.0, _cache[1])


def upload_target(raw: str) -> Path:
    """Chỗ lưu video tải lên: bỏ đường dẫn / ký tự lạ, đuôi phải là video, trùng tên thì thêm (2)."""
    name = Path(raw.replace("\\", "/")).name
    ext = Path(name).suffix.lower()
    if ext not in EXTS:
        raise ValueError(f"Chỉ nhận video {', '.join(sorted(EXTS))} (video iPhone .mov: đổi sang mp4 trước)")
    stem = _UNSAFE.sub("", Path(name).stem).strip(" .")[:80] or "video"
    target, n = VIDEO_DIR / f"{stem}{ext}", 2
    while target.exists():
        target, n = VIDEO_DIR / f"{stem} ({n}){ext}", n + 1
    return target


def remove(name: str) -> None:
    path = VIDEO_DIR / Path(name).name
    if path.suffix.lower() not in EXTS or not path.is_file():
        raise FileNotFoundError(name)
    path.unlink()


def videos() -> list[dict]:
    """[{name, title, url, seconds}] theo tên file; quét lại khi thư mục đổi, đo độ dài ở luồng riêng (chưa đo: 30 giây)."""
    global _cache
    try:
        stamp = VIDEO_DIR.stat().st_mtime
    except FileNotFoundError:
        stamp = 0.0
    if stamp != _cache[0]:
        files = sorted(p for p in VIDEO_DIR.iterdir() if p.suffix.lower() in EXTS) if stamp else []
        todo = [p for p in files if music._key(p) not in music._lengths and p.name not in _measuring]
        if todo:
            _measuring.update(p.name for p in todo)
            threading.Thread(target=_measure, args=(todo,), daemon=True).start()
        _cache = (stamp, [{"name": p.name, "title": p.stem.replace("_", " "), "url": f"/videos/{quote(p.name)}",
                           "seconds": round(music._lengths.get(music._key(p), 30.0), 1)} for p in files])
    return _cache[1]
