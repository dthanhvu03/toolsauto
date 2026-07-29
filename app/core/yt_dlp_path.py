"""Resolve yt-dlp binary so subprocess works when venv is not on PATH (PM2 / Windows)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def yt_dlp_binary() -> str | list[str]:
    """Return a subprocess argv head: path string or ``[python, -m, yt_dlp]``.

    Order: PATH → venv Scripts/bin next to ``sys.executable`` → ``python -m yt_dlp``.
    """
    found = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if found:
        return found

    bin_dir = Path(sys.executable).parent
    for name in ("yt-dlp.exe", "yt-dlp", "yt_dlp.exe"):
        candidate = bin_dir / name
        if candidate.is_file():
            return str(candidate)

    # Linux layout if somehow used
    linux_bin = bin_dir.parent / "bin" / "yt-dlp"
    if linux_bin.is_file():
        return str(linux_bin)

    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return "yt-dlp"
    return [sys.executable, "-m", "yt_dlp"]


def yt_dlp_cmd(*args: str) -> list[str]:
    """Build full argv for yt-dlp with optional trailing args."""
    head = yt_dlp_binary()
    if isinstance(head, list):
        return [*head, *args]
    return [head, *args]
