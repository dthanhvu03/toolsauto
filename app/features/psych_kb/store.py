"""Đọc kho tâm lý khách (PLAN-170) từ các file .md.

Kho gốc: ``app/features/psych_kb/kb/`` (theo git). Chủ bot sửa: chép file sang ``storage/db/config/psych_kb/`` — cùng tên
thì đè bản gốc, tên mới thì thêm. File bắt đầu bằng «_» (vd ``_nguon.md``) chỉ để đọc, không nạp.

Mỗi mục::

    ## <slug> — <Tiêu đề>
    Dấu hiệu: ...
    Vì sao: ...
    Nên: ...
    Tránh: ...
    Ví dụ: ...
    Dùng cho: threads, bot | all
    Nguồn: ...

Nạp lại khi file đổi (so mtime) — sửa kho có hiệu lực ở lần gọi sau, không cần restart.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent / "kb"
OVERRIDE_DIR = Path(__file__).resolve().parents[3] / "storage" / "db" / "config" / "psych_kb"

FIELDS = {
    "dấu hiệu": "signs",
    "vì sao": "why",
    "nên": "do",
    "tránh": "avoid",
    "ví dụ": "example",
    "dùng cho": "use_for",
    "nguồn": "source",
}
ALWAYS_USE = "all"
_HEADING = re.compile(r"^##\s+([a-z0-9-]+)\s*[—–-]\s*(.+?)\s*$")
_FIELD = re.compile(r"^([^:]{2,12}):\s*(.*)$")


@dataclass(frozen=True)
class Entry:
    id: str  # «<file>/<slug>», vd niem-tin/so-link-la
    title: str
    topic: str  # tiêu đề «# …» của file
    signs: str = ""
    why: str = ""
    do: str = ""
    avoid: str = ""
    example: str = ""
    source: str = ""
    use_for: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def always(self) -> bool:
        return ALWAYS_USE in self.use_for

    def fits(self, use_for: Optional[str]) -> bool:
        return use_for is None or self.always or use_for in self.use_for


def parse(text: str, stem: str) -> List[Entry]:
    topic, out = stem, []
    current: Optional[dict] = None
    last_key: Optional[str] = None

    def flush() -> None:
        if current is not None:
            uses = tuple(u.strip().lower() for u in current.pop("use_for", "").split(",") if u.strip())
            out.append(Entry(use_for=uses or ("threads", "bot"), topic=topic, **current))

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("# ") and current is None:
            topic = line[2:].strip()
            continue
        head = _HEADING.match(line)
        if head:
            flush()
            current, last_key = {"id": f"{stem}/{head.group(1)}", "title": head.group(2)}, None
            continue
        if current is None or not line.strip():
            continue
        m = _FIELD.match(line.strip())
        key = FIELDS.get(m.group(1).strip().lower()) if m else None
        if key:
            current[key], last_key = m.group(2).strip(), key
        elif last_key:  # dòng nối tiếp của trường trước
            current[last_key] = f"{current[last_key]} {line.strip()}".strip()
    flush()
    return out


class KnowledgeBase:
    """Kho đọc từ đĩa, nạp lại khi mtime / danh sách file đổi. An toàn khi nhiều luồng gọi."""

    def __init__(self, base_dir: Path = BASE_DIR, override_dir: Optional[Path] = OVERRIDE_DIR):
        self.base_dir, self.override_dir = base_dir, override_dir
        self._lock = threading.Lock()
        self._stamp: Tuple = ()
        self._entries: List[Entry] = []

    def _files(self) -> Dict[str, Path]:
        files: Dict[str, Path] = {}
        for folder in (self.base_dir, self.override_dir):
            if folder and folder.is_dir():
                for path in sorted(folder.glob("*.md")):
                    if not path.name.startswith("_"):
                        files[path.stem] = path  # override cùng tên đè bản gốc
        return files

    def entries(self) -> List[Entry]:
        files = self._files()
        stamp = tuple((k, str(p), p.stat().st_mtime_ns) for k, p in sorted(files.items()))
        with self._lock:
            if stamp != self._stamp:
                loaded: List[Entry] = []
                for stem, path in sorted(files.items()):
                    loaded.extend(parse(path.read_text(encoding="utf-8"), stem))
                self._entries, self._stamp = loaded, stamp
            return list(self._entries)

    def topics(self) -> Dict[str, List[Entry]]:
        out: Dict[str, List[Entry]] = {}
        for e in self.entries():
            out.setdefault(e.topic, []).append(e)
        return out


default_kb = KnowledgeBase()
