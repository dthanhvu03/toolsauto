"""
Runtime config for reup anti-dupe presets (no DB migration).
File: storage/db/config/reup_presets.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

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
}


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
