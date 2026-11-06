"""
Các nguồn ảnh internet (PLAN-157 / ADR-065). Mỗi hàm: ``(client, query, n, cfg) -> list[Candidate]``.

Chỉ đọc kết quả tìm (không tải ảnh). Lỗi mạng / HTTP ném ra cho ``search.py`` gom thành ghi chú.
Key đọc từ ``DocConfig.keys`` (Cài đặt vận hành → Studio — Audio→Doc).
"""
from __future__ import annotations

import html
import re
from typing import Callable

import httpx

from app.features.studio.doc.config import DocConfig
from app.features.studio.doc.images.licenses import normalize
from app.features.studio.doc.schema import Candidate

Provider = Callable[[httpx.Client, str, int, DocConfig], list[Candidate]]

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
PEXELS_API = "https://api.pexels.com/v1/search"
PIXABAY_API = "https://pixabay.com/api/"
GOOGLE_API = "https://www.googleapis.com/customsearch/v1"
PEXELS_LICENSE_URL = "https://www.pexels.com/license/"
PIXABAY_LICENSE_URL = "https://pixabay.com/service/license-summary/"


class MissingKey(RuntimeError):
    """Nguồn đang bật nhưng chưa nhập key."""


def _plain(value: object) -> str:
    """extmetadata của Wikimedia là HTML → chữ thường."""
    return html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()


def wikimedia(client: httpx.Client, query: str, n: int, cfg: DocConfig) -> list[Candidate]:
    r = client.get(WIKIMEDIA_API, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": n,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 480,
    })
    r.raise_for_status()
    pages = ((r.json().get("query") or {}).get("pages") or {}).values()
    out: list[Candidate] = []
    for page in sorted(pages, key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        if not str(info.get("mime") or "").startswith("image/"):
            continue
        lic_raw = _plain((meta.get("LicenseShortName") or {}).get("value"))
        out.append(Candidate(
            provider="wikimedia",
            image_url=info.get("url") or "",
            thumb_url=info.get("thumburl") or info.get("url") or "",
            source_page=info.get("descriptionurl") or "",
            title=_plain((meta.get("ObjectName") or {}).get("value")) or str(page.get("title") or ""),
            author=_plain((meta.get("Artist") or {}).get("value"))[:255],
            license=normalize(lic_raw),
            license_url=_plain((meta.get("LicenseUrl") or {}).get("value")),
            width=int(info.get("width") or 0),
            height=int(info.get("height") or 0),
        ))
    return out


def openverse(client: httpx.Client, query: str, n: int, cfg: DocConfig) -> list[Candidate]:
    # filter_dead=false: bỏ bước Openverse tự kiểm link chết từng ảnh (rất chậm, hay gây 504); ảnh hỏng thì lúc tải về báo lỗi.
    r = client.get(OPENVERSE_API, params={"q": query, "page_size": n, "filter_dead": "false"})
    r.raise_for_status()
    return [
        Candidate(
            provider="openverse",
            image_url=x.get("url") or "",
            thumb_url=x.get("thumbnail") or x.get("url") or "",
            source_page=x.get("foreign_landing_url") or "",
            title=str(x.get("title") or ""),
            author=str(x.get("creator") or "")[:255],
            license=normalize(x.get("license")),
            license_url=x.get("license_url") or "",
            width=int(x.get("width") or 0),
            height=int(x.get("height") or 0),
        )
        for x in r.json().get("results") or []
    ]


def pexels(client: httpx.Client, query: str, n: int, cfg: DocConfig) -> list[Candidate]:
    key = cfg.keys.get("pexels")
    if not key:
        raise MissingKey("chưa nhập Pexels API key")
    r = client.get(PEXELS_API, params={"query": query, "per_page": n}, headers={"Authorization": key})
    r.raise_for_status()
    return [
        Candidate(
            provider="pexels",
            image_url=(x.get("src") or {}).get("original") or "",
            thumb_url=(x.get("src") or {}).get("medium") or "",
            source_page=x.get("url") or "",
            title=str(x.get("alt") or ""),
            author=str(x.get("photographer") or "")[:255],
            license="pexels",
            license_url=PEXELS_LICENSE_URL,
            width=int(x.get("width") or 0),
            height=int(x.get("height") or 0),
        )
        for x in r.json().get("photos") or []
    ]


def pixabay(client: httpx.Client, query: str, n: int, cfg: DocConfig) -> list[Candidate]:
    key = cfg.keys.get("pixabay")
    if not key:
        raise MissingKey("chưa nhập Pixabay API key")
    r = client.get(PIXABAY_API, params={"key": key, "q": query, "image_type": "photo", "per_page": max(3, n)})
    r.raise_for_status()
    return [
        Candidate(
            provider="pixabay",
            image_url=x.get("largeImageURL") or x.get("webformatURL") or "",
            thumb_url=x.get("webformatURL") or "",
            source_page=x.get("pageURL") or "",
            title=str(x.get("tags") or ""),
            author=str(x.get("user") or "")[:255],
            license="pixabay",
            license_url=PIXABAY_LICENSE_URL,
            width=int(x.get("imageWidth") or 0),
            height=int(x.get("imageHeight") or 0),
        )
        for x in (r.json().get("hits") or [])[:n]
    ]


def google(client: httpx.Client, query: str, n: int, cfg: DocConfig) -> list[Candidate]:
    key, cx = cfg.keys.get("google"), cfg.keys.get("google_cx")
    if not key or not cx:
        raise MissingKey("chưa nhập Google API key / Search engine ID")
    r = client.get(GOOGLE_API, params={"key": key, "cx": cx, "q": query, "searchType": "image", "num": min(10, n)})
    r.raise_for_status()
    return [
        Candidate(
            provider="google",
            image_url=x.get("link") or "",
            thumb_url=(x.get("image") or {}).get("thumbnailLink") or "",
            source_page=(x.get("image") or {}).get("contextLink") or "",
            title=str(x.get("title") or ""),
            license="unknown",  # Google không cho biết giấy phép → anh tự kiểm
            width=int((x.get("image") or {}).get("width") or 0),
            height=int((x.get("image") or {}).get("height") or 0),
        )
        for x in r.json().get("items") or []
    ]


PROVIDERS: dict[str, Provider] = {
    "wikimedia": wikimedia,
    "openverse": openverse,
    "pexels": pexels,
    "pixabay": pixabay,
    "google": google,
}
