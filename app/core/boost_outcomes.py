"""Persist boost approve snapshots for Insights closed-loop (no DB migration)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _path() -> Path:
    from app import config

    config.RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return config.RUNTIME_CONFIG_DIR / "boost_outcomes.json"


def _load() -> list[dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        return items if isinstance(items, list) else []
    except Exception as e:
        logger.warning("[boost_outcomes] load failed: %s", e)
        return []


def _save(items: list[dict[str, Any]]) -> None:
    p = _path()
    payload = {"items": items[-100:]}  # keep last 100
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def record_boost_approval(
    *,
    material_id: int,
    target_page: str | None,
    page_name: str | None,
    material_url: str | None,
    views_before: int | float | None,
    growth_pct_before: float | None,
    status_before: str | None,
) -> None:
    items = _load()
    items.append(
        {
            "material_id": material_id,
            "target_page": target_page or "",
            "page_name": page_name or "",
            "material_url": material_url or "",
            "approved_at": int(time.time()),
            "views_before": int(views_before or 0),
            "growth_pct_before": float(growth_pct_before or 0),
            "status_before": status_before or "",
        }
    )
    _save(items)


def list_outcomes_with_delta(current_by_page: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge stored snapshots with current page analysis metrics."""
    out = []
    for row in reversed(_load()):
        page = row.get("target_page") or ""
        cur = current_by_page.get(page) or {}
        growth_now = float(cur.get("growth_pct") or 0)
        views_now = int(cur.get("views") or 0)
        growth_before = float(row.get("growth_pct_before") or 0)
        views_before = int(row.get("views_before") or 0)
        out.append(
            {
                **row,
                "views_now": views_now,
                "growth_pct_now": growth_now,
                "growth_delta": round(growth_now - growth_before, 2),
                "views_delta": views_now - views_before,
                "status_now": cur.get("status") or "",
                "has_current": bool(cur),
            }
        )
    return out[:40]
