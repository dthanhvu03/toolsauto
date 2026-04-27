"""
WorkflowRegistry — Dynamic platform configuration service.
Replaces all hardcoded selectors, timing, CTA, and adapter routing.
"""
import json
import time
import threading
import importlib
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CACHE_TTL = 60  # seconds — time-based fallback
_cache_lock = threading.Lock()
_cache: dict = {"ts": 0, "data": {}}

# ── Centralized constants (used by router, MCP, frontend) ────

KNOWN_TOGGLEABLE_STEPS = ["feed_browse", "pre_scan", "type_comment"]

PRESET_DESCRIPTIONS: dict[str, str] = {
    "post_facebook_reels": "Default full POST flow, all steps enabled",
    "facebook_post_stealth": "Stealth: max human-like delays for sensitive accounts",
    "facebook_post_fast": "Fast: skip feed_browse/pre_scan for batch publishing",
    "comment_facebook": "Default full COMMENT flow, all steps enabled",
    "facebook_comment_minimal": "Minimal: skip overlay/scroll, fast commenting",
}


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
    from app.database.core import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        data = {
            "platforms": {},
            "workflows": {},
            "selectors": {},
            "cta": {},
        }

        # Platform configs
        rows = db.execute(text(
            "SELECT platform, adapter_class, display_name, "
            "display_emoji, base_urls, viewport, media_extensions "
            "FROM platform_configs WHERE is_active=true"
        )).fetchall()
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

        # Workflow definitions — pick one active row per platform:job_type
        # ORDER BY name ensures deterministic winner if duplicates exist
        rows = db.execute(text(
            "SELECT name, platform, job_type, steps, "
            "timing_config, retry_config "
            "FROM workflow_definitions WHERE is_active=true "
            "ORDER BY platform, job_type, name"
        )).fetchall()
        for r in rows:
            key = f"{r[1]}:{r[2]}"
            if key in data["workflows"]:
                logger.warning(
                    "[WorkflowRegistry] Duplicate active preset for %s: "
                    "'%s' overwrites '%s'. Use apply_preset() to fix.",
                    key, r[0], data["workflows"][key].name,
                )
            data["workflows"][key] = WorkflowConfig(
                name=r[0], platform=r[1], job_type=r[2],
                steps=json.loads(r[3] or "[]"),
                timing=json.loads(r[4] or "{}"),
                retry=json.loads(r[5] or "{}"),
            )

        # Selectors — grouped by platform:category
        rows = db.execute(text("""
            SELECT id, platform, category, selector_name,
                   selector_type, selector_value, locale,
                   priority, notes
            FROM platform_selectors
            WHERE is_active=true
              AND (valid_until IS NULL OR valid_until > :now)
            ORDER BY platform, category, priority DESC
        """), {"now": int(time.time())}).fetchall()
        for r in rows:
            key = f"{r[1]}:{r[2]}:{r[3]}"
            if key not in data["selectors"]:
                data["selectors"][key] = []
            data["selectors"][key].append(SelectorItem(
                id=r[0], name=r[3], selector_type=r[4],
                selector_value=r[5], locale=r[6],
                priority=r[7], notes=r[8] or ""
            ))

        # CTA templates — grouped by platform
        rows = db.execute(text("""
            SELECT platform, template, locale,
                   page_url, niche, priority
            FROM cta_templates
            WHERE is_active=true
            ORDER BY platform, priority DESC
        """)).fetchall()
        for r in rows:
            key = r[0]
            if key not in data["cta"]:
                data["cta"][key] = []
            data["cta"][key].append({
                "template": r[1], "locale": r[2],
                "page_url": r[3], "niche": r[4],
                "priority": r[5]
            })

        return data
    except Exception as e:
        logger.error(f"[WorkflowRegistry] Load failed: {e}")
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


def invalidate():
    """Event-based cache bust — call after any admin save."""
    with _cache_lock:
        _cache["ts"] = 0
    logger.info("[WorkflowRegistry] Cache invalidated")


def get_cache_status() -> dict:
    """Expose cache state for admin UI."""
    with _cache_lock:
        ts = _cache["ts"]
    now = time.time()
    age = now - ts if ts > 0 else -1
    return {
        "age_seconds": round(age, 1) if age >= 0 else None,
        "last_reload_ts": round(ts, 1) if ts > 0 else None,
        "ttl_total": CACHE_TTL,
        "ttl_remaining": round(max(0, CACHE_TTL - age), 1) if age >= 0 else 0,
        "is_stale": age > CACHE_TTL if age >= 0 else True,
    }


class WorkflowRegistry:

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
                f"[Registry] No config for platform '{platform}'"
                f" — using DummyAdapter"
            )
            from app.adapters.dispatcher import DummyAdapter
            return DummyAdapter()
        try:
            mod_path, cls_name = config.adapter_class.rsplit(".", 1)
            module = importlib.import_module(mod_path)
            cls = getattr(module, cls_name)
            # GenericAdapter needs platform name to load correct workflow
            if cls_name == "GenericAdapter":
                return cls(platform=platform)
            return cls()
        except Exception as e:
            logger.error(f"[Registry] Import failed: {e}")
            from app.adapters.dispatcher import DummyAdapter
            return DummyAdapter()

    @staticmethod
    def get_platform_config(platform: str) -> Optional[PlatformConfig]:
        return _get_cache()["platforms"].get(platform)

    @staticmethod
    def get_workflow(
        platform: str, job_type: str
    ) -> Optional[WorkflowConfig]:
        key = f"{platform}:{job_type}"
        return _get_cache()["workflows"].get(key)

    @staticmethod
    def get_selectors(
        platform: str, category: str
    ) -> list[SelectorItem]:
        key = f"{platform}:{category}"
        return _get_cache()["selectors"].get(key, [])

    @staticmethod
    def get_selector_values(
        platform: str, category: str
    ) -> list[str]:
        """Return just selector strings in priority order."""
        items = WorkflowRegistry.get_selectors(platform, category)
        return [i.selector_value for i in items]

    @staticmethod
    def get_timing(
        platform: str, job_type: str, key: str,
        default: float = 0
    ) -> float:
        wf = WorkflowRegistry.get_workflow(platform, job_type)
        if not wf:
            return default
        return wf.timing.get(key, default)

    @staticmethod
    def get_cta_templates(
        platform: str,
        locale: str = "vi",
        page_url: str = None,
        niche: str = None
    ) -> list[str]:
        """
        Get CTA templates filtered by locale + optional page/niche.
        More specific matches first, then platform-wide.
        """
        all_cta = _get_cache()["cta"].get(platform, [])
        results = []
        for item in all_cta:
            if item["locale"] != locale and item["locale"] != "*":
                continue
            # Exact page match
            if page_url and item["page_url"] == page_url:
                results.insert(0, item["template"])
                continue
            # Niche match
            if niche and item["niche"] == niche:
                results.insert(0, item["template"])
                continue
            # Platform-wide (no page/niche restriction)
            if not item["page_url"] and not item["niche"]:
                results.append(item["template"])
        return results or ["{link}"]  # fallback

    @staticmethod
    def list_platforms() -> list[str]:
        return list(_get_cache()["platforms"].keys())

    @staticmethod
    def list_job_types(platform: str) -> list[str]:
        data = _get_cache()
        return [
            wf.job_type
            for key, wf in data["workflows"].items()
            if wf.platform == platform
        ]

    @staticmethod
    def get_base_url(platform: str, url_key: str) -> str:
        config = WorkflowRegistry.get_platform_config(platform)
        if not config:
            return ""
        return config.base_urls.get(url_key, "")

    # ── Phase 3C: Preset Management ─────────────────────────────

    @staticmethod
    def list_presets(platform: str, job_type: str) -> list[dict]:
        """List all presets (active + inactive) for a platform:job_type."""
        from app.database.core import SessionLocal
        from sqlalchemy import text as sa_text
        db = SessionLocal()
        try:
            rows = db.execute(sa_text(
                "SELECT name, is_active, steps, timing_config, retry_config "
                "FROM workflow_definitions "
                "WHERE platform = :platform AND job_type = :job_type "
                "ORDER BY is_active DESC, name"
            ), {"platform": platform, "job_type": job_type}).fetchall()
            return [{
                "name": r[0], "is_active": bool(r[1]),
                "steps": json.loads(r[2] or "[]"),
                "timing": json.loads(r[3] or "{}"),
                "retry": json.loads(r[4] or "{}"),
                "description": PRESET_DESCRIPTIONS.get(r[0], ""),
            } for r in rows]
        finally:
            db.close()

    @staticmethod
    def apply_preset(preset_name: str) -> str:
        """Activate a preset by name, deactivating siblings for same platform:job_type."""
        from app.database.core import SessionLocal
        from sqlalchemy import text as sa_text
        db = SessionLocal()
        try:
            row = db.execute(sa_text(
                "SELECT platform, job_type FROM workflow_definitions WHERE name = :name"
            ), {"name": preset_name}).fetchone()
            if not row:
                return f"Preset '{preset_name}' not found."

            platform, job_type = row[0], row[1]
            now = int(time.time())

            # Deactivate all siblings, activate target
            db.execute(sa_text(
                "UPDATE workflow_definitions SET is_active = false, updated_at = :now "
                "WHERE platform = :platform AND job_type = :job_type"
            ), {"platform": platform, "job_type": job_type, "now": now})

            db.execute(sa_text(
                "UPDATE workflow_definitions SET is_active = true, updated_at = :now "
                "WHERE name = :name"
            ), {"name": preset_name, "now": now})

            db.commit()
            invalidate()
            logger.info("[WorkflowRegistry] Preset '%s' activated for %s:%s",
                        preset_name, platform, job_type)
            return f"Preset '{preset_name}' activated for {platform}:{job_type}."
        except Exception as e:
            logger.error("[WorkflowRegistry] apply_preset failed: %s", e)
            return f"Error applying preset: {e}"
        finally:
            db.close()

    # ── Phase Overview: helpers ──────────────────────────────────

    @staticmethod
    def get_step_resolution(
        platform: str, job_type: str
    ) -> list[dict]:
        """Compute step resolution: RUN/SKIP for each known step."""
        wf = WorkflowRegistry.get_workflow(platform, job_type)
        active_steps = wf.steps if wf and wf.steps else []
        all_defaults = len(active_steps) == 0

        result = []
        for i, step in enumerate(KNOWN_TOGGLEABLE_STEPS):
            order = i + 1
            if all_defaults:
                result.append({
                    "step": step,
                    "order": order,
                    "status": "RUN",
                    "source": "default",
                    "reason": "steps=[] — all defaults",
                })
            elif step in active_steps:
                result.append({
                    "step": step,
                    "order": order,
                    "status": "RUN",
                    "source": "preset",
                    "reason": None,
                })
            else:
                result.append({
                    "step": step,
                    "order": order,
                    "status": "SKIP",
                    "source": "preset",
                    "reason": "not in steps list",
                })

        # Extra steps not in KNOWN_TOGGLEABLE_STEPS
        next_order = len(KNOWN_TOGGLEABLE_STEPS) + 1
        for step in active_steps:
            if step not in KNOWN_TOGGLEABLE_STEPS:
                result.append({
                    "step": step,
                    "order": next_order,
                    "status": "RUN",
                    "source": "preset",
                    "reason": "custom step",
                })
                next_order += 1
        return result

    @staticmethod
    def get_runtime_snapshot(
        platform: str, job_type: str, locale: str = "vi"
    ) -> dict:
        """Unified runtime snapshot for Overview tab."""
        wf = WorkflowRegistry.get_workflow(platform, job_type)

        # ── Timing human-readable ──
        def _human_ms(ms):
            if not isinstance(ms, (int, float)):
                return str(ms)
            if ms < 1000:
                return f"{int(ms)}ms"
            if ms < 60000:
                return f"{ms/1000:.1f}s"
            m = int(ms // 60000)
            s = round((ms % 60000) / 1000)
            return f"{m}m {s}s"

        timing_raw = wf.timing if wf else {}
        timing_human = {k: _human_ms(v) for k, v in timing_raw.items()}

        # ── CTA pool summary ──
        try:
            cta_list = WorkflowRegistry.get_cta_templates(
                platform, locale=locale
            )
            is_fallback = cta_list == ["{link}"]
            all_cta = _get_cache()["cta"].get(platform, [])
            page_specific = sum(
                1 for c in all_cta
                if c.get("page_url") and c.get("locale") in (locale, "*")
            )
            niche_specific = sum(
                1 for c in all_cta
                if c.get("niche") and not c.get("page_url")
                and c.get("locale") in (locale, "*")
            )
        except Exception:
            cta_list = ["{link}"]
            is_fallback = True
            page_specific = 0
            niche_specific = 0

        # ── Preset description ──
        preset_name = wf.name if wf else None
        preset_desc = PRESET_DESCRIPTIONS.get(preset_name, "") if preset_name else ""

        # ── Config source ──
        if not wf:
            config_source = {
                "preset": "none",
                "steps": "default",
                "timing": "default",
                "retry": "default",
                "cta": "fallback" if is_fallback else "database"
            }
        else:
            config_source = {
                "preset": "database",
                "steps": "preset" if wf.steps else "default",
                "timing": "preset" if wf.timing else "default",
                "retry": "preset" if wf.retry else "default",
                "cta": "fallback" if is_fallback else "database"
            }

        return {
            "preset": preset_name,
            "preset_description": preset_desc,
            "steps": wf.steps if wf else [],
            "step_resolution": WorkflowRegistry.get_step_resolution(
                platform, job_type
            ),
            "timing": timing_raw,
            "timing_human": timing_human,
            "retry": wf.retry if wf else {},
            "cta_pool": {
                "total": len(cta_list),
                "effective": page_specific + niche_specific,
                "locale": locale,
                "page_specific": page_specific,
                "niche_specific": niche_specific,
                "is_fallback": is_fallback,
            },
            "cache": get_cache_status(),
            "config_source": config_source,
        }
