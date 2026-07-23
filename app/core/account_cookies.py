"""Parse browser-exported cookie JSON for Playwright context.add_cookies."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from app.config import FACEBOOK_HOST, INSTAGRAM_HOST

_FB_HOSTS = ("facebook.com", "fb.com", "m.facebook.com", "www.facebook.com")
_IG_HOSTS = ("instagram.com", "www.instagram.com")


def parse_cookie_json(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Chưa dán nội dung cookie JSON.")
    if '"value":"..."' in text.replace(" ", "") or '"value": "..."' in text:
        raise ValueError("Đang dùng JSON mẫu — hãy dán file export thật từ Cookie-Editor.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON không hợp lệ: {e}") from e

    if isinstance(data, dict):
        if isinstance(data.get("cookies"), list):
            data = data["cookies"]
        elif isinstance(data.get("data"), list):
            data = data["data"]
        else:
            raise ValueError("JSON phải là mảng cookie hoặc object có key 'cookies'.")
    if not isinstance(data, list):
        raise ValueError("JSON phải là mảng các object cookie.")
    return [c for c in data if isinstance(c, dict)]


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.lower()
    except Exception:
        return ""


def _same_site_for_playwright(value: Any) -> str | None:
    if value is None or value == "" or value == "unspecified":
        return "Lax"
    s = str(value).lower()
    if s in ("none", "no_restriction"):
        return "None"
    if s == "strict":
        return "Strict"
    if s == "lax":
        return "Lax"
    return "Lax"


def _expires_seconds(item: dict[str, Any]) -> float | None:
    exp = item.get("expires")
    if exp is None:
        exp = item.get("expirationDate")
    if exp is None:
        return None
    try:
        exp = float(exp)
    except (TypeError, ValueError):
        return None
    if exp <= 0:
        return None
    if exp > 1e12:
        exp = exp / 1000.0
    return exp


def _domain_matches_platform(domain: str, platform: str) -> bool:
    d = (domain or "").lower().lstrip(".")
    if platform == "instagram":
        return any(h in d for h in _IG_HOSTS)
    return any(h in d for h in _FB_HOSTS)


def cookies_for_playwright(items: list[dict[str, Any]], platform: str) -> list[dict[str, Any]]:
    platform = (platform or "facebook").lower()
    default_domain = urlparse(
        INSTAGRAM_HOST if platform == "instagram" else FACEBOOK_HOST
    ).hostname or ("instagram.com" if platform == "instagram" else "facebook.com")

    out: list[dict[str, Any]] = []
    for item in items:
        name = item.get("name")
        if name is None or item.get("value") is None:
            continue
        domain = (item.get("domain") or "").strip()
        if not domain:
            domain = _domain_from_url(str(item.get("url") or "")) or default_domain
        if not _domain_matches_platform(domain, platform):
            continue

        if not domain.startswith(".") and domain.count(".") >= 1:
            domain = f".{domain.lstrip('.')}"

        path = item.get("path") or "/"
        cookie: dict[str, Any] = {
            "name": str(name),
            "value": str(item.get("value")),
            "domain": domain,
            "path": path,
        }
        exp = _expires_seconds(item)
        if exp is not None:
            cookie["expires"] = exp
        if "httpOnly" in item:
            cookie["httpOnly"] = bool(item.get("httpOnly"))
        if "secure" in item:
            cookie["secure"] = bool(item.get("secure"))
        ss = _same_site_for_playwright(item.get("sameSite"))
        if ss:
            cookie["sameSite"] = ss
        out.append(cookie)

    # Dedupe by name+domain+path (last wins)
    dedup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for c in out:
        key = (c["name"], c["domain"], c["path"])
        dedup[key] = c
    return list(dedup.values())
