"""
Runtime config for reup anti-dupe presets + brand intro (no DB migration).
File: storage/db/config/reup_presets.json
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

PRESETS = ("safe", "aggressive", "reels_short")
DEFAULT_CONFIG: dict[str, Any] = {
    "default_preset": "safe",
    "page_presets": {},  # page_url -> preset
    "niche_presets": {},  # niche keyword (lower) -> preset
    "brand_logo_enabled": False,
    "brand_logo_path": "",  # absolute or relative to project
    "audio_head_trim_sec": 0.15,  # Phase C micro-trim
    "ab_variants": ["safe", "aggressive"],  # rotate when no page/niche match
    # Brand intro (PLAN-044) — only use intros you own / have rights to
    "intro_enabled": False,
    "intro_max_sec": 3.0,
    # Soft join intro→body (0 = hard cut). Clamped in processor to ≤0.5s.
    "intro_fade_sec": 0.28,
    # cover = crop center to WxH (ít viền); contain = letterbox
    "intro_scale_mode": "cover",
    "intro_default": "",  # path or dir under storage/media/intros/
    "page_intros": {},  # page_url substring -> path or dir
    "niche_intros": {},  # niche keyword (lower) -> path or dir
    "account_intros": {},  # account_id str -> path or dir
}

_PAGE_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _path() -> Path:
    from app import config

    config.RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return config.RUNTIME_CONFIG_DIR / "reup_presets.json"


def load_reup_config() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(DEFAULT_CONFIG)
        out = dict(DEFAULT_CONFIG)
        out.update(data)
        return out
    except Exception as e:
        logger.warning("[reup_config] load failed: %s", e)
        return dict(DEFAULT_CONFIG)


def save_reup_config(data: dict[str, Any]) -> None:
    p = _path()
    payload = {**DEFAULT_CONFIG, **(data or {})}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_preset(name: str | None) -> str:
    key = (name or "").strip().lower()
    return key if key in PRESETS else "safe"


def resolve_preset(
    *,
    page_url: str | None = None,
    niches: list[str] | None = None,
    explicit: str | None = None,
    material_id: int | None = None,
) -> str:
    """Resolve anti-dupe preset: explicit > page > niche > A/B rotate > default."""
    cfg = load_reup_config()
    if explicit:
        return normalize_preset(explicit)

    page = (page_url or "").strip()
    page_map = cfg.get("page_presets") or {}
    if page and isinstance(page_map, dict):
        for key, val in page_map.items():
            if not key:
                continue
            if page == key or key in page or page in key:
                return normalize_preset(str(val))

    niche_map = cfg.get("niche_presets") or {}
    if niches and isinstance(niche_map, dict):
        for niche in niches:
            n = (niche or "").strip().lower()
            if n and n in niche_map:
                return normalize_preset(str(niche_map[n]))

    variants = cfg.get("ab_variants") or ["safe", "aggressive"]
    variants = [normalize_preset(v) for v in variants if v]
    if variants and material_id is not None:
        return variants[int(material_id) % len(variants)]

    return normalize_preset(cfg.get("default_preset"))


def _project_root() -> Path:
    from app import config

    return Path(config.BASE_DIR)


def _resolve_media_ref(ref: str | None) -> Optional[str]:
    """Resolve path or directory to an existing .mp4/.mov file."""
    raw = (ref or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = _project_root() / p
    try:
        p = p.resolve()
    except OSError:
        return None
    if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}:
        return str(p)
    if p.is_dir():
        candidates = sorted(
            [
                f
                for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}
            ],
            key=lambda f: f.name.lower(),
        )
        if candidates:
            return str(candidates[0])
    return None


def page_intro_slug(page_url: str | None) -> str:
    """facebook.com/kids0810 → kids0810"""
    page = (page_url or "").strip().rstrip("/")
    if not page:
        return ""
    tail = page.split("/")[-1] or ""
    if "?" in tail:
        tail = tail.split("?", 1)[0]
    return _PAGE_SLUG_RE.sub("_", tail).strip("._")[:80]


def resolve_intro_path(
    *,
    page_url: str | None = None,
    niches: list[str] | None = None,
    account_id: int | None = None,
    explicit: str | None = None,
) -> Optional[str]:
    """
    Resolve brand intro clip: explicit > page > niche > account > default.
    Returns absolute path or None (skip intro).
    """
    from app import config

    cfg = load_reup_config()
    if not cfg.get("intro_enabled"):
        if explicit:
            return _resolve_media_ref(explicit)
        return None

    if explicit:
        hit = _resolve_media_ref(explicit)
        if hit:
            return hit

    page = (page_url or "").strip()
    page_map = cfg.get("page_intros") or {}
    if page and isinstance(page_map, dict):
        for key, val in page_map.items():
            if not key:
                continue
            if page == key or key in page or page in key:
                hit = _resolve_media_ref(str(val))
                if hit:
                    return hit
        slug = page_intro_slug(page)
        if slug:
            hit = _resolve_media_ref(str(config.STORAGE_INTROS_DIR / "by_page" / slug))
            if hit:
                return hit

    niche_map = cfg.get("niche_intros") or {}
    if niches and isinstance(niche_map, dict):
        for niche in niches:
            n = (niche or "").strip().lower()
            if n and n in niche_map:
                hit = _resolve_media_ref(str(niche_map[n]))
                if hit:
                    return hit
            if n:
                slug = _PAGE_SLUG_RE.sub("_", n).strip("._")
                hit = _resolve_media_ref(str(config.STORAGE_INTROS_DIR / "by_niche" / slug))
                if hit:
                    return hit

    if account_id is not None:
        acc_map = cfg.get("account_intros") or {}
        if isinstance(acc_map, dict):
            key = str(account_id)
            if key in acc_map:
                hit = _resolve_media_ref(str(acc_map[key]))
                if hit:
                    return hit
        hit = _resolve_media_ref(str(config.STORAGE_INTROS_DIR / "by_account" / str(account_id)))
        if hit:
            return hit

    return _resolve_media_ref(str(cfg.get("intro_default") or ""))
