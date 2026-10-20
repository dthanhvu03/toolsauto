# Project: 24/7 Hardware Resource Optimization (RAM, CPU, Disk) & Cleanup Policy

## Architecture
ToolsAuto is a 24/7 automated viral content intake, processing, subtitling, and multi-channel publishing platform running on a Linux VPS (Intel Core i5-10300H, 4 logical cores, 7.6 GB RAM, 0 B Swap).
The resource optimization architecture introduces five protective layers:
1. **Storage Retention & Safe Cleanup Layer (`app/features/maintenance/storage_cleanup_service.py` + CLI `manage.py storage`)**:
   - Manages safe retention rotation for `storage/media/` (deleting posted videos in `da-dang/`, stale raw/reup files > 7 days, orphan preview frames/thumbnails).
   - Manages Playwright/Chromium profile cache pruning with 100% isolation of session keys (`Local State`, `Cookies`, `Local Storage/`, `IndexedDB/`, `Login Data`, `Preferences`), checking `SingletonLock` and `fcntl.flock` to guarantee zero corruption of social media login states.
   - Rotates failure logs (`logs/fb/`) and compresses historical SQL dumps.
2. **Memory Leak Prevention & Worker Lifecycle Layer**:
   - On-Demand Whisper model loading and unloading in `ContentOrchestrator` (`app/core/orchestrator.py`), invoking `del model`, `gc.collect()`, and Linux `ctypes.CDLL('libc.so.6').malloc_trim(0)` to release hundreds of megabytes back to OS RSS.
   - Clean subprocess lifecycles: reaping dead child processes with `.wait()` to prevent `<defunct>` zombie processes.
   - Robust Playwright browser bootstrap cleanup: ensuring `pw.stop()` is executed even when browser launch fails.
   - Short-lived DB transactions: moving long web scraping tasks outside SQLite transactions.
3. **CPU Throttling & Adaptive Polling Layer**:
   - Enforcing `-threads 2` and `nice -n 19` across all FFmpeg transcoding and subtitle-burning commands (`reup_processor.py`, `subtitle_layer.py`).
   - Capping Faster-Whisper to `cpu_threads=2`.
   - Adaptive backoff in idle worker loops to eliminate busy-waiting CPU spikes.
4. **PM2 24/7 Ecosystem Hardening Layer (`ecosystem.config.js`)**:
   - Adding `max_memory_restart` safeguards (e.g. 1500M for `Maintenance`, 500M for `Web_Dashboard`).
   - Adding `exp_backoff_restart_delay: 200` to prevent rapid restart death spirals.
   - Graceful shutdown signal handling (`SIGTERM`/`SIGINT`).
5. **E2E Testing & Resource Benchmark Verification Layer**:
   - Independent verification via `scripts/benchmark_resources.py`.
   - Comprehensive test suite covering disk cleanup, profile cache safety, memory release, and CPU caps without regressing the 478+ existing baseline tests.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Safe Media Retention & Cleanup | Automated pruning of `da-dang/` posted files, stale raw/reup files > 7 days, orphan frames/thumbnails in `storage/media/` | M1 | Survey 1 |
| 2 | Profile Cache Purge with Session Isolation | Safe pruning of Chromium/Playwright caches (`Cache`, `Code Cache`, `GPUCache`, shader caches) while strictly preserving `Local State`, `Cookies`, `Local Storage`, `IndexedDB`, `Login Data`, `Preferences` with PID lock safety | M1 | Survey 1 |
| 3 | Obsolete Profile Quarantine/Removal | Quarantining and safe deletion of unreferenced dead test profiles (`gemini_bot/`, `gemini_test_uc/`, `gemini_debug/` ~1.04GB) | M1 | Survey 1 |
| 4 | Log Rotation & DB Backup Compression | Pruning failure DOM dumps (`logs/fb/`), debug PNGs, and gzip compression of `.sql` backups in `storage/db/backups/` | M1 | Survey 1 |
| 5 | Central Storage Cleanup Service & CLI | Unified service in `app/features/maintenance/storage_cleanup_service.py` with `manage.py storage audit` and `manage.py storage cleanup` commands | M1 | Survey 1 |
| 6 | On-Demand Whisper Lifecycle & Malloc Trim | Dynamic loading/unloading of Whisper model with `del`, `gc.collect()`, and `libc.malloc_trim(0)` to prevent 1.7GB RAM trapping | M2 | Survey 2 |
| 7 | Subprocess Reaping & Zombie Prevention | Reaping terminated child processes via `.wait()` in `maintenance.py` and `insights/service.py` to prevent `<defunct>` zombies | M2 | Survey 2 |
| 8 | Playwright Node Driver Leak Fix | Ensuring `pw.stop()` is always called in exception branches during `launch_persistent_context` failures in `FacebookSessionManager` | M2 | Survey 2 |
| 9 | SQLite Transaction Duration Optimization | Moving 15-30s Playwright scraping outside SQLite `SessionLocal` transactions in `MetricsChecker` to eliminate DB write lock stalls | M2 | Survey 2 |
| 10 | FFmpeg Thread Throttling & Nice Priority | Specifying `-threads 2` and `nice -n 19` in all video transcoding/subtitle burning pipelines (`reup_processor.py`, `subtitle_layer.py`) | M3 | Survey 3 |
| 11 | Faster-Whisper CPU Thread Capping | Setting `cpu_threads=2` in `WhisperModel` initialization to prevent 100% CPU starvation on 4-core host | M3 | Survey 3 |
| 12 | Adaptive Polling Backoff in Background Workers | Implementing backoff polling in `Maintenance`, `verifier.py`, `auto_reply.py`, and `news_worker.py` to minimize idle CPU | M3 | Survey 3 |
| 13 | PM2 Max Memory Restarts | Setting `max_memory_restart` for `Maintenance` (1500M) and `Web_Dashboard` (500M) in `ecosystem.config.js` | M4 | Survey 3 |
| 14 | PM2 Exponential Backoff Restart Delay | Adding `exp_backoff_restart_delay: 200` to all worker definitions in `ecosystem.config.js` | M4 | Survey 3 |
| 15 | Worker Graceful Shutdown Handlers | Implementing `SIGTERM`/`SIGINT` signal trapping in Threads workers to terminate cleanly under PM2 | M4 | Survey 3 |
| 16 | Resource Benchmark & Telemetry Script | Benchmark script `scripts/benchmark_resources.py` to record before/after snapshots of RAM RSS, Disk, CPU, and Zombie counts | M5 | Survey 3 |
| 17 | E2E Testing Suite (Tiers 1-4) | Comprehensive test suite verifying cleanup accuracy, session protection, memory trim, and thread caps | M5 | Testing Track |
| 18 | Initial Safe Storage Pruning Execution | Running safe cleanup command to immediately reclaim ~4.7GB disk space without impacting active workflows | M5 | Survey 1, Acceptance |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Disk Storage Retention & Automated Smart Cleanup | Features 1, 2, 3, 4, 5: `storage_cleanup_service.py`, profile cache pruner with session preservation assertion, log/backup pruning, CLI commands | None | DONE (Passed Gate It2; 174 tests) |
| M2 | RAM Leak Prevention, Whisper Lifecycle & Zombie Reaping | Features 6, 7, 8, 9: Whisper on-demand load/unload with `malloc_trim(0)`, subprocess wait reaping, Playwright driver cleanup, short DB transactions | None | PLANNED |
| M3 | CPU Idle Optimization, FFmpeg Throttling & Backoff | Features 10, 11, 12: `-threads 2` & `nice -n 19` across FFmpeg commands, Whisper `cpu_threads=2`, worker adaptive polling | None | PLANNED |
| M4 | PM2 24/7 Ecosystem Hardening & Graceful Shutdown | Features 13, 14, 15: `ecosystem.config.js` updates (`max_memory_restart`, `exp_backoff_restart_delay`), `SIGTERM` handlers in workers | M2, M3 | PLANNED |
| M5 | E2E Verification, Resource Benchmark & Initial Disk Reclamation | Features 16, 17, 18: `scripts/benchmark_resources.py`, 100% test pass (Tiers 1-4 + 478 baseline), first safe cleanup run | M1, M2, M3, M4 | PLANNED |

---

## Interface Contracts

### 1. Storage Cleanup Service (`app/features/maintenance/storage_cleanup_service.py`)
```python
class StorageCleanupResult:
    reclaimed_bytes: int
    media_files_deleted: int
    profiles_cleaned: int
    logs_cleaned: int
    errors: list[str]

class StorageCleanupService:
    @classmethod
    def audit(cls) -> dict[str, Any]:
        """Calculates reclaimable bytes without deleting anything (dry-run)."""
        ...
    @classmethod
    def prune_media(cls, retention_days: int = 7, dry_run: bool = False) -> int:
        """Prunes posted da-dang files, stale raw/reup files > retention_days."""
        ...
    @classmethod
    def prune_profile_caches(cls, dry_run: bool = False) -> int:
        """Prunes disposable browser caches while asserting session file preservation."""
        ...
    @classmethod
    def prune_logs_and_backups(cls, dry_run: bool = False) -> int:
        """Prunes old DOM failure dumps and compresses SQL backups."""
        ...
    @classmethod
    def run_all(cls, dry_run: bool = False) -> StorageCleanupResult:
        """Executes full cleanup routine and logs results."""
        ...
```

### 2. Whisper Model Lifecycle (`app/core/orchestrator.py` & `app/features/viral_intake/subtitle_layer.py`)
```python
def release_whisper_model() -> None:
    """Explicitly deallocates faster-whisper model and calls malloc_trim(0)."""
    ...

class WhisperContext:
    """Context manager or on-demand accessor ensuring model unload and memory return to OS kernel."""
    def __enter__(self): ...
    def __exit__(self, exc_type, exc_val, exc_tb): ...
```

### 3. Subprocess & Process Execution Guardrails
- In `reup_processor.py` & `subtitle_layer.py`: All `ffmpeg` commands MUST include `-threads 2` and `nice -n 19`.
- In `ContentOrchestrator._get_whisper_model()`: `cpu_threads=2`.
- In `maintenance.py` & `insights/service.py`: Any `proc.kill()` MUST be immediately followed by `proc.wait(timeout=5)`.

---

## Code Layout
- `app/features/maintenance/storage_cleanup_service.py`: Core retention & cleanup logic. Owned by M1 Worker.
- `app/features/system_panel/workers/maintenance.py`: Periodic execution of storage cleanup, zombie prevention, short DB sessions. Owned by M1/M2 Worker.
- `manage.py`: Typer CLI entry points for `manage.py storage audit / cleanup`. Owned by M1 Worker.
- `app/core/orchestrator.py`: Whisper model lifecycle management and `malloc_trim(0)`. Owned by M2 Worker.
- `app/features/facebook/core/session.py` & `app/adapters/common/session.py`: Playwright `pw.stop()` leak prevention. Owned by M2 Worker.
- `app/features/viral_intake/reup_processor.py`: FFmpeg `-threads 2` and nice parameters. Owned by M3 Worker.
- `app/features/viral_intake/subtitle_layer.py`: Subtitle burning `-threads 2` and nice parameters. Owned by M3 Worker.
- `app/features/threads/workers/`: Polling backoff and `SIGTERM` signal handlers. Owned by M3/M4 Worker.
- `ecosystem.config.js`: PM2 memory restart limits and restart backoff. Owned by M4 Worker.
- `scripts/benchmark_resources.py`: Telemetry benchmark script. Owned by M5 Worker.
- `tests/test_storage_cleanup.py`: New unit tests for storage cleanup & session preservation. Owned by Test Writer / M1.
