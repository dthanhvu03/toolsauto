"""Tests for PLAN-034 article curation scorer."""
from __future__ import annotations

import pytest

from app.features.threads.service.article_scorer import compute_score


class _Article:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _now() -> int:
    return 1_780_000_000  # fixed reference timestamp


def _article(title="Tin tức bình thường", source_name="VnExpress", topic_key="abc", age_hours=0.0):
    return _Article(
        title=title,
        source_name=source_name,
        topic_key=topic_key,
        published_at=_now() - int(age_hours * 3600),
    )


def test_recency_decays_with_age():
    fresh = compute_score(_article(age_hours=0.0), all_topic_counts={}, source_weights={}, now_ts=_now())
    medium = compute_score(_article(age_hours=6.0), all_topic_counts={}, source_weights={}, now_ts=_now())
    old = compute_score(_article(age_hours=24.0), all_topic_counts={}, source_weights={}, now_ts=_now())
    assert fresh > medium > old


def test_source_weight_higher_beats_lower():
    weights = {"VnExpress": 1.5, "24h": 0.5}
    high = compute_score(
        _article(source_name="VnExpress"), all_topic_counts={}, source_weights=weights, now_ts=_now()
    )
    low = compute_score(
        _article(source_name="24h"), all_topic_counts={}, source_weights=weights, now_ts=_now()
    )
    assert high > low


def test_hot_marker_bonus():
    plain = compute_score(
        _article(title="Bộ Y tế công bố quy định mới"),
        all_topic_counts={}, source_weights={}, now_ts=_now(),
    )
    hot = compute_score(
        _article(title="NÓNG: Bộ Y tế công bố quy định mới"),
        all_topic_counts={}, source_weights={}, now_ts=_now(),
    )
    assert hot > plain
    assert pytest.approx(hot - plain, abs=0.01) == 15.0


def test_topic_competition_bonus_tiers():
    base = compute_score(
        _article(topic_key="topic_x"),
        all_topic_counts={"topic_x": 1}, source_weights={}, now_ts=_now(),
    )
    two = compute_score(
        _article(topic_key="topic_x"),
        all_topic_counts={"topic_x": 2}, source_weights={}, now_ts=_now(),
    )
    three = compute_score(
        _article(topic_key="topic_x"),
        all_topic_counts={"topic_x": 5}, source_weights={}, now_ts=_now(),
    )
    assert three > two > base


def test_source_weight_clamped_high():
    weights = {"Foo": 99.0}
    score = compute_score(
        _article(source_name="Foo"), all_topic_counts={}, source_weights=weights, now_ts=_now(),
    )
    capped = compute_score(
        _article(source_name="Foo"), all_topic_counts={}, source_weights={"Foo": 1.5}, now_ts=_now(),
    )
    assert pytest.approx(score, abs=0.01) == capped


def test_source_weight_clamped_low():
    weights = {"Foo": -5.0}
    score = compute_score(
        _article(source_name="Foo"), all_topic_counts={}, source_weights=weights, now_ts=_now(),
    )
    floored = compute_score(
        _article(source_name="Foo"), all_topic_counts={}, source_weights={"Foo": 0.3}, now_ts=_now(),
    )
    assert pytest.approx(score, abs=0.01) == floored


def test_hot_marker_case_insensitive_with_diacritics():
    upper = compute_score(
        _article(title="ĐỘT NGỘT: lãi suất tăng"),
        all_topic_counts={}, source_weights={}, now_ts=_now(),
    )
    lower = compute_score(
        _article(title="đột ngột: lãi suất tăng"),
        all_topic_counts={}, source_weights={}, now_ts=_now(),
    )
    plain = compute_score(
        _article(title="Lãi suất tăng theo dự đoán"),
        all_topic_counts={}, source_weights={}, now_ts=_now(),
    )
    assert upper == lower
    assert upper > plain


def test_score_bounded_between_zero_and_hundred():
    weights = {"VnExpress": 1.5}
    best = compute_score(
        _article(
            title="NÓNG: chấn động sốc",
            source_name="VnExpress",
            topic_key="topic_hot",
            age_hours=0.0,
        ),
        all_topic_counts={"topic_hot": 10},
        source_weights=weights,
        now_ts=_now(),
    )
    worst = compute_score(
        _article(
            title="Tin cũ thường",
            source_name="Unknown",
            topic_key="topic_cold",
            age_hours=72.0,
        ),
        all_topic_counts={"topic_cold": 1},
        source_weights={"Unknown": 0.3},
        now_ts=_now(),
    )
    assert 0.0 <= worst <= best <= 100.0


def test_missing_published_at_zeros_recency():
    article = _Article(title="Tin", source_name="VnExpress", topic_key="t", published_at=None)
    score = compute_score(article, all_topic_counts={}, source_weights={}, now_ts=_now())
    # No recency, no hot marker, no topic competition → only source contribution remains.
    # Source weight default 1.0 → (1.0 - 0.3) / (1.5 - 0.3) ≈ 0.583 of 20 = ~11.67
    assert 10.0 <= score <= 13.0


def test_dict_input_supported():
    article = {
        "title": "NÓNG: tin",
        "source_name": "VnExpress",
        "topic_key": "abc",
        "published_at": _now(),
    }
    score = compute_score(article, all_topic_counts={}, source_weights={}, now_ts=_now())
    assert score > 0.0
