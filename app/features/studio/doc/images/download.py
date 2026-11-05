"""Tải một ảnh gợi ý về máy: giới hạn dung lượng, chỉ nhận ảnh jpg/png/webp (PLAN-157)."""
from __future__ import annotations

from pathlib import Path

import httpx

from app.features.studio.doc.config import DocConfig

CONTENT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class DownloadError(ValueError):
    """Thông điệp đưa thẳng cho người dùng."""


def fetch(http: httpx.Client, url: str, dest_stem: Path, cfg: DocConfig) -> Path:
    """Tải ``url`` về ``dest_stem`` + đuôi theo content-type. Quá ``image_max_mb`` hoặc không phải ảnh → ``DownloadError``."""
    limit = int(cfg.image_max_mb) * 1024 * 1024
    try:
        with http.stream("GET", url) as r:
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            suffix = CONTENT_TYPES.get(ctype)
            if suffix is None:
                raise DownloadError(f"không phải ảnh jpg/png/webp ({ctype or 'không rõ'})")
            if int(r.headers.get("content-length") or 0) > limit:
                raise DownloadError(f"ảnh lớn hơn {cfg.image_max_mb} MB")
            dest = dest_stem.with_suffix(suffix)
            size = 0
            with dest.open("wb") as out:
                for chunk in r.iter_bytes(1024 * 256):
                    size += len(chunk)
                    if size > limit:
                        out.close()
                        dest.unlink(missing_ok=True)
                        raise DownloadError(f"ảnh lớn hơn {cfg.image_max_mb} MB")
                    out.write(chunk)
    except httpx.HTTPError as exc:
        raise DownloadError(f"không tải được ảnh: {type(exc).__name__}") from exc
    if size == 0:
        dest.unlink(missing_ok=True)
        raise DownloadError("ảnh rỗng")
    return dest
