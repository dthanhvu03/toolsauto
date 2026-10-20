"""
tests/test_memory_leak_prevention.py — Comprehensive Unit & Integration Tests for Milestone 2:
Features 6, 7, 8, 9: RAM Optimization, Memory Leak Prevention & Process Lifecycle.

Test Areas:
1. Feature 6: On-Demand Whisper Model Lifecycle & libc.malloc_trim(0)
2. Feature 7: Subprocess Reaping & Zombie Prevention (kill + wait(timeout=5))
3. Feature 8: Playwright Node Driver Process Leak (pw.stop() on launch failure)
4. Feature 9: SQLite Transaction Duration Optimization (Short Transaction Pattern)
"""

import os
import sys
import time
import subprocess
import threading
from unittest.mock import MagicMock, patch, ANY
import pytest

from app.core.orchestrator import (
    ContentOrchestrator,
    release_whisper_model,
    WhisperContext,
)
from app.features.facebook.core.session import FacebookSessionManager
from app.adapters.common.session import PlatformSessionManager, SessionManager
from app.core.observability.metrics_checker import (
    MetricsChecker,
    _MetricsJobTarget,
)
import app.features.system_panel.workers.maintenance as maint
import app.features.insights.service as insights_svc
from app.core.database.models import Job, Account
from app.constants import JobStatus


# ==============================================================================
# Feature 6: On-Demand Whisper Model Lifecycle & Malloc Trim
# ==============================================================================

class TestWhisperLifecycleAndMallocTrim:
    """Tests for on-demand Whisper model loading, releasing, and libc malloc_trim."""

    def test_release_whisper_model_clears_singleton_and_calls_malloc_trim(self):
        """Verifies release_whisper_model() clears cached model and triggers malloc_trim(0)."""
        ContentOrchestrator._whisper_model = {"dummy_model": "weights"}
        assert ContentOrchestrator._whisper_model is not None

        with patch("ctypes.CDLL") as mock_cdll, patch("gc.collect") as mock_gc:
            mock_libc = MagicMock()
            mock_cdll.return_value = mock_libc
            mock_libc.malloc_trim.return_value = 1

            release_whisper_model()

            assert ContentOrchestrator._whisper_model is None
            mock_gc.assert_called()
            mock_cdll.assert_called_with("libc.so.6")
            mock_libc.malloc_trim.assert_called_with(0)

    def test_release_whisper_model_with_target_obj(self):
        """Verifies release_whisper_model(target_obj) clears target's _whisper_model."""
        class CustomTarget:
            _whisper_model = "fake_heavy_model"

        target = CustomTarget()
        with patch("ctypes.CDLL") as mock_cdll:
            mock_libc = MagicMock()
            mock_cdll.return_value = mock_libc

            release_whisper_model(target)

            assert target._whisper_model is None
            mock_libc.malloc_trim.assert_called_with(0)

    def test_release_whisper_model_handles_missing_libc_gracefully(self):
        """Verifies release_whisper_model() handles OSError if libc.so.6 is missing."""
        ContentOrchestrator._whisper_model = {"fake": "model"}

        with patch("ctypes.CDLL", side_effect=OSError("libc.so.6 not found")), \
             patch("gc.collect") as mock_gc:
            # Should not raise exception
            release_whisper_model()

            assert ContentOrchestrator._whisper_model is None
            mock_gc.assert_called()

    def test_whisper_context_lifecycle_and_cleanup(self):
        """Verifies WhisperContext loads model, deletes reference on exit, and invokes malloc_trim."""
        mock_model_instance = MagicMock()

        with patch("faster_whisper.WhisperModel", return_value=mock_model_instance) as mock_wm, \
             patch("ctypes.CDLL") as mock_cdll, \
             patch("gc.collect") as mock_gc:
            mock_libc = MagicMock()
            mock_cdll.return_value = mock_libc

            with WhisperContext("base", cpu_threads=2) as model:
                assert model is mock_model_instance
                mock_wm.assert_called_once_with(
                    "base",
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=2,
                )

            # After exit
            mock_gc.assert_called()
            mock_libc.malloc_trim.assert_called_with(0)

    def test_whisper_default_model_size_is_base(self):
        """Verifies default model size is 'base' when WHISPER_MODEL_SIZE is unset or empty."""
        orig_val = os.environ.get("WHISPER_MODEL_SIZE")
        try:
            # Test when unset
            os.environ.pop("WHISPER_MODEL_SIZE", None)
            ContentOrchestrator._whisper_model = None

            with patch("faster_whisper.WhisperModel") as mock_wm:
                ContentOrchestrator.get_whisper_model()
                mock_wm.assert_called_once_with(
                    "base",
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=2,
                )

            # Test when empty string
            os.environ["WHISPER_MODEL_SIZE"] = ""
            ContentOrchestrator._whisper_model = None

            with patch("faster_whisper.WhisperModel") as mock_wm:
                ContentOrchestrator.get_whisper_model()
                mock_wm.assert_called_once_with(
                    "base",
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=2,
                )
        finally:
            if orig_val is not None:
                os.environ["WHISPER_MODEL_SIZE"] = orig_val
            else:
                os.environ.pop("WHISPER_MODEL_SIZE", None)
            ContentOrchestrator._whisper_model = None

    def test_viral_processor_calls_release_whisper_model_on_caption(self):
        """Verifies processor calls release_whisper_model() after generating caption for material."""
        from app.features.viral_intake import processor

        mock_db = MagicMock()
        mock_mat = MagicMock()
        mock_mat.id = 999
        mock_mat.status = "PENDING"
        mock_mat.platform = "facebook"

        with patch("app.features.viral_intake.processor.runtime_settings.get_bool", return_value=True), \
             patch("app.features.viral_intake.processor.ViralService.generate_caption_for_material", return_value=(True, "caption")), \
             patch("app.core.orchestrator.release_whisper_model") as mock_release, \
             patch("app.core.notifier.service.NotifierService.notify_material_ready"):
            
            processor._finish_ready_material(
                mock_db,
                mock_mat,
                media_path="/fake/path.mp4",
                drive_dest="offsite/path.mp4",
            )

            mock_release.assert_called_once()

    def test_viral_processor_calls_release_whisper_model_even_on_exception(self):
        """Verifies release_whisper_model() is called in finally block even if caption fails."""
        from app.features.viral_intake import processor

        mock_db = MagicMock()
        mock_mat = MagicMock()
        mock_mat.id = 999
        mock_mat.status = "PENDING"
        mock_mat.platform = "facebook"

        with patch("app.features.viral_intake.processor.runtime_settings.get_bool", return_value=True), \
             patch("app.features.viral_intake.processor.ViralService.generate_caption_for_material", side_effect=RuntimeError("AI failed")), \
             patch("app.core.orchestrator.release_whisper_model") as mock_release, \
             patch("app.core.notifier.service.NotifierService.notify_material_ready"):
            
            processor._finish_ready_material(
                mock_db,
                mock_mat,
                media_path="/fake/path.mp4",
                drive_dest="offsite/path.mp4",
            )

            mock_release.assert_called_once()


# ==============================================================================
# Feature 7: Subprocess Reaping & Zombie Prevention
# ==============================================================================

class TestSubprocessReapingAndZombiePrevention:
    """Tests for child process reaping with wait(timeout=5) after kill()."""

    def test_maintenance_subprocess_kill_and_immediate_wait(self):
        """Verifies maintenance._scrape_page_insights calls proc.kill() followed by proc.wait(timeout=5)."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc._start_time = time.time() - 2000  # Exceeds INSIGHTS_TIMEOUT_SEC (1800)

        maint._insights_process = mock_proc
        maint._last_insights_ts = time.time()  # Prevent starting a second process immediately

        try:
            maint._scrape_page_insights()

            mock_proc.kill.assert_called_once()
            mock_proc.wait.assert_called_once_with(timeout=5)
            assert maint._insights_process is None
        finally:
            maint._insights_process = None

    def test_insights_service_reaps_child_process_with_wait(self):
        """Verifies insights service trigger_refresh spawns child process and reaps it."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.wait.return_value = 0

        insights_svc._refresh_running = False

        with patch("os.path.exists", return_value=True), \
             patch("subprocess.Popen", return_value=mock_proc):
            
            res = insights_svc.trigger_refresh()
            assert isinstance(res, dict)
            assert res.get("status") == "success"
            assert res.get("pid") == 12345

            # Allow reaper thread to run wait()
            time.sleep(0.1)

            mock_proc.wait.assert_called()

    def test_insights_service_reaps_child_process_on_timeout(self):
        """Verifies insights service kills and reaps with wait(timeout=5) if child times out."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        # First call (timeout=1800) raises TimeoutExpired; second call (timeout=5) succeeds
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd=["test"], timeout=1800),
            0,
        ]

        insights_svc._refresh_running = False

        with patch("os.path.exists", return_value=True), \
             patch("subprocess.Popen", return_value=mock_proc):
            
            res = insights_svc.trigger_refresh()
            assert res.get("status") == "success"

            time.sleep(0.1)

            mock_proc.kill.assert_called_once()
            assert mock_proc.wait.call_count >= 2

    def test_real_subprocess_zombie_reaping(self):
        """Verifies a real OS process killed and reaped via wait() does not stay <defunct>."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        pid = proc.pid
        assert proc.poll() is None

        proc.kill()
        exit_code = proc.wait(timeout=5)

        assert exit_code is not None
        assert proc.poll() is not None

        # Verify not zombie in Linux procfs
        status_file = f"/proc/{pid}/status"
        if os.path.exists(status_file):
            try:
                with open(status_file, "r") as f:
                    content = f.read()
                assert "zombie" not in content.lower()
            except (FileNotFoundError, PermissionError):
                pass  # Process completely reaped and removed from procfs


# ==============================================================================
# Feature 8: Playwright Node Driver Process Leak Prevention
# ==============================================================================

class TestPlaywrightDriverCleanup:
    """Tests for closing pw and context on bootstrap failure to prevent orphaned Node.js drivers."""

    def test_facebook_session_pw_stop_on_launch_failure(self):
        """Verifies FacebookSessionManager calls pw.stop() when launch_persistent_context fails."""
        mock_pw = MagicMock()
        mock_pw.chromium.launch_persistent_context.side_effect = RuntimeError("Context launch failed")

        with patch("app.features.facebook.core.session.sync_playwright") as mock_sync_pw, \
             patch("app.features.facebook.core.session.FacebookSessionManager.log_profile_health"):
            
            mock_sync_pw.return_value.start.return_value = mock_pw

            result = FacebookSessionManager.launch_persistent("/fake/profile/path")

            assert result is None
            mock_pw.chromium.launch_persistent_context.assert_called_once()
            mock_pw.stop.assert_called_once()

    def test_common_session_pw_stop_on_launch_failure(self):
        """Verifies PlatformSessionManager calls pw.stop() when launch fails."""
        mock_pw = MagicMock()
        mock_pw.chromium.launch_persistent_context.side_effect = RuntimeError("Chromium launch failed")

        with patch("app.adapters.common.session.sync_playwright") as mock_sync_pw:
            mock_sync_pw.return_value.start.return_value = mock_pw

            result = PlatformSessionManager.launch(profile_path="/fake/profile/path")

            assert result is None
            mock_pw.chromium.launch_persistent_context.assert_called_once()
            mock_pw.stop.assert_called_once()

    def test_common_session_alias_launch_persistent(self):
        """Verifies SessionManager alias provides launch_persistent method."""
        mock_pw = MagicMock()
        mock_pw.chromium.launch_persistent_context.side_effect = RuntimeError("Chromium launch failed")

        with patch("app.adapters.common.session.sync_playwright") as mock_sync_pw:
            mock_sync_pw.return_value.start.return_value = mock_pw

            result = SessionManager.launch_persistent(profile_path="/fake/profile/path")

            assert result is None
            mock_pw.stop.assert_called_once()

    def test_metrics_checker_scrape_views_cleanup_no_unbound_local(self):
        """Verifies MetricsChecker._scrape_views handles cleanup without UnboundLocalError when browser is None."""
        mock_target = _MetricsJobTarget(
            id=101,
            post_url="https://facebook.com/reel/123456789012345",
            target_page="test_page",
            account_id=1,
            account_name="test_acc",
            profile_path=None,
        )

        mock_page = MagicMock()
        mock_page.evaluate.return_value = [{"url": "/reel/123456789012345", "text": "1.5K"}]
        mock_ctx = MagicMock()
        mock_ctx.pages = [mock_page]
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch_persistent_context.return_value = mock_ctx

        with patch("playwright.sync_api.sync_playwright") as mock_spw:
            mock_spw.return_value.__enter__.return_value = mock_playwright

            views = MetricsChecker._scrape_views(mock_target)

            assert views == 1500
            mock_ctx.close.assert_called_once()


# ==============================================================================
# Feature 9: SQLite Transaction Duration Optimization
# ==============================================================================

class TestSQLiteTransactionDurationOptimization:
    """Tests for Short Transaction Pattern in MetricsChecker and Maintenance worker."""

    def test_metrics_checker_short_transactions(self):
        """Verifies MetricsChecker acquires short DB read transaction, drops it during scraping, then short write."""
        events = []

        class MockSession:
            def __enter__(self):
                events.append("session_open")
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                events.append("session_close")

            def query(self, *args, **kwargs):
                return self

            def join(self, *args, **kwargs):
                return self

            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return self

            def first(self):
                # Return dummy job for read transaction
                mock_job = MagicMock()
                mock_job.id = 77
                mock_job.post_url = "https://facebook.com/reel/9988776655"
                mock_job.target_page = "my_page"
                mock_job.account_id = 5
                mock_job.account = MagicMock(name="acc5", profile_path=None)
                return mock_job

            def commit(self):
                events.append("session_commit")

        def fake_scrape(target):
            events.append("scrape_views_started")
            time.sleep(0.01)
            events.append("scrape_views_finished")
            return 3200

        with patch("app.core.database.core.SessionLocal", side_effect=[MockSession(), MockSession()]), \
             patch.object(MetricsChecker, "_scrape_views", side_effect=fake_scrape):

            MetricsChecker.check_pending()

            # Verify event sequence:
            # 1. Read session opened, committed, closed
            # 2. Scrape views performed outside DB session
            # 3. Write session opened, committed, closed
            assert events == [
                "session_open",
                "session_commit",
                "session_close",
                "scrape_views_started",
                "scrape_views_finished",
                "session_open",
                "session_commit",
                "session_close",
            ]

    def test_maintenance_does_not_hold_db_session_during_metrics_check(self):
        """Verifies maintenance.run_loop does NOT call MetricsChecker inside the main routine DB session."""
        import inspect
        source = inspect.getsource(maint.run_loop)

        # In run_loop, the main maintenance block is `with SessionLocal() as db:`
        main_with_idx = source.find("with SessionLocal() as db:")
        assert main_with_idx != -1

        # Locate the end of that with block (db.commit())
        main_commit_idx = source.find("db.commit()", main_with_idx)
        assert main_commit_idx != -1

        # Check if MetricsChecker.check_pending is called within [main_with_idx, main_commit_idx]
        inside_main_db = source[main_with_idx:main_commit_idx]
        assert "MetricsChecker.check_pending" not in inside_main_db, (
            "MetricsChecker.check_pending should NOT be inside main maintenance with SessionLocal() transaction"
        )

        # Check that MetricsChecker.check_pending IS called in run_loop after that block
        after_main_db = source[main_commit_idx:]
        assert "MetricsChecker.check_pending" in after_main_db, (
            "MetricsChecker.check_pending should be called in an isolated short transaction outside the main DB session"
        )
