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
    # Max clips per intro pool (page/account/default/niche dir)
    "intro_pool_max": 8,
    # Brand outro (PLAN-045) — append after body
    "outro_enabled": False,
    "outro_max_sec": 2.5,
    "outro_fade_sec": 0.28,
    "outro_scale_mode": "cover",
    "outro_default": "",
    "page_outros": {},
    "niche_outros": {},
    "account_outros": {},
    # Hook text overlay on body (before intro) — first N seconds
    "hook_enabled": False,
    "hook_max_sec": 2.0,
    "hook_default_text": "",
    "page_hooks": {},  # page_url -> text
    "account_hooks": {},  # account_id str -> text
    "niche_hooks": {},  # niche -> text
    # Reels canvas normalize (opt-in): cover+crop → 1080×1920 + CRF sạch hơn
    "reels_1080_enabled": False,
    "reels_target_width": 1080,
    "reels_target_height": 1920,
    "reels_1080_crf": 23,
    "reels_1080_x264_preset": "veryfast",
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


_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}


def _list_media_files(path: Path) -> list[Path]:
    """List video files in a file-or-directory ref (sorted by name)."""
    if not path.exists():
        return []
    if path.is_file() and path.suffix.lower() in _VIDEO_EXT:
        # Pool = siblings in parent that look like intro/outro clips
        parent = path.parent
        if parent.is_dir():
            sibs = [
                f
                for f in parent.iterdir()
                if f.is_file() and f.suffix.lower() in _VIDEO_EXT
            ]
            if sibs:
                return sorted(sibs, key=lambda f: f.name.lower())
        return [path]
    if path.is_dir():
        return sorted(
            [
                f
                for f in path.iterdir()
                if f.is_file() and f.suffix.lower() in _VIDEO_EXT
            ],
            key=lambda f: f.name.lower(),
        )
    return []


def list_media_pool(ref: str | None) -> list[str]:
    """Absolute paths of all clips in a pool ref (file or dir)."""
    raw = (ref or "").strip()
    if not raw:
        return []
    p = Path(raw)
    if not p.is_absolute():
        p = _project_root() / p
    try:
        p = p.resolve()
    except OSError:
        return []
    return [str(f) for f in _list_media_files(p)]


def _resolve_media_ref(ref: str | None, *, randomize: bool = False) -> Optional[str]:
    """
    Resolve path or directory to an existing video file.
    randomize=True → uniform pick from pool (reup); False → first sorted (UI peek).
    """
    import random

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
    files = _list_media_files(p)
    if not files:
        return None
    if randomize and len(files) > 1:
        return str(random.choice(files))
    return str(files[0])


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
    Uniform random when pool has multiple files.
    """
    from app import config

    cfg = load_reup_config()

    def pick(ref: str | None) -> Optional[str]:
        return _resolve_media_ref(ref, randomize=True)

    if not cfg.get("intro_enabled"):
        if explicit:
            return pick(explicit)
        return None

    if explicit:
        hit = pick(explicit)
        if hit:
            return hit

    page = (page_url or "").strip()
    page_map = cfg.get("page_intros") or {}
    if page and isinstance(page_map, dict):
        for key, val in page_map.items():
            if not key:
                continue
            if page == key or key in page or page in key:
                hit = pick(str(val))
                if hit:
                    return hit
        slug = page_intro_slug(page)
        if slug:
            hit = pick(str(config.STORAGE_INTROS_DIR / "by_page" / slug))
            if hit:
                return hit

    niche_map = cfg.get("niche_intros") or {}
    if niches and isinstance(niche_map, dict):
        for niche in niches:
            n = (niche or "").strip().lower()
            if n and n in niche_map:
                hit = pick(str(niche_map[n]))
                if hit:
                    return hit
            if n:
                slug = _PAGE_SLUG_RE.sub("_", n).strip("._")
                hit = pick(str(config.STORAGE_INTROS_DIR / "by_niche" / slug))
                if hit:
                    return hit

    if account_id is not None:
        acc_map = cfg.get("account_intros") or {}
        if isinstance(acc_map, dict):
            key = str(account_id)
            if key in acc_map:
                hit = pick(str(acc_map[key]))
                if hit:
                    return hit
        hit = pick(str(config.STORAGE_INTROS_DIR / "by_account" / str(account_id)))
        if hit:
            return hit

    default_ref = str(cfg.get("intro_default") or "").strip()
    if default_ref:
        hit = pick(default_ref)
        if hit:
            return hit
    return pick(str(config.STORAGE_INTROS_DIR / "default"))


def resolve_outro_path(
    *,
    page_url: str | None = None,
    niches: list[str] | None = None,
    account_id: int | None = None,
    explicit: str | None = None,
) -> Optional[str]:
    """Resolve brand outro: explicit > page > niche > account > default (random pool)."""
    from app import config

    cfg = load_reup_config()

    def pick(ref: str | None) -> Optional[str]:
        return _resolve_media_ref(ref, randomize=True)

    if not cfg.get("outro_enabled"):
        if explicit:
            return pick(explicit)
        return None

    if explicit:
        hit = pick(explicit)
        if hit:
            return hit

    page = (page_url or "").strip()
    page_map = cfg.get("page_outros") or {}
    if page and isinstance(page_map, dict):
        for key, val in page_map.items():
            if not key:
                continue
            if page == key or key in page or page in key:
                hit = pick(str(val))
                if hit:
                    return hit
        slug = page_intro_slug(page)
        if slug:
            hit = pick(str(config.STORAGE_OUTROS_DIR / "by_page" / slug))
            if hit:
                return hit

    niche_map = cfg.get("niche_outros") or {}
    if niches and isinstance(niche_map, dict):
        for niche in niches:
            n = (niche or "").strip().lower()
            if n and n in niche_map:
                hit = pick(str(niche_map[n]))
                if hit:
                    return hit
            if n:
                slug = _PAGE_SLUG_RE.sub("_", n).strip("._")
                hit = pick(str(config.STORAGE_OUTROS_DIR / "by_niche" / slug))
                if hit:
                    return hit

    if account_id is not None:
        acc_map = cfg.get("account_outros") or {}
        if isinstance(acc_map, dict):
            key = str(account_id)
            if key in acc_map:
                hit = pick(str(acc_map[key]))
                if hit:
                    return hit
        hit = pick(str(config.STORAGE_OUTROS_DIR / "by_account" / str(account_id)))
        if hit:
            return hit

    default_ref = str(cfg.get("outro_default") or "").strip()
    if default_ref:
        hit = pick(default_ref)
        if hit:
            return hit
    return pick(str(config.STORAGE_OUTROS_DIR / "default"))


def resolve_hook_text(
    *,
    page_url: str | None = None,
    niches: list[str] | None = None,
    account_id: int | None = None,
    explicit: str | None = None,
) -> Optional[str]:
    """Resolve hook overlay text: explicit > page > niche > account > default."""
    cfg = load_reup_config()
    if not cfg.get("hook_enabled"):
        if explicit and str(explicit).strip():
            return str(explicit).strip()[:120]
        return None

    if explicit and str(explicit).strip():
        return str(explicit).strip()[:120]

    page = (page_url or "").strip()
    page_map = cfg.get("page_hooks") or {}
    if page and isinstance(page_map, dict):
        for key, val in page_map.items():
            if key and (page == key or key in page or page in key):
                t = str(val or "").strip()
                if t:
                    return t[:120]

    niche_map = cfg.get("niche_hooks") or {}
    if niches and isinstance(niche_map, dict):
        for niche in niches:
            n = (niche or "").strip().lower()
            if n and n in niche_map:
                t = str(niche_map[n] or "").strip()
                if t:
                    return t[:120]

    if account_id is not None:
        acc_map = cfg.get("account_hooks") or {}
        if isinstance(acc_map, dict):
            t = str(acc_map.get(str(account_id)) or "").strip()
            if t:
                return t[:120]

    t = str(cfg.get("hook_default_text") or "").strip()
    return t[:120] if t else None
