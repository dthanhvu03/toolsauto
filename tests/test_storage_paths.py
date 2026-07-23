"""Storage path resolution (PLAN-003 / output unification)."""

import app.config as config
from app.core.storage_paths import resolve_media_path


def test_threads_media_under_storage_media():
    assert config.THREADS_MEDIA_DIR == config.STORAGE_MEDIA_DIR / "threads"


def test_debug_steps_under_logs():
    assert config.DEBUG_STEPS_DIR == config.LOGS_DIR / "debug_steps"


def test_resolve_reup_legacy_prefix(tmp_path, monkeypatch):
    reup = tmp_path / "reup"
    reup.mkdir()
    f = reup / "viral_1.mp4"
    f.write_bytes(b"x")
    monkeypatch.setattr(config, "REUP_DIR", reup)

    stored = "D:/old/reup_videos/viral_1.mp4"
    assert resolve_media_path(stored) == str(f.resolve())


def test_resolve_storage_content_prefix(tmp_path, monkeypatch):
    content = tmp_path / "storage" / "media" / "content"
    media = content / "media"
    media.mkdir(parents=True)
    f = media / "upload.jpg"
    f.write_bytes(b"x")
    monkeypatch.setattr(config, "CONTENT_DIR", content)

    stored = "C:/proj/content/media/upload.jpg"
    assert resolve_media_path(stored) == str(f.resolve())
