"""Guards for PM2 single-source and overlap cleanup."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pm2_safe_names_match_ecosystem():
    from app.core.pm2_apps import PM2_SAFE_NAMES, PM2_LOG_MAP

    eco = (ROOT / "ecosystem.config.js").read_text(encoding="utf-8")
    for name in (
        "Maintenance",
        "Web_Dashboard",
        "Threads_Growth",
        "Studio_Heavy",
        "Studio_Light",
        "9Router_Gateway",
    ):
        assert name in PM2_SAFE_NAMES
        assert f'name: "{name}"' in eco
        assert name in PM2_LOG_MAP
    # PLAN-166: worker đăng trực tiếp cũ đã bỏ khỏi PM2 và danh sách điều khiển
    for gone in ("FB_Publisher_1", "AI_Generator_1", "Threads_Publisher", "Threads_NewsWorker", "Threads_AutoReply"):
        assert gone not in PM2_SAFE_NAMES and f'name: "{gone}"' not in eco


def test_start_sh_uses_ecosystem_not_legacy_workers_path():
    start = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "ecosystem.config.js" in start
    assert "pm2 start ecosystem.config.js" in start
    # Legacy root path (pre feature move) must not be started
    assert " $VENV_PYTHON workers/" not in start
    assert 'pm2 start "bash -c' not in start or "ecosystem.config.js" in start


def test_no_core_import_of_features_facebook_media():
    notifier = (ROOT / "app/core/notifier/service.py").read_text(encoding="utf-8")
    assert "app.features.facebook" not in notifier
    assert "app.core.media" in notifier


def test_publishers_use_shared_claim_precheck():
    fb = (ROOT / "app/features/facebook/workers/publisher.py").read_text(encoding="utf-8")
    th = (ROOT / "app/features/threads/workers/publisher.py").read_text(encoding="utf-8")
    for src in (fb, th):
        assert "claim_precheck" in src
        assert "postpone_if_sleeping" in src
        assert "resource_blocks_claim(" not in src
