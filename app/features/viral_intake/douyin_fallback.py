"""Tải Douyin khi yt-dlp Fresh cookies / timeout trên WSL.

yt-dlp 2026.08 gọi aweme/detail (chữ ký Argus) nên cookie Chrome trên WSL không đủ.
Chrome Windows headed lấy ``video.currentSrc`` (CDN đã ký) rồi Python tải file.
"""
from __future__ import annotations

import json
import logging
import os
import random
import shutil
import subprocess
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_SKIP_WIN_USERS = {"Public", "Default", "Default User", "All Users", "desktop.ini"}
_MIN_BYTES = 80_000
_SCRIPT_NAME = "douyin_chrome_src.ps1"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)


def is_real_douyin_cdn_url(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http"):
        return False
    if "uuu_" in u or "douyinstatic.com/obj/douyin-pc-web/" in u:
        return False
    return any(
        token in u
        for token in (
            "mime_type=video",
            "zjcdn.com",
            "douyinvod",
            "bytevod",
            "tos-cn-ve",
            "/aweme/v1/play",
        )
    )


def _win_temp() -> Path | None:
    root = Path("/mnt/c/Users")
    if not root.is_dir():
        return None
    try:
        children = list(root.iterdir())
    except OSError:
        return None
    for child in children:
        if child.name in _SKIP_WIN_USERS or not child.is_dir():
            continue
        temp = child / "AppData" / "Local" / "Temp"
        if temp.is_dir():
            return temp
    return None


def _windows_script() -> str | None:
    src = Path(__file__).with_name(_SCRIPT_NAME)
    if not src.is_file():
        return None
    dest_dir = _win_temp()
    if dest_dir is None:
        return None
    dest = dest_dir / "toolsauto-dy-get-src.ps1"
    dest.write_bytes(src.read_bytes())
    user = dest_dir.parent.parent.parent.name
    return f"C:\\Users\\{user}\\AppData\\Local\\Temp\\toolsauto-dy-get-src.ps1"


def _powershell() -> str | None:
    return shutil.which("powershell.exe")


def _capture_src(page_url: str) -> dict:
    ps = _powershell()
    script = _windows_script()
    if not ps or not script:
        return {"ok": False, "error": "no_windows_chrome_helper"}
    port = random.randint(19100, 19800)
    cmd = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        script,
        "-VideoUrl",
        page_url,
        "-Port",
        str(port),
        "-WaitSec",
        "22",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=55)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "chrome_helper_timeout"}
    raw = (r.stdout or "").strip().splitlines()
    last = next((ln for ln in reversed(raw) if ln.strip().startswith("{")), "")
    if not last:
        err = (r.stderr or r.stdout or "empty")[:180]
        return {"ok": False, "error": err}
    try:
        data = json.loads(last)
    except json.JSONDecodeError:
        return {"ok": False, "error": last[:180]}
    if not data.get("ok") or not is_real_douyin_cdn_url(str(data.get("src") or "")):
        return {"ok": False, "error": data.get("error") or "placeholder_or_no_src"}
    return data


def _looks_like_mp4(path: str) -> bool:
    try:
        size = os.path.getsize(path)
        if size < _MIN_BYTES:
            return False
        with open(path, "rb") as fh:
            head = fh.read(64)
        return b"ftyp" in head
    except OSError:
        return False


def download_douyin_via_chrome(url: str, output_path: str) -> bool:
    """Mở Chrome Windows, lấy CDN URL, tải mp4 vào ``output_path``."""
    captured = _capture_src(url)
    src = str(captured.get("src") or "")
    if not captured.get("ok") or not src:
        logger.warning("[VIRAL] Douyin Chrome helper failed: %s", captured.get("error"))
        return False
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    try:
        resp = requests.get(
            src,
            stream=True,
            timeout=60,
            headers={"User-Agent": _UA, "Referer": "https://www.douyin.com/"},
        )
        if resp.status_code != 200:
            logger.warning("[VIRAL] Douyin CDN HTTP %s", resp.status_code)
            return False
        tmp = output_path + ".part"
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    fh.write(chunk)
        if not _looks_like_mp4(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
            logger.warning("[VIRAL] Douyin CDN file is not mp4")
            return False
        os.replace(tmp, output_path)
        logger.info("[VIRAL] Douyin Chrome fallback saved %s", output_path)
        return True
    except Exception as exc:
        logger.error("[VIRAL] Douyin Chrome download failed: %s", exc)
        return False
