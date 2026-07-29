"""
Brand intro upload / config helpers (PLAN-044 Phase 2 UI).
Files live under storage/media/intros/; maps in reup_presets.json.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from app import config
from app.features.viral_intake.reup_config import (
    list_media_pool,
    load_reup_config,
    page_intro_slug,
    save_reup_config,
)

logger = logging.getLogger(__name__)

ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm"}
MAX_BYTES = 40 * 1024 * 1024  # 40MB
_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _pool_max() -> int:
    cfg = load_reup_config()
    try:
        n = int(cfg.get("intro_pool_max") or 8)
    except (TypeError, ValueError):
        n = 8
    return max(1, min(12, n))


def _pool_entries(paths: list[str]) -> list[dict[str, str]]:
    out = []
    for p in paths:
        try:
            rel = _rel_storage(Path(p))
        except Exception:
            rel = p
        out.append({"name": os.path.basename(p), "path": p, "rel": rel})
    return out


def intro_enabled() -> bool:
    return bool(load_reup_config().get("intro_enabled"))


def set_intro_enabled(enabled: bool) -> dict[str, Any]:
    cfg = load_reup_config()
    cfg["intro_enabled"] = bool(enabled)
    save_reup_config(cfg)
    return cfg


def set_outro_enabled(enabled: bool) -> dict[str, Any]:
    cfg = load_reup_config()
    cfg["outro_enabled"] = bool(enabled)
    save_reup_config(cfg)
    return cfg


def set_hook_enabled(enabled: bool) -> dict[str, Any]:
    cfg = load_reup_config()
    cfg["hook_enabled"] = bool(enabled)
    save_reup_config(cfg)
    return cfg


def set_reels_1080_enabled(enabled: bool) -> dict[str, Any]:
    cfg = load_reup_config()
    cfg["reels_1080_enabled"] = bool(enabled)
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
    pool_max = _pool_max()

    default_dir = str(config.STORAGE_INTROS_DIR / "default")
    default_ref = str(cfg.get("intro_default") or "").strip() or default_dir
    default_pool = list_media_pool(default_ref) or list_media_pool(default_dir)
    default_file = default_pool[0] if default_pool else None

    account_dir = str(config.STORAGE_INTROS_DIR / "by_account" / str(account_id))
    acc_map = cfg.get("account_intros") or {}
    account_ref = str(acc_map.get(str(account_id)) or account_dir)
    account_pool = list_media_pool(account_ref) or list_media_pool(account_dir)
    account_file = account_pool[0] if account_pool else None

    outro_default = _resolve_media_ref(str(cfg.get("outro_default") or "")) or _resolve_media_ref(
        str(config.STORAGE_OUTROS_DIR / "default")
    )
    outro_account = _resolve_media_ref(str(config.STORAGE_OUTROS_DIR / "by_account" / str(account_id)))
    outro_acc_map = cfg.get("account_outros") or {}
    if not outro_account and str(account_id) in (outro_acc_map or {}):
        outro_account = _resolve_media_ref(str(outro_acc_map[str(account_id)]))

    page_map = cfg.get("page_intros") or {}
    outro_page_map = cfg.get("page_outros") or {}
    page_hooks = cfg.get("page_hooks") or {}
    page_rows = []
    for p in pages or []:
        url = (p.get("url") or "").strip()
        slug = page_intro_slug(url)
        page_dir = str(config.STORAGE_INTROS_DIR / "by_page" / slug) if slug else ""
        pool: list[str] = []
        if url and isinstance(page_map, dict):
            for key, val in page_map.items():
                if key and (url == key or key in url or url in key):
                    pool = list_media_pool(str(val))
                    if pool:
                        break
        if not pool and page_dir:
            pool = list_media_pool(page_dir)
        resolved = pool[0] if pool else None

        outro_resolved = None
        if url and isinstance(outro_page_map, dict):
            for key, val in outro_page_map.items():
                if key and (url == key or key in url or url in key):
                    outro_resolved = _resolve_media_ref(str(val))
                    if outro_resolved:
                        break
        if not outro_resolved and slug:
            outro_resolved = _resolve_media_ref(str(config.STORAGE_OUTROS_DIR / "by_page" / slug))

        hook_text = ""
        if url and isinstance(page_hooks, dict):
            for key, val in page_hooks.items():
                if key and (url == key or key in url or url in key):
                    hook_text = str(val or "").strip()
                    if hook_text:
                        break

        page_rows.append(
            {
                "url": url,
                "name": p.get("name") or url,
                "slug": slug,
                "resolved": resolved,
                "resolved_name": os.path.basename(resolved) if resolved else None,
                "pool": _pool_entries(pool),
                "pool_count": len(pool),
                "outro_resolved": outro_resolved,
                "outro_name": os.path.basename(outro_resolved) if outro_resolved else None,
                "hook_text": hook_text,
            }
        )

    acc_hooks = cfg.get("account_hooks") or {}
    return {
        "intro_enabled": bool(cfg.get("intro_enabled")),
        "intro_max_sec": float(cfg.get("intro_max_sec") or 3),
        "intro_pool_max": pool_max,
        "default_file": default_file,
        "default_name": os.path.basename(default_file) if default_file else None,
        "default_pool": _pool_entries(default_pool),
        "default_pool_count": len(default_pool),
        "account_file": account_file,
        "account_name": os.path.basename(account_file) if account_file else None,
        "account_pool": _pool_entries(account_pool),
        "account_pool_count": len(account_pool),
        "outro_enabled": bool(cfg.get("outro_enabled")),
        "outro_max_sec": float(cfg.get("outro_max_sec") or 2.5),
        "outro_default_file": outro_default,
        "outro_default_name": os.path.basename(outro_default) if outro_default else None,
        "outro_account_file": outro_account,
        "outro_account_name": os.path.basename(outro_account) if outro_account else None,
        "hook_enabled": bool(cfg.get("hook_enabled")),
        "hook_max_sec": float(cfg.get("hook_max_sec") or 2),
        "hook_default_text": str(cfg.get("hook_default_text") or ""),
        "hook_account_text": str((acc_hooks or {}).get(str(account_id)) or ""),
        "reels_1080_enabled": bool(cfg.get("reels_1080_enabled")),
        "reels_target_width": int(cfg.get("reels_target_width") or 1080),
        "reels_target_height": int(cfg.get("reels_target_height") or 1920),
        "pages": page_rows,
    }


def _safe_write_upload_pool(dest_dir: Path, filename: str, data: bytes, stem: str = "intro") -> Path:
    """Append a new clip into dest_dir pool (does not wipe siblings)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Chỉ nhận file video: {', '.join(sorted(ALLOWED_EXT))}")
    if len(data) > MAX_BYTES:
        raise ValueError(f"File quá lớn (max {MAX_BYTES // (1024*1024)}MB)")
    if len(data) < 1024:
        raise ValueError("File rỗng / quá nhỏ")

    existing = [
        f for f in dest_dir.iterdir() if f.is_file() and f.suffix.lower() in ALLOWED_EXT
    ]
    limit = _pool_max()
    if len(existing) >= limit:
        raise ValueError(f"Pool đã đủ {limit} clip — xóa bớt rồi upload tiếp")

    dest = dest_dir / f"{stem}_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    return dest


def _safe_write_upload(dest_dir: Path, filename: str, data: bytes, stem: str = "intro") -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Chỉ nhận file video: {', '.join(sorted(ALLOWED_EXT))}")
    if len(data) > MAX_BYTES:
        raise ValueError(f"File quá lớn (max {MAX_BYTES // (1024*1024)}MB)")
    if len(data) < 1024:
        raise ValueError("File rỗng / quá nhỏ")
    dest = dest_dir / f"{stem}{ext}"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    for f in dest_dir.iterdir():
        if f.is_file() and f.name.startswith(stem) and f.resolve() != dest.resolve():
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
    Appends into pool dir + maps point to the directory.
    """
    scope = (scope or "").strip().lower()
    cfg = load_reup_config()

    if scope == "default":
        dest_dir = config.STORAGE_INTROS_DIR / "default"
        path = _safe_write_upload_pool(dest_dir, filename, data, stem="intro")
        rel = _rel_storage(dest_dir)
        cfg["intro_default"] = rel
        cfg["intro_enabled"] = True
        save_reup_config(cfg)
        return {
            "scope": scope,
            "path": _rel_storage(path),
            "pool_dir": rel,
            "pool_count": len(list_media_pool(str(dest_dir))),
        }

    if scope == "account":
        if account_id is None:
            raise ValueError("Thiếu account_id")
        dest_dir = config.STORAGE_INTROS_DIR / "by_account" / str(account_id)
        path = _safe_write_upload_pool(dest_dir, filename, data, stem="intro")
        rel = _rel_storage(dest_dir)
        acc_map = dict(cfg.get("account_intros") or {})
        acc_map[str(account_id)] = rel
        cfg["account_intros"] = acc_map
        cfg["intro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": _rel_storage(path), "pool_dir": rel, "account_id": account_id}

    if scope == "page":
        url = (page_url or "").strip()
        if not url:
            raise ValueError("Thiếu page_url")
        slug = page_intro_slug(url) or "page"
        dest_dir = config.STORAGE_INTROS_DIR / "by_page" / slug
        path = _safe_write_upload_pool(dest_dir, filename, data, stem="intro")
        rel = _rel_storage(dest_dir)
        page_map = dict(cfg.get("page_intros") or {})
        page_map[url] = rel
        cfg["page_intros"] = page_map
        cfg["intro_enabled"] = True
        save_reup_config(cfg)
        return {
            "scope": scope,
            "path": _rel_storage(path),
            "pool_dir": rel,
            "page_url": url,
            "slug": slug,
        }

    if scope == "niche":
        n = (niche or "").strip().lower()
        if not n:
            raise ValueError("Thiếu niche")
        slug = _SAFE.sub("_", n).strip("._") or "niche"
        dest_dir = config.STORAGE_INTROS_DIR / "by_niche" / slug
        path = _safe_write_upload_pool(dest_dir, filename, data, stem="intro")
        rel = _rel_storage(dest_dir)
        niche_map = dict(cfg.get("niche_intros") or {})
        niche_map[n] = rel
        cfg["niche_intros"] = niche_map
        cfg["intro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": _rel_storage(path), "pool_dir": rel, "niche": n}

    raise ValueError("scope phải là default|account|page|niche")


def delete_intro_file(*, rel_or_abs: str) -> None:
    """Delete one clip from an intro pool."""
    raw = (rel_or_abs or "").strip()
    if not raw:
        raise ValueError("Thiếu path file")
    p = Path(raw)
    if not p.is_absolute():
        p = config.BASE_DIR / p
    try:
        p = p.resolve()
    except OSError as e:
        raise ValueError(f"Path không hợp lệ: {e}") from e
    intros_root = str(config.STORAGE_INTROS_DIR.resolve())
    if not str(p).startswith(intros_root):
        raise ValueError("Chỉ xóa được file trong thư mục intros")
    if not p.is_file() or p.suffix.lower() not in ALLOWED_EXT:
        raise ValueError("File không tồn tại hoặc không phải video")
    p.unlink()


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


def save_outro_upload(
    *,
    scope: str,
    data: bytes,
    filename: str,
    account_id: int | None = None,
    page_url: str | None = None,
) -> dict[str, Any]:
    scope = (scope or "").strip().lower()
    cfg = load_reup_config()
    if scope == "default":
        path = _safe_write_upload(config.STORAGE_OUTROS_DIR / "default", filename, data, stem="outro")
        rel = _rel_storage(path)
        cfg["outro_default"] = rel
        cfg["outro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": rel}
    if scope == "account":
        if account_id is None:
            raise ValueError("Thiếu account_id")
        path = _safe_write_upload(
            config.STORAGE_OUTROS_DIR / "by_account" / str(account_id), filename, data, stem="outro"
        )
        rel = _rel_storage(path)
        m = dict(cfg.get("account_outros") or {})
        m[str(account_id)] = rel
        cfg["account_outros"] = m
        cfg["outro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": rel}
    if scope == "page":
        url = (page_url or "").strip()
        if not url:
            raise ValueError("Thiếu page_url")
        slug = page_intro_slug(url) or "page"
        path = _safe_write_upload(
            config.STORAGE_OUTROS_DIR / "by_page" / slug, filename, data, stem="outro"
        )
        rel = _rel_storage(path)
        m = dict(cfg.get("page_outros") or {})
        m[url] = rel
        cfg["page_outros"] = m
        cfg["outro_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "path": rel, "page_url": url}
    raise ValueError("scope outro: default|account|page")


def delete_outro(
    *,
    scope: str,
    account_id: int | None = None,
    page_url: str | None = None,
) -> None:
    cfg = load_reup_config()
    scope = (scope or "").strip().lower()

    def _rm_dir(d: Path) -> None:
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)

    if scope == "default":
        _rm_dir(config.STORAGE_OUTROS_DIR / "default")
        cfg["outro_default"] = ""
        save_reup_config(cfg)
        return
    if scope == "account" and account_id is not None:
        _rm_dir(config.STORAGE_OUTROS_DIR / "by_account" / str(account_id))
        m = dict(cfg.get("account_outros") or {})
        m.pop(str(account_id), None)
        cfg["account_outros"] = m
        save_reup_config(cfg)
        return
    if scope == "page":
        url = (page_url or "").strip()
        slug = page_intro_slug(url)
        if slug:
            _rm_dir(config.STORAGE_OUTROS_DIR / "by_page" / slug)
        m = dict(cfg.get("page_outros") or {})
        m.pop(url, None)
        for k in list(m.keys()):
            if url and (url in k or k in url):
                m.pop(k, None)
        cfg["page_outros"] = m
        save_reup_config(cfg)
        return
    raise ValueError("Không xóa được outro scope này")


def save_hook_text(
    *,
    scope: str,
    text: str,
    account_id: int | None = None,
    page_url: str | None = None,
) -> dict[str, Any]:
    scope = (scope or "").strip().lower()
    cfg = load_reup_config()
    t = (text or "").strip()[:120]
    if scope == "default":
        cfg["hook_default_text"] = t
        if t:
            cfg["hook_enabled"] = True
        save_reup_config(cfg)
        return {"scope": scope, "text": t}
    if scope == "account":
        if account_id is None:
            raise ValueError("Thiếu account_id")
        m = dict(cfg.get("account_hooks") or {})
        if t:
            m[str(account_id)] = t
            cfg["hook_enabled"] = True
        else:
            m.pop(str(account_id), None)
        cfg["account_hooks"] = m
        save_reup_config(cfg)
        return {"scope": scope, "text": t}
    if scope == "page":
        url = (page_url or "").strip()
        if not url:
            raise ValueError("Thiếu page_url")
        m = dict(cfg.get("page_hooks") or {})
        if t:
            m[url] = t
            cfg["hook_enabled"] = True
        else:
            m.pop(url, None)
        cfg["page_hooks"] = m
        save_reup_config(cfg)
        return {"scope": scope, "text": t, "page_url": url}
    raise ValueError("scope hook: default|account|page")
