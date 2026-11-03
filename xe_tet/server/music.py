"""Danh sách nhạc trong xe (PLAN-127): file anh thả vào thư mục.

- File của anh: mp3 / ogg / m4a / wav trong `storage/media/xe_tet/music/` (anh tự chịu trách nhiệm quyền dùng). Tải lên
  ngay trên /control (hoặc chép thẳng vào thư mục) là có trong danh sách, không cần khởi động lại server.
"""

import contextlib
import os
import re
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# XE_TET_MUSIC_DIR: máy chủ thử (8811) dùng thư mục riêng — tải lên / xoá thử không đụng nhạc của anh
MUSIC_DIR = Path(os.getenv("XE_TET_MUSIC_DIR") or ROOT / "storage" / "media" / "xe_tet" / "music")
EXTS = {".mp3", ".ogg", ".m4a", ".wav"}
MAX_BYTES = 200 * 1024 * 1024  # một file tối đa 200 MB: đủ cho mix nhạc dài / WAV (ghi thẳng xuống đĩa, không giữ RAM)
_UNSAFE = re.compile(r"[^\w\-. ()]+")  # giữ chữ (kể cả tiếng Việt), số, - . khoảng trắng, ngoặc

GENERATED: tuple[str, ...] = ()

GENERATED_SECONDS = 150.0  # bài tự sinh lặp vô hạn: coi 2,5 phút là hết bài để tự qua bài
UNKNOWN_SECONDS = 180.0  # file không đo được độ dài (ffprobe lỗi): coi như 3 phút

_cache: tuple[float, list[dict]] = (-1.0, [])
_lengths: dict[tuple[str, float], float] = {}  # (tên file, mtime) → giây — đo một lần
_measuring: set[str] = set()  # file đang đo ở luồng riêng


def _key(path: Path) -> tuple[str, float]:
    return path.name, path.stat().st_mtime


def _measure(paths: list[Path]) -> None:
    """Đo độ dài ở luồng riêng (ffprobe tới 20 giây / file — chạy trong vòng game là đứng cả game), xong thì quét lại."""
    global _cache
    for path in paths:
        with contextlib.suppress(OSError):
            length_of(path)
        _measuring.discard(path.name)
    _cache = (-1.0, _cache[1])


def length_of(path: Path) -> float:
    """Độ dài bài (giây) bằng ffprobe; đo một lần / file, lỗi thì coi như UNKNOWN_SECONDS."""
    key = _key(path)
    if key not in _lengths:
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                  str(path)], capture_output=True, text=True, timeout=20).stdout.strip()
            _lengths[key] = float(out) if out and float(out) > 1 else UNKNOWN_SECONDS
        except (OSError, ValueError, subprocess.TimeoutExpired):
            _lengths[key] = UNKNOWN_SECONDS
    return _lengths[key]


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
    """[{id, title, seconds, url?}] — bài tự sinh trước, rồi file theo tên. Quét lại thư mục khi nó đổi (so mtime).
    Không bao giờ chạy ffprobe ở đây (gọi mỗi nhịp game): bài chưa đo tạm tính UNKNOWN_SECONDS, đo xong tự cập nhật."""
    global _cache
    try:
        stamp = MUSIC_DIR.stat().st_mtime
    except FileNotFoundError:
        stamp = 0.0
    if stamp != _cache[0]:
        files = sorted(p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in EXTS) if stamp else []
        todo = [p for p in files if _key(p) not in _lengths and p.name not in _measuring]
        if todo:
            _measuring.update(p.name for p in todo)
            threading.Thread(target=_measure, args=(todo,), daemon=True).start()
        _cache = (stamp, [{"id": f"gen:{i}", "title": title, "seconds": GENERATED_SECONDS} for i, title in enumerate(GENERATED)]
                  + [{"id": f"file:{p.name}", "title": p.stem.replace("_", " "), "url": f"/music/{p.name}",
                      "seconds": round(_lengths.get(_key(p), UNKNOWN_SECONDS), 1)} for p in files])
    return _cache[1]
