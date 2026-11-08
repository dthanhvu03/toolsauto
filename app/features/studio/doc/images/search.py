"""Tìm ảnh ở mọi nguồn đang bật, song song; một nguồn lỗi không làm hỏng nguồn khác (PLAN-157)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.features.studio.doc.config import DocConfig
from app.features.studio.doc.images.providers import PROVIDERS, MissingKey
from app.features.studio.doc.schema import Candidate

logger = logging.getLogger(__name__)

# Wikimedia chặn (403) User-Agent không có thông tin liên hệ — https://meta.wikimedia.org/wiki/User-Agent_policy.
# Dùng URL dự án (không dùng email cá nhân).
USER_AGENT = "ToolsAuto-Studio/1.0 (https://github.com/dthanhvu03/toolsauto; audio-doc image search) python-httpx"


def client(cfg: DocConfig) -> httpx.Client:
    return httpx.Client(
        timeout=float(cfg.search_timeout_sec), follow_redirects=True, headers={"User-Agent": USER_AGENT},
    )


def search(query: str, cfg: DocConfig, *, http: httpx.Client | None = None) -> tuple[list[Candidate], list[str]]:
    """``(ảnh gợi ý, ghi chú lỗi theo nguồn)``. Lọc ảnh hẹp hơn ``image_min_width`` (0 / không rõ kích thước thì giữ)."""
    query = query.strip()
    if not query:
        return [], ["chưa có từ khóa"]
    if not cfg.sources:
        return [], ["chưa bật nguồn ảnh nào (Cài đặt vận hành → Studio — Audio→Doc)"]
    own = http is None
    http = http or client(cfg)
    notes: list[str] = []

    def one(name: str) -> list[Candidate]:
        try:
            return PROVIDERS[name](http, query, cfg.candidates_per_source, cfg)
        except MissingKey as exc:
            notes.append(f"{name}: {exc}")
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("[Studio] doc image search %s lỗi: %s", name, exc)
            notes.append(f"{name}: lỗi {type(exc).__name__}")
        return []

    try:
        with ThreadPoolExecutor(max_workers=len(cfg.sources)) as pool:
            results = list(pool.map(one, cfg.sources))
    finally:
        if own:
            http.close()
    out: list[Candidate] = []
    seen: set[str] = set()
    for batch in results:
        for c in batch:
            if not c.image_url or c.image_url in seen:
                continue
            if c.width and c.width < cfg.image_min_width:
                continue
            seen.add(c.image_url)
            out.append(c)
    return out, notes
