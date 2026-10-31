"""
Quét link TikTok (kênh ``@user`` hoặc 1 video) → danh sách video để chọn trên trang «Lấy từ TikTok» (PLAN-113).

Chỉ đọc metadata (``yt-dlp --flat-playlist --dump-json``), không tải. Tải là việc của bước ``fetch`` sau khi người
dùng chọn. Không import ``viral_intake`` (feature độc lập) — dùng thẳng ``app.core.yt_dlp_path``.
"""
from __future__ import annotations

import json
import logging
import subprocess
from urllib.parse import urlparse

from app.core.yt_dlp_path import impersonate_args, yt_dlp_cmd

logger = logging.getLogger(__name__)

MAX_SCAN = 30
SCAN_TIMEOUT_SEC = 120
_HOSTS = ("tiktok.com",)


class SourceError(ValueError):
    """Thông điệp đưa thẳng cho người dùng."""


def is_tiktok(url: str) -> bool:
    host = (urlparse(str(url or "").strip()).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _HOSTS)


def _thumb(data: dict) -> str | None:
    if data.get("thumbnail"):
        return str(data["thumbnail"])
    thumbs = [t.get("url") for t in data.get("thumbnails") or [] if isinstance(t, dict) and t.get("url")]
    return thumbs[-1] if thumbs else None


def parse(stdout: str) -> list[dict]:
    """Mỗi dòng JSON của yt-dlp → ``{id, url, title, views, duration, thumbnail}``; dòng hỏng / thiếu link bỏ qua."""
    items, seen = [], set()
    for line in (stdout or "").splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        url = data.get("webpage_url") or data.get("url") or data.get("original_url")
        if not url or url in seen:
            continue
        seen.add(url)
        items.append({
            "id": str(data.get("id") or url),
            "url": str(url),
            "title": str(data.get("title") or data.get("description") or "")[:300],
            "views": data.get("view_count"),
            "duration": data.get("duration"),
            "thumbnail": _thumb(data),
        })
    return items


def scan(url: str, limit: int = 10) -> list[dict]:
    url = str(url or "").strip()
    if not url.lower().startswith(("http://", "https://")) or not is_tiktok(url):
        raise SourceError("cần link TikTok (kênh tiktok.com/@… hoặc 1 video)")
    limit = max(1, min(MAX_SCAN, int(limit or 10)))
    cmd = yt_dlp_cmd(
        "--flat-playlist", "--dump-json", "--playlist-end", str(limit), "--no-warnings", *impersonate_args(), url,
    )
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SCAN_TIMEOUT_SEC)
    except subprocess.TimeoutExpired as exc:
        raise SourceError(f"quét quá {SCAN_TIMEOUT_SEC} giây — thử lại hoặc giảm số video") from exc
    items = parse(proc.stdout)[:limit]
    if items:
        return items
    err = (proc.stderr or "").lower()
    logger.warning("[STUDIO] quét %s hỏng: %s", url, (proc.stderr or "")[-300:])
    if "429" in err or "too many" in err or "rate limit" in err:
        raise SourceError("TikTok đang chặn vì quét nhiều (429) — thử lại sau ít phút")
    if "private" in err or "login" in err:
        raise SourceError("kênh / video riêng tư hoặc cần đăng nhập")
    raise SourceError("không đọc được video nào từ link này (kênh trống, link sai, hoặc TikTok đổi cách trả dữ liệu)")
