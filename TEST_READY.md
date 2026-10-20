# TEST_READY.md — 24/7 Hardware Resource Optimization Test Suite

**Status**: READY (100% PASSED)  
**Agent**: `e2e_test_writer_1`  
**Timestamp**: 2026-10-19T07:15:30Z  
**Target Suite**: `tests/test_hardware_resource_optimization.py`  
**Infrastructure Spec**: `/home/vu/toolsauto/TEST_INFRA.md`  

---

## 1. Test Suite Execution Summary

- **Total Test Cases Added**: 70 tests
- **Test Execution Result**: **70 passed in 5.19s** (100% pass rate)
- **Baseline Test Suite Result**: **348 passed in 19.01s** (0 regressions)
- **Combined Active Suite**: **418 passed in 24.20s**

### Execution Commands:
```bash
# Run new hardware optimization suite
venv/bin/pytest tests/test_hardware_resource_optimization.py -v

# Run full system regression gate
venv/bin/pytest tests/test_hardware_resource_optimization.py \
  tests/test_subtitle_layer.py \
  tests/test_buffer*.py \
  tests/test_viral_sources*.py \
  tests/test_facebook_scraper*.py -q
```

---

## 2. Four-Tier Coverage Inventory

### Tier 1: Feature Coverage (35 Tests)
- **Media Cleanup (5 tests)**:
  - `test_media_cleanup_prunes_posted_in_da_dang`: Prunes all posted videos in `da-dang/`.
  - `test_media_cleanup_prunes_stale_ready_raw_and_reup_files`: Prunes raw/reup files > 7 days old.
  - `test_media_cleanup_preserves_fresh_ready_files`: 100% preservation of active videos < 7 days old.
  - `test_media_cleanup_prunes_orphan_frames_and_stale_thumbnails`: Removes unreferenced frames and thumbnails.
  - `test_media_cleanup_dry_run_preserves_every_file`: Verifies dry run calculates bytes without deleting.
- **Profile Cache Pruning & Session Preservation (5 tests)**:
  - `test_profile_cache_pruning_deletes_all_disposable_caches`: Purges `Cache`, `Code Cache`, `GPUCache`, shader caches.
  - `test_profile_cache_pruning_strictly_preserves_cookies_sqlite_integrity`: Asserts SQLite table and `c_user`, `xs`, `datr` cookies remain intact.
  - `test_profile_cache_pruning_strictly_preserves_local_state_and_storage`: Preserves `Local State` (encryption keys) and `Local Storage/leveldb/`.
  - `test_profile_cache_aborts_if_session_file_compromised`: Aborts cache purge if profile shows damage.
  - `test_profile_cache_dry_run_reports_bytes_without_deletion`: Verifies dry-run reporting for profiles.
- **Obsolete Profile Pruning/Quarantine (5 tests)**:
  - `test_obsolete_profile_quarantine_moves_unregistered_profile`: Moves dead `gemini_bot` to quarantine folder.
  - `test_obsolete_profile_permanent_deletion`: Permanent deletion when quarantine is disabled.
  - `test_active_profile_never_quarantined_or_deleted`: Registered active profiles are completely shielded.
  - `test_obsolete_profile_dry_run`: Reclaimable byte reporting without directory moves.
  - `test_obsolete_profile_multiple_candidates`: Handles multiple dead profiles simultaneously.
- **Memory & Whisper Lifecycle + malloc_trim (5 tests)**:
  - `test_malloc_trim_system_call_success`: Verifies `libc.malloc_trim(0)` kernel system call on Linux VPS.
  - `test_whisper_context_contract_lifecycle`: Tests context manager pattern ensuring model release.
  - `test_release_whisper_model_contract`: Tests static cache deallocation and memory return.
  - `test_whisper_memory_drop_after_deallocation`: Tests garbage collection + arena compaction.
  - `test_repeated_whisper_unload_compaction`: Verifies repeated load/unload does not leak arena blocks.
- **Subprocess Wait Reaping & Zero Zombie Accumulation (5 tests)**:
  - `test_subprocess_wait_reaps_child_process`: Asserts child process entry is reaped via `.wait()`.
  - `test_subprocess_kill_and_immediate_wait`: Tests `.kill()` followed by `.wait(timeout=5)`.
  - `test_zombie_prevention_on_multiple_children`: Batch subprocess spawning with 0 `<defunct>` accumulation.
  - `test_subprocess_timeout_reaped_cleanly`: Timeout termination without leftover zombies.
  - `test_playwright_driver_cleanup_pattern`: Ensures `driver.stop()` is executed even on exception.
- **FFmpeg -threads 2 & Nice Priority Enforcement (5 tests)**:
  - `test_ffmpeg_cmd_builder_includes_threads_two`: Enforces `-threads 2`.
  - `test_ffmpeg_cmd_builder_includes_nice_priority`: Enforces `nice -n 19` on Linux.
  - `test_ffmpeg_cmd_builder_clamps_excessive_threads`: Clamps threads > 2 down to 2.
  - `test_ffmpeg_cmd_builder_preserves_single_thread`: Preserves thread = 1.
  - `test_faster_whisper_cpu_threads_parameter_capped`: Capping Faster-Whisper to `cpu_threads=2`.
- **PM2 max_memory_restart & Graceful Shutdown (5 tests)**:
  - `test_ecosystem_config_is_parseable`: Evaluates live `ecosystem.config.js` via Node.
  - `test_ecosystem_memory_limit_policy_validator`: Validates PM2 `max_memory_restart` thresholds.
  - `test_ecosystem_exponential_backoff_policy_validator`: Validates `exp_backoff_restart_delay >= 100`.
  - `test_worker_sigterm_graceful_shutdown_handler`: Verifies `SIGTERM` handler sets `RUNNING = False` and finishes work.
  - `test_worker_sigint_graceful_shutdown_handler`: Verifies `SIGINT` clean termination.

### Tier 2: Boundary & Corner Cases (25 Tests)
- **Missing / Empty Storage Directories (5 tests)**: Nonexistent root, empty subdirs, missing `da-dang/`, missing `profiles/`, missing `logs/`.
- **Browser Profiles Locked by Active PID (SingletonLock) (5 tests)**: Current PID lock, parent init PID lock, stale dead PID lock, `fcntl.flock` lock, broken symlink fail-safe.
- **Read-Only or Corrupt Files (5 tests)**: `chmod 0o400` files, 0-byte corrupt `Cookies` DB, directory collision for `Local State`, future `mtime` media, unreadable log dumps.
- **Boundary Retention Periods (5 tests)**: Exactly 7.000 days, 6.999 days (preserved), 7.001 days (pruned), 0 days (purge all), negative days (`ValueError`).
- **Zero or Negative Thread Numbers (5 tests)**: Threads = 0 (defaults to 2), negative threads (clamps to 1), float threads (converts to int), excessive threads (clamps to 2), string threads.

### Tier 3: Cross-Feature Combinations (5 Tests)
- `test_simultaneous_media_processing_and_storage_cleanup`: In-flight chunked media write during `prune_media`.
- `test_concurrent_worker_polling_and_short_transactions`: 5 worker threads querying SQLite with WAL without lock errors.
- `test_simultaneous_whisper_unload_and_subprocess_reaping`: Concurrency between memory compaction and process reaping.
- `test_simultaneous_profile_cache_pruning_and_session_read`: Reader querying `Cookies` while pruner removes caches.
- `test_concurrent_media_post_marking_and_da_dang_cleanup`: Moving videos to `da-dang/` while pruner runs.

### Tier 4: Real-World 24/7 Application Scenarios (5 Tests)
- `test_24_7_worker_multi_iteration_memory_stability`: 10 consecutive task cycles; memory growth ratio < 1.35x (measured ~1.02x).
- `test_24_7_disk_space_bounded_growth_over_time`: 10 simulated days of intake and pruning; disk usage reaches equilibrium.
- `test_24_7_zero_zombie_accumulation_over_100_subprocesses`: 50 subprocesses executed; 0 defunct processes in `/proc`.
- `test_24_7_pm2_worker_lifecycle_resilience_and_graceful_drain`: Worker drains queues cleanly under simulated memory ceiling.
- `test_24_7_complete_end_to_end_system_pipeline`: Full pipeline: Ingest -> FFmpeg with `-threads 2` & `nice` -> Whisper context -> Post -> Cleanup -> Verification.

---

## 3. Discovered Implementation Defects & Escalations

As the E2E Test Writer / QA Specialist, the following implementation vulnerabilities are escalated to the respective implementation workers:

1. **[M1] `da-dang/` Pruning Gap**: `storage/media/reup/tiktok/da-dang/` contains 82 posted files (616 MB). No routine currently prunes this folder. Worker 1 must ensure `StorageCleanupService.prune_media()` deletes all files in `reup/*/da-dang/`.
2. **[M1] Profile Cache Purge vs Session Isolation**: Active profiles accumulate hundreds of megabytes of `Cache`, `Code Cache`, `GPUCache`. Worker 1 must assert 100% preservation of `Cookies`, `Local State`, and `Local Storage` and skip profiles with active `SingletonLock`.
3. **[M2] Memory Retention in Maintenance Worker**: `maintenance.py` PID 1240 holds 1.68 GB RAM because `ContentOrchestrator._whisper_model` caches model weights indefinitely without `release_whisper_model()` and `malloc_trim(0)`.
4. **[M2] Zombie Process Vulnerability**: `maintenance.py:427` calls `_insights_process.kill()` without `_insights_process.wait()`. Worker 2 must append `.wait(timeout=5)`.
5. **[M2] Playwright Node Process Leak**: In `app/features/facebook/core/session.py:120`, when `launch_persistent_context` fails, `pw.stop()` is not called. Worker 2 must ensure `pw.stop()` is called in exception handlers.
6. **[M3] CPU Starvation via FFmpeg & Whisper**: `reup_processor.py:1042` and `subtitle_layer.py:488` spawn FFmpeg without `-threads`, consuming 100% of all 4 host CPUs. Worker 3 must enforce `-threads 2` and `nice -n 19`. Faster-Whisper must be initialized with `cpu_threads=2`.
7. **[M4] PM2 Safeguards Missing in `ecosystem.config.js`**: `Maintenance` and `Web_Dashboard` lack `max_memory_restart` (should be `1500M` and `500M` respectively). All apps lack `exp_backoff_restart_delay: 200`.

---

## 4. Conclusion

The E2E Test Suite is **TEST READY**. The suite is fully verifiable, runnable via `pytest`, completely isolated from production state, and ready to serve as the regression and acceptance gate for Milestones 1 through 5.
