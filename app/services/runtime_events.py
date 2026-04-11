"""
Phase 3A — Lightweight structured runtime event emitter.

Every event is a single logger.info() call with a JSON-serializable dict.
Format: [RT:{event}] {json_payload}

No external dependencies. Safe to call from any thread.
If logging fails, the caller's control-flow is never interrupted.
"""
import json
import logging

logger = logging.getLogger("n8n.runtime")


def emit(event: str, **fields) -> None:
    """Emit a structured runtime event. Never raises."""
    try:
        payload = {"event": event, **fields}
        logger.info(
            "[RT:%s] %s",
            event,
            json.dumps(payload, ensure_ascii=False, default=str),
        )
    except Exception:
        pass  # observability must never break runtime


# ── Phase 3B: Selector Health Counters ──────────────────────
import time
import copy
import threading

_server_start_ts = time.time()
_health_lock = threading.Lock()
_selector_stats: dict[str, dict] = {}


def record_selector_outcome(
    category: str, selector_key: str, source: str,
    matched: bool, matched_index: int | None = None,
    total_tried: int = 0,
) -> None:
    """Record whether a selector array matched or failed. Never raises."""
    try:
        key = f"{category}:{selector_key}"
        with _health_lock:
            if key not in _selector_stats:
                _selector_stats[key] = {
                    "hit": 0, "miss": 0,
                    "last_source": "", "last_result": "",
                    "last_ts": 0,
                }
            stats = _selector_stats[key]
            if matched:
                stats["hit"] += 1
                stats["last_result"] = "match"
            else:
                stats["miss"] += 1
                stats["last_result"] = "no_match"
            stats["last_source"] = source
            stats["last_ts"] = time.time()

        event_name = "selector_match_success" if matched else "selector_match_failure"
        emit(event_name, platform="facebook", category=category,
             selector_key=selector_key, source=source,
             matched_index=matched_index, total_tried=total_tried)
    except Exception:
        pass


def get_selector_health() -> dict:
    """Return current selector health snapshot. Thread-safe."""
    with _health_lock:
        return copy.deepcopy(_selector_stats)


def get_server_uptime() -> float:
    """Seconds since this process started."""
    return time.time() - _server_start_ts


def get_enriched_selector_health() -> dict:
    """Return selector health with summary, severity, and suggestions."""
    stats = get_selector_health()
    now = time.time()

    items = []
    summary = {"healthy": 0, "warning": 0, "failing": 0}

    for key, s in stats.items():
        total = s["hit"] + s["miss"]
        rate = round(s["hit"] / total * 100) if total else 0

        # Severity
        if rate == 0 and total > 0:
            severity = "critical"
            summary["failing"] += 1
        elif rate < 50:
            severity = "warning"
            summary["warning"] += 1
        else:
            severity = "healthy"
            summary["healthy"] += 1

        # Suggestion
        if severity == "critical" and s["last_source"] == "static_fallback":
            suggestion = (
                "Khong co DB selector, static fallback cung fail. "
                "Can them selector moi vao DB."
            )
        elif severity == "critical":
            suggestion = (
                "Selector trong DB co the da cu. "
                "Inspect DOM va cap nhat selector value."
            )
        elif severity == "warning":
            suggestion = (
                "Selector doi khi match, doi khi khong. "
                "Co the DOM khac nhau giua cac locale hoac account type."
            )
        else:
            suggestion = None

        confidence = "low" if total < 5 else "high"

        items.append({
            "key": key,
            "hit": s["hit"],
            "miss": s["miss"],
            "total": total,
            "rate": rate,
            "last_result": s["last_result"],
            "last_source": s["last_source"],
            "last_attempt_ts": s["last_ts"],
            "last_attempt_ago": round(now - s["last_ts"]) if s["last_ts"] else None,
            "severity": severity,
            "confidence": confidence,
            "suggestion": suggestion,
        })

    # Sort: failing first, then warning, then healthy
    severity_order = {"critical": 0, "warning": 1, "healthy": 2}
    items.sort(key=lambda x: (severity_order.get(x["severity"], 9), -x["total"]))

    return {
        "server_uptime_seconds": round(get_server_uptime()),
        "total_tracked": len(items),
        "summary": summary,
        "items": items,
    }

