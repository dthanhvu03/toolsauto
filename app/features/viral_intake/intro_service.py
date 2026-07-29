"""
Brand intro upload / config helpers (PLAN-044 Phase 2 UI).
Files live under storage/media/intros/; maps in reup_presets.json.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from app import config
from app.features.viral_intake.reup_config import (
    load_reup_config,
    page_intro_slug,
    save_reup_config,
)

logger = logging.getLogger(__name__)

ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm"}
MAX_BYTES = 40 * 1024 * 1024  # 40MB
_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def intro_enabled() -> bool:
    return bool(load_reup_config().get("intro_enabled"))


def set_intro_enabled(enabled: bool) -> dict[str, Any]:
    cfg = load_reup_config()
    cfg["intro_enabled"] = bool(enabled)
    save_reup_config(cfg)
    return cfg


def _rel_storage(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(config.BASE_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def status_bundle(
    *,
    account_id: int,
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Snapshot for Target Pages UI (does not mutate enable flag)."""
    from app.features.viral_intake.reup_config import _resolve_media_ref

    cfg = load_reup_config()
    default_ref = str(cfg.get("intro_default") or "").strip()
    default_file = _resolve_media_ref(default_ref) if default_ref else None
    if not default_file:
        default_file = _resolve_media_ref(str(config.STORAGE_INTROS_DIR / "default"))

    account_file = _resolve_media_ref(str(config.STORAGE_INTROS_DIR / "by_account" / str(account_id)))
    acc_map = cfg.get("account_intros") or {}
    if not account_file and str(account_id) in acc_map:
        account_file = _resolve_media_ref(str(acc_map[str(account_id)]))

    page_map = cfg.get("page_intros") or {}
    page_rows = []
    for p in pages or []:
        url = (p.get("url") or "").strip()
        slug = page_intro_slug(url)
        resolved = None
        if url and isinstance(page_map, dict):
            for key, val in page_map.items():
                if key and (url == key or key in url or url in key):
                    resolved = _resolve_media_ref(str(val))
                    if resolved:
                        break
        if not resolved and slug:
            resolved = _resolve_media_ref(str(config.STORAGE_INTROS_DIR / "by_page" / slug))
        page_rows.append(
            {
                "url": url,
                "name": p.get("name") or url,
                "slug": slug,
                "resolved": resolved,
                "resolved_name": os.path.basename(resolved) if resolved else None,
            }
        )

    return {
        "intro_enabled": bool(cfg.get("intro_enabled")),
        "intro_max_sec": float(cfg.get("intro_max_sec") or 3),
        "default_file": default_file,
        "default_name": os.path.basename(default_file) if default_file else None,
        "account_file": account_file,
        "account_name": os.path.basename(account_file) if account_file else None,
        "pages": page_rows,
    }


def _safe_write_upload(dest_dir: Path, filename: str, data: bytes) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Chỉ nhận file video: {', '.join(sorted(ALLOWED_EXT))}")
    if len(data) > MAX_BYTES:
        raise ValueError(f"File quá lớn (max {MAX_BYTES // (1024*1024)}MB)")
    if len(data) < 1024:
        raise ValueError("File rỗng / quá nhỏ")
    dest = dest_dir / f"intro{ext}"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    # Remove other intro.* in folder to keep one canonical file
    for f in dest_dir.iterdir():
        if f.is_file() and f.name.startswith("intro") and f.resolve() != dest.resolve():
            try:
                f.unlink()
            except OSError:
                pass
    return dest


def save_intro_upload(
    *,
    scope: str,
    data: bytes,
    filename: str,
    account_id: int | None = None,
    page_url: str | None = None,
    niche: str | None = None,
) -> dict[str, Any]:
    """
    scope: default | account | page | niche
    Writes file + updates reup_presets.json maps.
    """
    scope = (scope or "").strip().lower()
    cfg = load_reup_config()

    if scope == "default":
        dest_dir = config.STORAGE_INTROS_DIR / "default"
        path = _safe_write_upload(dest_dir, filename, data)
        rel = _rel_storage(path)
        cfg["intro_default"] = rel
        cfg["intro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": rel, "abs": str(path)}

    if scope == "account":
        if account_id is None:
            raise ValueError("Thiếu account_id")
        dest_dir = config.STORAGE_INTROS_DIR / "by_account" / str(account_id)
        path = _safe_write_upload(dest_dir, filename, data)
        rel = _rel_storage(path)
        acc_map = dict(cfg.get("account_intros") or {})
        acc_map[str(account_id)] = rel
        cfg["account_intros"] = acc_map
        cfg["intro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": rel, "abs": str(path), "account_id": account_id}

    if scope == "page":
        url = (page_url or "").strip()
        if not url:
            raise ValueError("Thiếu page_url")
        slug = page_intro_slug(url) or "page"
        dest_dir = config.STORAGE_INTROS_DIR / "by_page" / slug
        path = _safe_write_upload(dest_dir, filename, data)
        rel = _rel_storage(path)
        page_map = dict(cfg.get("page_intros") or {})
        page_map[url] = rel
        cfg["page_intros"] = page_map
        cfg["intro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": rel, "abs": str(path), "page_url": url, "slug": slug}

    if scope == "niche":
        n = (niche or "").strip().lower()
        if not n:
            raise ValueError("Thiếu niche")
        slug = _SAFE.sub("_", n).strip("._") or "niche"
        dest_dir = config.STORAGE_INTROS_DIR / "by_niche" / slug
        path = _safe_write_upload(dest_dir, filename, data)
        rel = _rel_storage(path)
        niche_map = dict(cfg.get("niche_intros") or {})
        niche_map[n] = rel
        cfg["niche_intros"] = niche_map
        cfg["intro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": rel, "abs": str(path), "niche": n}

    raise ValueError("scope phải là default|account|page|niche")


def delete_intro(
    *,
    scope: str,
    account_id: int | None = None,
    page_url: str | None = None,
    niche: str | None = None,
) -> None:
    cfg = load_reup_config()
    scope = (scope or "").strip().lower()

    def _rm_dir(d: Path) -> None:
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)

    if scope == "default":
        _rm_dir(config.STORAGE_INTROS_DIR / "default")
        cfg["intro_default"] = ""
        save_reup_config(cfg)
        return
    if scope == "account" and account_id is not None:
        _rm_dir(config.STORAGE_INTROS_DIR / "by_account" / str(account_id))
        acc_map = dict(cfg.get("account_intros") or {})
        acc_map.pop(str(account_id), None)
        cfg["account_intros"] = acc_map
        save_reup_config(cfg)
        return
    if scope == "page":
        url = (page_url or "").strip()
        slug = page_intro_slug(url)
        if slug:
            _rm_dir(config.STORAGE_INTROS_DIR / "by_page" / slug)
        page_map = dict(cfg.get("page_intros") or {})
        page_map.pop(url, None)
        # Also remove keys that match url loosely
        for k in list(page_map.keys()):
            if url and (url in k or k in url):
                page_map.pop(k, None)
        cfg["page_intros"] = page_map
        save_reup_config(cfg)
        return
    if scope == "niche":
        n = (niche or "").strip().lower()
        slug = _SAFE.sub("_", n).strip("._")
        if slug:
            _rm_dir(config.STORAGE_INTROS_DIR / "by_niche" / slug)
        niche_map = dict(cfg.get("niche_intros") or {})
        niche_map.pop(n, None)
        cfg["niche_intros"] = niche_map
        save_reup_config(cfg)
        return
    raise ValueError("Không xóa được scope này")
