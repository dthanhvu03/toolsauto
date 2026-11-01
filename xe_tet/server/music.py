"""Danh sách nhạc trong xe (PLAN-127): bài tự sinh + file anh thả vào thư mục.

- Bài tự sinh («gen:N»): overlay tự chơi bằng Web Audio (ngũ cung, đàn tranh / sáo / trống / mõ) — nhạc của mình, không
  vướng bản quyền khi phát trên TikTok LIVE.
- File của anh: mp3 / ogg / m4a / wav trong `storage/media/xe_tet/music/` (anh tự chịu trách nhiệm quyền dùng). Thả file
  vào là có trong danh sách, không cần khởi động lại server.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUSIC_DIR = ROOT / "storage" / "media" / "xe_tet" / "music"
EXTS = {".mp3", ".ogg", ".m4a", ".wav"}

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
