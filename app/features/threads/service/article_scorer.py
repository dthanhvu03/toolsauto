"""PLAN-034 article curation scoring.

Pure-function scorer combining 4 signals to rank news articles for Threads
publishing. Score is in [0, 100]; higher = more deserving of being posted.

Signal weights (sum = 100):
- recency       40   exp(-age_hours / 6)         newer = higher
- source_weight 20   clamp(weight, 0.3, 1.5)     authority bias
- hot_marker    15   regex match in title         scroll-stop bonus
- topic_comp    25   topic_key count >= 2|3       multi-source = hot

The scorer is intentionally cheap (no I/O) so news_scraper can call it
inline during ingestion.
"""
from __future__ import annotations

import math
import re
import time
from typing import Mapping, Optional


_HOT_MARKER_RE = re.compile(
    r"\b(nóng|đột ngột|lần đầu|kỷ lục|vừa|mới nhất|bất ngờ|chấn động|sốc)\b",
    re.IGNORECASE,
)

_RECENCY_WEIGHT = 40.0
_SOURCE_WEIGHT = 20.0
_HOT_WEIGHT = 15.0
_TOPIC_WEIGHT = 25.0

_SOURCE_WEIGHT_MIN = 0.3
_SOURCE_WEIGHT_MAX = 1.5
_RECENCY_HALFLIFE_HOURS = 6.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _recency_factor(published_at: Optional[int], now_ts: int) -> float:
    """Exponential decay; 0h → 1.0, 6h → 0.37, 12h → 0.14, 24h → 0.018."""
    if not published_at:
        return 0.0
    age_hours = max(0.0, (now_ts - int(published_at)) / 3600.0)
    return math.exp(-age_hours / _RECENCY_HALFLIFE_HOURS)


def _source_factor(source_name: Optional[str], source_weights: Mapping[str, float]) -> float:
    if not source_name:
        return 1.0
    raw = source_weights.get(source_name, 1.0)
    try:
        weight = float(raw)
    except (TypeError, ValueError):
        weight = 1.0
    return _clamp(weight, _SOURCE_WEIGHT_MIN, _SOURCE_WEIGHT_MAX)


def _hot_marker_factor(title: Optional[str]) -> float:
    if not title:
        return 0.0
    return 1.0 if _HOT_MARKER_RE.search(title) else 0.0


def _topic_competition_factor(topic_key: Optional[str], all_topic_counts: Mapping[str, int]) -> float:
    """Bonus tier — single source: 0, 2 sources: 1.0, 3+ sources: 1.5."""
    if not topic_key:
        return 0.0
    count = int(all_topic_counts.get(topic_key, 0) or 0)
    if count >= 3:
        return 1.5
    if count >= 2:
        return 1.0
    return 0.0


def compute_score(
    article,
    *,
    all_topic_counts: Mapping[str, int],
    source_weights: Mapping[str, float],
    now_ts: Optional[int] = None,
) -> float:
    """Compute curation score for a NewsArticle-like object.

    `article` may be a SQLAlchemy model or a dict-like object exposing
    `title`, `source_name`, `topic_key`, `published_at` attributes/keys.
    """
    if now_ts is None:
        now_ts = int(time.time())

    def _attr(name: str):
        if hasattr(article, name):
            return getattr(article, name)
        if isinstance(article, Mapping):
            return article.get(name)
        return None

    title = _attr("title")
    source_name = _attr("source_name")
    topic_key = _attr("topic_key")
    published_at = _attr("published_at")

    recency = _recency_factor(published_at, now_ts)
    source = _source_factor(source_name, source_weights or {})
    hot = _hot_marker_factor(title)
    topic = _topic_competition_factor(topic_key, all_topic_counts or {})

    # Source weight scales the recency contribution (authoritative + recent = much higher),
    # but does not scale the bonuses (hot marker / topic competition stand alone).
    score = (
        _RECENCY_WEIGHT * recency * source / _SOURCE_WEIGHT_MAX
        + _SOURCE_WEIGHT * (source - _SOURCE_WEIGHT_MIN) / (_SOURCE_WEIGHT_MAX - _SOURCE_WEIGHT_MIN)
        + _HOT_WEIGHT * hot
        + _TOPIC_WEIGHT * (topic / 1.5)
    )
    return round(_clamp(score, 0.0, 100.0), 4)
