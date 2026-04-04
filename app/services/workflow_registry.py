"""
WorkflowRegistry — Dynamic platform configuration service.
Loads selectors, timing, CTA, and adapter routing from the database.
"""
from __future__ import annotations

import importlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_TTL = 60
_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {"ts": 0, "data": {}}


@dataclass
class SelectorItem:
    id: int
    name: str
    selector_type: str
    selector_value: str
    locale: str
    priority: int
    notes: str = ""


@dataclass
class PlatformConfig:
    platform: str
    adapter_class: str
    display_name: str
    display_emoji: str
    base_urls: dict = field(default_factory=dict)
    viewport: dict = field(default_factory=dict)
    media_extensions: list = field(default_factory=list)


@dataclass
class WorkflowConfig:
    name: str
    platform: str
    job_type: str
    steps: list
    timing: dict
    retry: dict


def _load_all() -> dict:
    """Load all config from DB into cache dict."""
    from sqlalchemy import text

    from app.database.core import SessionLocal

    db = SessionLocal()
    try:
        data: Dict[str, Any] = {
            "platforms": {},
            "workflows": {},
            "selectors": {},
            "cta": {},
        }

        rows = db.execute(
            text(
                "SELECT platform, adapter_class, display_name, "
                "display_emoji, base_urls, viewport, media_extensions "
                "FROM platform_configs WHERE is_active=1"
            )
        ).fetchall()
        for r in rows:
            data["platforms"][r[0]] = PlatformConfig(
                platform=r[0],
                adapter_class=r[1],
                display_name=r[2] or r[0].title(),
                display_emoji=r[3] or "",
                base_urls=json.loads(r[4] or "{}"),
                viewport=json.loads(r[5] or "{}"),
                media_extensions=json.loads(r[6] or "[]"),
            )

        rows = db.execute(
            text(
                "SELECT name, platform, job_type, steps, "
                "timing_config, retry_config "
                "FROM workflow_definitions WHERE is_active=1"
            )
        ).fetchall()
        for r in rows:
            key = f"{r[1]}:{r[2]}"
            data["workflows"][key] = WorkflowConfig(
                name=r[0],
                platform=r[1],
                job_type=r[2],
                steps=json.loads(r[3] or "[]"),
                timing=json.loads(r[4] or "{}"),
                retry=json.loads(r[5] or "{}"),
            )

        now = int(time.time())
        rows = db.execute(
            text(
                """
            SELECT id, platform, category, selector_name,
                   selector_type, selector_value, locale,
                   priority, notes
            FROM platform_selectors
            WHERE is_active=1
              AND (valid_until IS NULL OR valid_until > :now)
            ORDER BY platform, category, priority DESC
        """
            ),
            {"now": now},
        ).fetchall()
        for r in rows:
            key = f"{r[1]}:{r[2]}"
            if key not in data["selectors"]:
                data["selectors"][key] = []
            data["selectors"][key].append(
                SelectorItem(
                    id=r[0],
                    name=r[3],
                    selector_type=r[4],
                    selector_value=r[5],
                    locale=r[6],
                    priority=r[7],
                    notes=r[8] or "",
                )
            )

        rows = db.execute(
            text(
                """
            SELECT platform, template, locale,
                   page_url, niche, priority
            FROM cta_templates
            WHERE is_active=1
            ORDER BY platform, priority DESC
        """
            )
        ).fetchall()
        for r in rows:
            key = r[0]
            if key not in data["cta"]:
                data["cta"][key] = []
            data["cta"][key].append(
                {
                    "template": r[1],
                    "locale": r[2],
                    "page_url": r[3],
                    "niche": r[4],
                    "priority": r[5],
                }
            )

        return data
    except Exception as e:
        logger.error("[WorkflowRegistry] Load failed: %s", e, exc_info=True)
        return _cache.get("data", {})
    finally:
        db.close()


def _get_cache() -> dict:
    now = time.time()
    with _cache_lock:
        if now - _cache["ts"] > CACHE_TTL:
            _cache["data"] = _load_all()
            _cache["ts"] = now
    return _cache["data"]


def invalidate() -> None:
    """Event-based cache bust — call after any admin save."""
    with _cache_lock:
        _cache["ts"] = 0
    logger.info("[WorkflowRegistry] Cache invalidated")


class WorkflowRegistry:
    @staticmethod
    def invalidate() -> None:
        """Clear TTL cache (same as module-level invalidate())."""
        invalidate()

    @staticmethod
    def get_adapter(platform: str):
        """
        Dynamically import and instantiate adapter for platform.
        Falls back to DummyAdapter if not configured.
        """
        data = _get_cache()
        config = data["platforms"].get(platform)
        if not config:
            logger.warning(
                "[Registry] No config for platform '%s' — using DummyAdapter",
                platform,
            )
            from app.adapters.dispatcher import DummyAdapter

            return DummyAdapter()
        try:
            mod_path, cls_name = config.adapter_class.rsplit(".", 1)
            module = importlib.import_module(mod_path)
            cls = getattr(module, cls_name)
            return cls()
        except Exception as e:
            logger.error("[Registry] Import failed: %s", e, exc_info=True)
            from app.adapters.dispatcher import DummyAdapter

            return DummyAdapter()

    @staticmethod
    def get_platform_config(platform: str) -> Optional[PlatformConfig]:
        return _get_cache()["platforms"].get(platform)

    @staticmethod
    def get_workflow(platform: str, job_type: str) -> Optional[WorkflowConfig]:
        key = f"{platform}:{job_type}"
        return _get_cache()["workflows"].get(key)

    @staticmethod
    def get_selectors(platform: str, category: str) -> List[SelectorItem]:
        key = f"{platform}:{category}"
        return _get_cache()["selectors"].get(key, [])

    @staticmethod
    def get_selector_values(platform: str, category: str) -> List[str]:
        items = WorkflowRegistry.get_selectors(platform, category)
        return [i.selector_value for i in items]

    @staticmethod
    def get_timing(
        platform: str, job_type: str, key: str, default: float = 0
    ) -> float:
        wf = WorkflowRegistry.get_workflow(platform, job_type)
        if not wf:
            return default
        v = wf.timing.get(key, default)
        if isinstance(v, (int, float)):
            return float(v)
        return default

    @staticmethod
    def get_cta_templates(
        platform: str,
        locale: str = "vi",
        page_url: Optional[str] = None,
        niche: Optional[str] = None,
    ) -> List[str]:
        """
        CTA template strings filtered by locale and optional page/niche.
        More specific matches first, then platform-wide.
        """
        all_cta = _get_cache()["cta"].get(platform, [])
        results: List[str] = []
        for item in all_cta:
            loc = item["locale"]
            if loc != locale and loc != "*":
                continue
            if page_url and item["page_url"] == page_url:
                results.insert(0, item["template"])
                continue
            if niche and item["niche"] == niche:
                results.insert(0, item["template"])
                continue
            if not item["page_url"] and not item["niche"]:
                results.append(item["template"])
        return results or ["{link}"]

    @staticmethod
    def list_platforms() -> List[str]:
        return list(_get_cache()["platforms"].keys())

    @staticmethod
    def list_job_types(platform: str) -> List[str]:
        data = _get_cache()
        seen = {
            wf.job_type
            for key, wf in data["workflows"].items()
            if wf.platform == platform
        }
        return sorted(seen)

    @staticmethod
    def get_base_url(platform: str, url_key: str) -> str:
        config = WorkflowRegistry.get_platform_config(platform)
        if not config:
            return ""
        return config.base_urls.get(url_key, "")
