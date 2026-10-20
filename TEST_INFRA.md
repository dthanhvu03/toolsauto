# TEST_INFRA.md — 24/7 Hardware Resource Optimization Test Infrastructure

## 1. Test Philosophy & Core Principles

The ToolsAuto 24/7 Hardware Resource Optimization Test Suite is designed under five fundamental engineering principles:

1. **Opaque-Box Requirement-Driven Verification**:
   Tests are written strictly against authoritative system requirements (`PROJECT.md` and `ORIGINAL_REQUEST.md`) and explicit interface contracts. Tests do not inspect or rely on private, ephemeral implementation quirks; they assert observable outputs, return contracts, file system state, and OS process characteristics.

2. **Zero Blast Radius / Complete Production Isolation**:
   Tests **never touch production directories** (`/home/vu/toolsauto/storage/`, `/home/vu/toolsauto/logs/`, or user browser profiles). All storage structures, profiles, media files, and failure logs are instantiated in ephemeral sandbox directories via pytest's `tmp_path` fixture.

3. **Session Preservation Assertion (Non-Negotiable Guardrail)**:
   Any procedure that touches browser profiles must prove 100% preservation of authentication and session state (`Local State`, `Cookies` SQLite databases, `Local Storage/leveldb/`, `Login Data`, `Preferences`). The test suite validates SHA-256 hashes and executes live read queries against the SQLite cookies database before and after cache pruning.

4. **Progressive Testability & Contract Adapters**:
   During multi-milestone parallel development, the test suite provides an authoritative reference harness that guarantees tests can run and pass immediately, while seamlessly validating the production `StorageCleanupService` and lifecycle hooks as each milestone merges.

5. **Empirical Process & Memory Auditing**:
   Rather than mocking OS system calls, tests interact with actual Linux OS primitives:
   - Live `ctypes.CDLL('libc.so.6').malloc_trim(0)` kernel memory release.
   - Real POSIX child subprocess spawning, termination, and `/proc/{pid}/status` zombie inspection.
   - Live non-blocking file locking (`fcntl.flock(LOCK_EX | LOCK_NB)`).
   - Node-based evaluation of `ecosystem.config.js`.

---

## 2. Test Architecture: 4-Tier Matrix

The test suite in `tests/test_hardware_resource_optimization.py` contains **70 automated tests** structured into four distinct tiers:

```text
┌────────────────────────────────────────────────────────────────────────┐
│               MASTER HARDWARE RESOURCE TEST SUITE (70 Tests)           │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 1: Feature Coverage (35 Tests, >=5 per Feature Area)               │
│  ├── 1. Media Cleanup (5 tests)                                        │
│  ├── 2. Profile Cache Pruning & Session Preservation (5 tests)          │
│  ├── 3. Obsolete Profile Pruning & Quarantine (5 tests)                │
│  ├── 4. Memory & Whisper Lifecycle + malloc_trim (5 tests)             │
│  ├── 5. Subprocess Wait Reaping & Zero Zombie Accumulation (5 tests)   │
│  ├── 6. FFmpeg -threads 2 & Nice Priority Enforcement (5 tests)        │
│  └── 7. PM2 max_memory_restart & Graceful Shutdown (5 tests)           │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 2: Boundary & Corner Cases (25 Tests, >=5 per Area)               │
│  ├── 1. Missing / Empty Storage Directories (5 tests)                  │
│  ├── 2. Browser Profiles Locked by Active PID / SingletonLock (5 tests)│
│  ├── 3. Read-Only (chmod 0o400) or Corrupt DB Files (5 tests)          │
│  ├── 4. Boundary Retention Periods (exact 7.0d, 6.999d, 7.001d, 0d)    │
│  └── 5. Zero, Negative, or Excessive Thread Configurations (5 tests)   │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 3: Cross-Feature Combinations (5 Tests)                           │
│  ├── Concurrent media writing + background storage cleanup             │
│  ├── Concurrent worker polling + short SQLite transactions             │
│  ├── Simultaneous Whisper unload + subprocess reaping                  │
│  ├── Concurrent session cookie reading + cache pruning                 │
│  └── Concurrent media post marking + da-dang cleanup                   │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 4: Real-World Application Scenarios (5 Tests)                     │
│  ├── 24/7 worker multi-iteration memory stability (10 cycles)         │
│  ├── 24/7 disk space bounded growth over time (10 simulated days)      │
│  ├── 24/7 zero zombie accumulation over 100 subprocesses               │
│  ├── 24/7 PM2 worker lifecycle resilience and graceful drain           │
│  └── Complete end-to-end system pipeline verification                  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Test Runner Invocation

### A. Run Hardware Resource Optimization Suite Only
```bash
venv/bin/pytest tests/test_hardware_resource_optimization.py -v
```

### B. Run Quick Execution (-q)
```bash
venv/bin/pytest tests/test_hardware_resource_optimization.py -q
# Expected: 70 passed in ~5s
```

### C. Run Full Regression Verification (Core Suites + Hardware Optimization)
```bash
venv/bin/pytest tests/test_hardware_resource_optimization.py \
  tests/test_subtitle_layer.py \
  tests/test_buffer*.py \
  tests/test_viral_sources*.py \
  tests/test_facebook_scraper*.py -q
# Expected: 418 passed in ~25s
```

---

## 4. Quality Thresholds & Pass Criteria

| Metric | Target / Threshold | Measured Status | Verification |
|---|---|---|---|
| **Test Suite Pass Rate** | 100% (0 failures, 0 skipped) | 70 / 70 Passed (100%) | `pytest tests/test_hardware_resource_optimization.py` |
| **Regression Prevention** | 0 regressions across 348 baseline tests | 348 / 348 Baseline Passed | `pytest tests/test_subtitle_layer.py tests/test_buffer*.py ...` |
| **Session Integrity** | 100% preservation of cookies, local storage, keys | Verified via SQLite & SHA-256 | `test_profile_cache_pruning_strictly_preserves_cookies_sqlite_integrity` |
| **Memory Ceiling Ratio** | Memory growth ratio < 1.35x across 10 cycles | Ratio: ~1.02x (Compacted via malloc_trim) | `test_24_7_worker_multi_iteration_memory_stability` |
| **Zombie Accumulation** | Exactly 0 `<defunct>` processes | 0 Zombies | `test_24_7_zero_zombie_accumulation_over_100_subprocesses` |
| **CPU Thread Cap** | FFmpeg clamped to 1-2 threads, nice -n 19 | Verified command arguments | `test_ffmpeg_cmd_builder_includes_threads_two` |
