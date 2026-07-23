"""
Persist reup variant outcomes for Insights closed-loop (no DB migration).
"""
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
    return config.RUNTIME_CONFIG_DIR / "reup_variants.json"


def _load() -> list[dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        return items if isinstance(items, list) else []
    except Exception as e:
        logger.warning("[reup_variants] load failed: %s", e)
        return []


def _save(items: list[dict[str, Any]]) -> None:
    p = _path()
    payload = {"items": items[-200:]}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def record_reup_variant(
    *,
    material_id: int,
    preset: str,
    platform: str | None = None,
    target_page: str | None = None,
    metrics: dict[str, Any] | None = None,
    source: str = "ingest",
) -> None:
    items = _load()
    items.append(
        {
            "material_id": material_id,
            "preset": preset,
            "platform": platform or "",
            "target_page": target_page or "",
            "source": source,
            "recorded_at": int(time.time()),
            "metrics": metrics or {},
        }
    )
    _save(items)


def list_variant_stats() -> list[dict[str, Any]]:
    """Aggregate counts per preset for Insights panel."""
    counts: dict[str, dict[str, Any]] = {}
    for row in _load():
        preset = row.get("preset") or "safe"
        bucket = counts.setdefault(
            preset,
            {"preset": preset, "count": 0, "last_at": 0, "avg_runtime_ms": 0.0, "_rt_sum": 0.0},
        )
        bucket["count"] += 1
        bucket["last_at"] = max(int(bucket["last_at"] or 0), int(row.get("recorded_at") or 0))
        rt = float((row.get("metrics") or {}).get("runtime_ms") or 0)
        bucket["_rt_sum"] += rt
    out = []
    for preset, b in counts.items():
        n = max(1, int(b["count"]))
        out.append(
            {
                "preset": preset,
                "count": b["count"],
                "last_at": b["last_at"],
                "avg_runtime_ms": round(float(b["_rt_sum"]) / n, 1),
            }
        )
    out.sort(key=lambda x: (-x["count"], x["preset"]))
    return out
