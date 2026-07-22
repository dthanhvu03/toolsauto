"""Guards for health/auth hardening."""
from pathlib import Path

MAIN_PY = Path(__file__).resolve().parents[1] / "app" / "main.py"
HEALTH_PY = Path(__file__).resolve().parents[1] / "app" / "platform" / "health" / "router.py"
STRATEGIC_PY = Path(__file__).resolve().parents[1] / "app" / "core" / "strategic.py"


def test_health_prefix_not_fully_public():
    src = MAIN_PY.read_text(encoding="utf-8")
    assert 'allowed_prefixes = ("/health"' not in src
    assert "/health/gemini/cookie-sync" in src
    assert 'public_exact' in src


def test_cookie_sync_has_no_hardcoded_default_secret():
    src = HEALTH_PY.read_text(encoding="utf-8")
    assert "vuxuandao2026" not in src
    assert "COOKIE_SYNC_SECRET is not configured" in src


def test_strategic_platform_filter_parameterized():
    src = STRATEGIC_PY.read_text(encoding="utf-8")
    assert "WHERE platform = '{platform}'" not in src
    assert 'platform_filter = "WHERE platform = :platform"' in src
