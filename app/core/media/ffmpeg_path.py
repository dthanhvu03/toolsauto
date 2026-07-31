"""
Single place that answers "where is ffmpeg/ffprobe?".

On Windows a WinGet install puts the shims in %LOCALAPPDATA%\\Microsoft\\WinGet\\Links,
which is often missing from the PATH inherited by a service/PM2 process. Calling a
bare "ffmpeg" there raises WinError 2, so every caller must resolve first.
"""
from __future__ import annotations

import os
import shutil
from typing import Optional

FFMPEG_FALLBACK = "ffmpeg"
FFPROBE_FALLBACK = "ffprobe"


def winget_links_dir() -> Optional[str]:
    local = os.environ.get("LOCALAPPDATA") or ""
    if not local:
        return None
    path = os.path.join(local, "Microsoft", "WinGet", "Links")
    return path if os.path.isdir(path) else None


def ensure_ffmpeg_on_path() -> None:
    """If WinGet installed ffmpeg but the shell PATH is stale, prepend Links."""
    links = winget_links_dir()
    if not links:
        return
    path_env = os.environ.get("PATH") or ""
    if links.lower() in path_env.lower():
        return
    os.environ["PATH"] = links + os.pathsep + path_env


def _resolve(binary: str) -> Optional[str]:
    ensure_ffmpeg_on_path()
    found = shutil.which(binary)
    if found:
        return found
    links = winget_links_dir()
    if links:
        candidate = os.path.join(links, f"{binary}.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def resolve_ffmpeg() -> Optional[str]:
    """Absolute path to ffmpeg, or None when it is not installed."""
    return _resolve("ffmpeg")


def resolve_ffprobe() -> Optional[str]:
    """Absolute path to ffprobe, or None when it is not installed."""
    return _resolve("ffprobe")


def ffmpeg_bin() -> str:
    """Resolved ffmpeg, falling back to the bare name so errors stay readable."""
    return resolve_ffmpeg() or FFMPEG_FALLBACK


def ffprobe_bin() -> str:
    """Resolved ffprobe, falling back to the bare name so errors stay readable."""
    return resolve_ffprobe() or FFPROBE_FALLBACK


def ffmpeg_available() -> bool:
    return bool(resolve_ffprobe() or resolve_ffmpeg())
