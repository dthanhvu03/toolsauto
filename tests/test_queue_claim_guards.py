"""Static guards for claim_next_job security/fairness fixes."""
from pathlib import Path

QUEUE_PY = Path(__file__).resolve().parents[1] / "app" / "core" / "queue" / "queue.py"


def test_claim_uses_exact_platform_match():
    src = QUEUE_PY.read_text(encoding="utf-8")
    assert "j.platform LIKE '%' || :platform || '%'" not in src
    assert "j.platform = :platform" in src


def test_claim_mutex_is_per_platform():
    src = QUEUE_PY.read_text(encoding="utf-8")
    assert "j2.platform = j.platform" in src
    assert "Per-platform mutex" in src


def test_recover_caps_tries_to_failed():
    src = QUEUE_PY.read_text(encoding="utf-8")
    assert "WHEN (tries + 1) >= COALESCE(max_tries, 3) THEN 'FAILED'" in src
