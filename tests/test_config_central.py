"""Runtime config lives under storage/db/config (not repo root)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_config_dir_under_storage():
    from app import config

    assert config.RUNTIME_CONFIG_DIR == config.STORAGE_DB_DIR / "config"
    assert config.GEMINI_COOKIES_FILE.parent == config.RUNTIME_CONFIG_DIR
    assert config.NINE_ROUTER_CONFIG_FILE.parent == config.RUNTIME_CONFIG_DIR


def test_no_hardcoded_root_gemini_paths_in_app():
    app_dir = ROOT / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        if path.name == "config.py":
            continue
        text = path.read_text(encoding="utf-8")
        if 'BASE_DIR / "gemini_cookies' in text or 'join(APP_DIR, "gemini_cookies' in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
