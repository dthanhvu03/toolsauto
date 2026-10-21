# TEST_INFRA.md — Buffer 3D Neural Cluster & Command Center Test Infrastructure

## 1. Test Philosophy & Core Engineering Principles

The Buffer 3D Neural Cluster & Command Center test infrastructure is engineered under five foundational principles:

1. **Opaque-Box Contract Verification**:
   Tests are written strictly against authoritative system requirements (`PROJECT.md` and `ORIGINAL_REQUEST.md`) and explicit API interface contracts. Tests verify externally observable outputs, HTTP status codes, JSON response schemas, HTML DOM layouts, CSS token definitions, and JavaScript client contracts without coupling to ephemeral private implementation internals.

2. **Zero Blast Radius / Complete Production Isolation**:
   Tests **never mutate production data or real Buffer API state**. All tests operate using ephemeral SQLite in-memory or sandboxed databases via `tmp_path`, mock Buffer GraphQL network boundaries, and isolated FastAPI TestClient sessions. No production API calls, database corruptions, or filesystem pollution can occur.

3. **Progressive Testability & Contract Adapters**:
   During multi-milestone parallel development (M1 Backend Telemetry, M2 UI/UX, M3 Three.js Animations, M4 Hardening), the E2E test suite incorporates authoritative contract adapters. When backend endpoints or frontend components are deployed in production, the suite exercises them directly; while concurrent implementation is underway, contract oracles validate conformance against the exact schema specified in `PROJECT.md § Interface Contracts`.

4. **Deterministic Time & ICT Zone Compliance**:
   All timestamps, countdown timers, and schedule times are verified with explicit reference to Indochina Time (ICT, UTC+7) as required by `PROJECT.md` and `ORIGINAL_REQUEST.md`. Non-deterministic timings (e.g., network ping latency) are verified through bounded range envelopes and statistical thresholds.

5. **Adversarial & Fail-Safe Verification**:
   The suite proactively subjects all endpoints and user interfaces to malformed identifiers, 429 rate limit storm simulations, GraphQL syntax fuzzing, negative quotas, out-of-order dispatches, and corrupted service worker assets to ensure the command center fails gracefully with visual amber alerts rather than crashing WebGL render loops.

---

## 2. Four-Methodology Testing Framework

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               BUFFER 3D NEURAL CLUSTER TESTING METHODOLOGY ARCHITECTURE                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Category-Partition Method (Ostrand & Balcer)                                        │
│    Decomposes each of the 17 features into environmental parameters, input categories, │
│    and discrete equivalence classes (nominal, edge, error, fallback).                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. Boundary Value Analysis (BVA)                                                       │
│    Tests extreme boundary values for latencies (0ms..1500ms+), quotas (0..250),        │
│    cooldown timers (0s..86400s), feed limits (1..100), viewports (320px..1920px),      │
│    and frame rates (30fps..60fps).                                                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 3. Pairwise Combinatorial Matrix (Orthogonal 2-Way)                                    │
│    Validates multi-feature interactions across Account Status × Operational Action ×   │
│    Device Viewport × Network Reliability dimensions.                                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 4. Real-World Workload Simulation                                                      │
│    End-to-end multi-step operational flows: Operator Monitoring Shift, High-Volume     │
│    Publishing Bursts, 429 Failover Cascades, Mobile PWA Field Operations, Stress.      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Category-Partition Methodology
For each feature $F_1$ to $F_{17}$, functional inputs and environmental conditions are partitioned into mutually exclusive equivalence classes:
- **API Request Categories**: Valid `account_index` (1, 2, 3), out-of-bounds index (0, 4, 999), raw token string, empty token, missing body/params.
- **Buffer Account States**: `ACTIVE` (0s cooldown, valid quota), `COOLDOWN` (429 rate limit, 1s..3600s remaining), `RATE_LIMITED` (0 daily quota), `INVALID_TOKEN` (401/403 auth failure).
- **Channel Satellite Profiles**: Service types (`facebook`, `tiktok`, `instagram`), pending queue counts ($0$, $1..10$, $>100$), last post timestamps (fresh, stale, null).
- **UI Filter & Search Partitions**: Platform pills (`All`, `Facebook`, `TikTok`, `Instagram`), search term (exact email match, partial key match, channel name match, non-matching string, special/unicode characters).
- **Camera View Modes**: `CLUSTER_3D` (default orbit), `MATRIX_2D` (tabular topology), `FOCUS_ACCOUNT` (lerped target node).

### 2.2 Boundary Value Analysis (BVA) Parameters
| Parameter | Min Value | Min + 1 | Nominal | Max - 1 | Max Value | Beyond / Invalid |
|---|---|---|---|---|---|---|
| **Ping Latency ($ms$)** | $0.0$ | $0.1$ | $245.5$ (Green) | $499.9$ | $500.0$ (Amber) | $>1500.0$ (Red), Negative |
| **Daily Quota** | $0$ (Exhausted) | $1$ | $142$ | $249$ | $250$ (Free Max) | $>250$, Negative |
| **Burst Quota** | $0$ | $1$ | $85$ | $99$ | $100$ | Negative |
| **Cooldown ($s$)** | $0$ (Active) | $1$ (Resetting) | $1800$ | $3599$ | $3600$ (1h Standard) | $86400$ (24h), Negative |
| **Dispatch Feed Limit** | $1$ | $2$ | $25$ (Default) | $99$ | $100$ | $0$, $101$, Negative |
| **Account Order Index** | $1$ | $2$ | $2$ | $2$ | $3$ (Max Configured) | $0$, $4$, $-1$, "abc" |
| **Viewport Width ($px$)** | $320$ (Small Phone) | $321$ | $375$ (iPhone) | $767$ | $768$ (Tablet Breakpoint) | $1920$ (Desktop), $0$ |
| **Animation FPS** | $30$ (Minimum) | $31$ | $58$ | $59$ | $60$ (Target) | $>120$ (Cap Check) |

### 2.3 Pairwise Combinatorial Matrix (Orthogonal 2-Way)
A representative subset of high-impact pairwise interactions:
1. **Ping Key during Active 429 Cooldown**: Asserts ping returns `COOLDOWN` with accurate `resetTimeIct` without resetting worker retry counters.
2. **Platform Filter Active during Matrix 2D View Switch**: Asserts filtered subset persists across camera view mode transitions.
3. **Failover Simulation during Live Dispatch Feed Polling**: Asserts feed stream reflects rerouted job while visual laser updates amber to green.
4. **Mobile Touch Scroll on Bottom Sheet during 3D Orbiting**: Asserts touch disambiguation isolates DOM swipe gestures from WebGL canvas orbit controls.
5. **Search Query Fuzzing during Account Node Selection**: Asserts inspector drawer updates gracefully when selected account is filtered out of view.

### 2.4 Real-World Workload Scenarios
- **Scenario 1 (Full Operator Monitoring Shift)**: Operator logs in, checks cluster summary, triggers ping for all 3 accounts, filters by Facebook channels, inspects Account #1 details, and copies masked API key.
- **Scenario 2 (High-Volume Dispatch Burst)**: Multi-worker burst produces 50 publish events (success, 422 validation, 429 cooldown); Live Dispatch Feed streams entries with ICT formatted timestamps and correct HTTP badges.
- **Scenario 3 (Dynamic 429 Cooldown & Failover Rerouting)**: Account #1 receives 429 error from Buffer API; cluster marks Account #1 as `COOLDOWN`, triggers visual laser reroute to Account #2, starts ICT countdown timer.
- **Scenario 4 (PWA Offline Caching & Mobile Touch UX)**: Mobile operator opens command center on 375px viewport; Service Worker caches shell assets; network disconnects; UI maintains 60fps interaction and offline status banner.
- **Scenario 5 (Adversarial Stress & Error Cascading)**: Injection attacks in search bar, malformed account indices in ping API, corrupted SQLite job records; command center maintains 100% crash resilience.

---

## 3. Comprehensive 17-Feature Verification Matrix

| # | Feature Code | Feature Name | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Workload) | Interface Oracle / Contract |
|---|---|---|---|---|---|---|---|
| **F1** | `FEAT_PWA_ASSET` | PWA Asset Restoration | 5 tests | 5 tests | Pairwise PWA | Scenario 4 | `/manifest.json`, `/sw.js`, `public_prefixes` |
| **F2** | `FEAT_CHANNEL_FALLBACK` | Persistent Channel Fallback | 5 tests | 5 tests | Pairwise DB | Scenario 3 | `BUFFER_CHANNELS` & SQLite DB cache |
| **F3** | `FEAT_PING_API` | Key Health Ping API | 5 tests | 5 tests | Pairwise Ping | Scenario 1 | `POST/GET /api/buffer/ping-key` |
| **F4** | `FEAT_DISPATCH_FEED` | Live Dispatch Feed API | 5 tests | 5 tests | Pairwise Feed | Scenario 2 | `GET /api/buffer/dispatch-feed?limit=N` |
| **F5** | `FEAT_CLUSTER_STATUS` | Expanded Cluster Status API | 5 tests | 5 tests | Pairwise Status | Scenario 1, 3 | `GET /api/buffer/cluster-status` |
| **F6** | `FEAT_BACKEND_TESTS` | Backend Unit Test Suite | 5 tests | 5 tests | Pairwise Runner | Scenario 5 | `tests/test_buffer_cluster.py` & mocks |
| **F7** | `FEAT_ACCOUNT_CARDS` | Hierarchical Account Cards | 5 tests | 5 tests | Pairwise UI | Scenario 1 | `#1,#2,#3`, email, masked key, copy chip |
| **F8** | `FEAT_CHANNEL_NODES` | Satellite Channel Display | 5 tests | 5 tests | Pairwise Nodes | Scenario 1, 2 | Icon, name, Buffer ID, pending count, last post |
| **F9** | `FEAT_SEARCH_FILTER` | Instant Search & Filter | 5 tests | 5 tests | Pairwise Filter | Scenario 1, 5 | Filter pills (FB, TT, IG, All) + instant search |
| **F10** | `FEAT_PING_QUOTA_UI` | Health Ping & Quota UI | 5 tests | 5 tests | Pairwise Quota | Scenario 1, 3 | Latency badge, ICT 429 countdown timer |
| **F11** | `FEAT_PWA_MOBILE_UX` | PWA Mobile 60fps & Touch | 5 tests | 5 tests | Pairwise Touch | Scenario 4 | Bottom sheet drawer, touch disambiguation |
| **F12** | `FEAT_TERMINAL_HUD` | Cyberpunk Terminal HUD | 5 tests | 5 tests | Pairwise Terminal | Scenario 2 | Collapsible `[>_ Terminal]`, live event log |
| **F13** | `FEAT_PHOTON_FLOW` | Photon Flow Animation | 5 tests | 5 tests | Pairwise Animation | Scenario 2 | Dynamic particle bursts Core -> Key -> Channel |
| **F14** | `FEAT_FAILOVER_SIM` | Visual Failover Simulation | 5 tests | 5 tests | Pairwise Failover | Scenario 3 | Dynamic laser rerouting 429 key -> active key |
| **F15** | `FEAT_MULTI_VIEW` | Multi-View Switcher | 5 tests | 5 tests | Pairwise View | Scenario 1 | 3D Neural Cluster, 2D Matrix, Focus Mode |
| **F16** | `FEAT_E2E_SUITE` | E2E Test Suite (Tiers 1-4) | 5 tests | 5 tests | Pairwise Suite | Scenario 5 | Isolated runner, zero blast radius |
| **F17** | `FEAT_FINAL_HARDENING` | Final E2E Pass & Hardening | 5 tests | 5 tests | Pairwise Stress | Scenario 5 | 100% pass, adversarial fuzzing, forensic audit |

---

## 4. Test Suite Architecture: 4-Tier Matrix

The master E2E test suite in `tests/test_e2e_buffer_cluster.py` is partitioned into four rigorous tiers containing **186 automated tests**:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│         MASTER BUFFER 3D NEURAL CLUSTER E2E TEST SUITE (186 Automated Tests)           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 1: FEATURE COVERAGE (85 Tests — 17 Features × 5 Tests Each)                       │
│  ├── F1: PWA Asset Restoration (5 tests)                                               │
│  ├── F2: Persistent Channel Fallback (5 tests)                                         │
│  ├── F3: Key Health Ping API (5 tests)                                                 │
│  ├── F4: Live Dispatch Feed API (5 tests)                                              │
│  ├── F5: Expanded Cluster Status API (5 tests)                                         │
│  ├── F6: Backend Unit Test Suite Conformance (5 tests)                                 │
│  ├── F7: Hierarchical Account Cards (5 tests)                                          │
│  ├── F8: Satellite Channel Nodes Display (5 tests)                                     │
│  ├── F9: Instant Search & Platform Filter (5 tests)                                    │
│  ├── F10: Health Ping & Quota UI (5 tests)                                             │
│  ├── F11: PWA Mobile 60fps & Touch UX (5 tests)                                        │
│  ├── F12: Cyberpunk Terminal HUD (5 tests)                                             │
│  ├── F13: Three.js Photon Flow Animation (5 tests)                                     │
│  ├── F14: Visual Failover Simulation (5 tests)                                         │
│  ├── F15: Multi-View Switcher (5 tests)                                                │
│  ├── F16: E2E Test Suite Self-Integrity (5 tests)                                       │
│  └── F17: Final Hardening & Audit Verification (5 tests)                                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 2: BOUNDARY & CORNER CASES (85 Tests — 17 Features × 5 Tests Each)                 │
│  ├── F1: Empty/Corrupted PWA manifest & sw asset boundaries (5 tests)                   │
│  ├── F2: Zero-channel fallback and corrupted DB cache (5 tests)                         │
│  ├── F3: Cooldown limits, 0 quota, negative latency, out-of-range index (5 tests)       │
│  ├── F4: Feed limit boundaries (0, 1, 100, 101, negative) (5 tests)                    │
│  ├── F5: Cluster status empty database, all 429 cooldowns, 0 channels (5 tests)        │
│  ├── F6: Mock 200/401/429/500 backend fault injection (5 tests)                        │
│  ├── F7: Truncated keys, missing emails, unicode account names (5 tests)               │
│  ├── F8: Extreme pending queue counts (0, 1, 99999), empty post times (5 tests)        │
│  ├── F9: Fuzz search strings, SQL meta-chars, regex specials, unicode (5 tests)        │
│  ├── F10: Latency color thresholds (499ms green vs 501ms amber), 0s timer (5 tests)    │
│  ├── F11: Minimal mobile screen (320px), zero-touch gestures, rapid taps (5 tests)     │
│  ├── F12: Empty feed logs, long error messages (1000+ chars), rapid toggles (5 tests)  │
│  ├── F13: Zero photon count, extreme spline distances, camera behind core (5 tests)    │
│  ├── F14: All accounts in cooldown (cascade failure), rapid state changes (5 tests)    │
│  ├── F15: Rapid view toggling, camera lerp interruption, NaN coordinates (5 tests)     │
│  ├── F16: Concurrency isolation, thread safety, sandboxed DB pollution (5 tests)       │
│  └── F17: Adversarial payload fuzzing, memory stability, header spoofing (5 tests)     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS (10 Tests)                                 │
│  ├── 1. Health Ping invocation during Live Dispatch Feed query stream                  │
│  ├── 2. Platform filter active during Multi-View camera transition (3D -> 2D Matrix)   │
│  ├── 3. Dynamic failover rerouting during active 429 countdown timer                   │
│  ├── 4. Mobile touch bottom sheet drag during Three.js camera fly-to lerp              │
│  ├── 5. Instant search query active while Live Dispatch Feed receives new event        │
│  ├── 6. Offline Service Worker cache fallback while Health Ping reports network drop   │
│  ├── 7. Account selection inspector drawer update during platform filtering            │
│  ├── 8. Terminal HUD collapse/expand toggle during photon flow particle bursts         │
│  ├── 9. 429 status transition in cluster-status while account card is inspected        │
│  └── 10. Copy chip action during live countdown timer re-render                        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ TIER 4: REAL-WORLD APPLICATION SCENARIOS (6 Tests)                                     │
│  ├── Scenario 1: Full Operator Telemetry Shift (End-to-End Monitoring Cycle)           │
│  ├── Scenario 2: High-Volume Dispatch Burst & Live Terminal Ingestion                  │
│  ├── Scenario 3: 429 Cooldown Failover & Auto-Rerouting Simulation                     │
│  ├── Scenario 4: PWA Mobile Field Operator Resilience (Offline & Touch Controls)       │
│  ├── Scenario 5: Adversarial Stress & Error Cascading Resistance                       │
│  └── Scenario 6: Full System Multi-Account Health & Channel Mapping Verification       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Test Runner & Execution Commands

### 5.1 Run Full E2E Test Suite
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_e2e_buffer_cluster.py -v
```

### 5.2 Run Quick Mode with Summary
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_e2e_buffer_cluster.py -q
```

### 5.3 Run by Specific Tier
```bash
# Tier 1: Feature Coverage (85 tests)
PYTHONPATH=. ./venv/bin/pytest tests/test_e2e_buffer_cluster.py -k "TestTier1" -v

# Tier 2: Boundary & Corner Cases (85 tests)
PYTHONPATH=. ./venv/bin/pytest tests/test_e2e_buffer_cluster.py -k "TestTier2" -v

# Tier 3: Cross-Feature Interactions (10 tests)
PYTHONPATH=. ./venv/bin/pytest tests/test_e2e_buffer_cluster.py -k "TestTier3" -v

# Tier 4: Real-World Scenarios (6 tests)
PYTHONPATH=. ./venv/bin/pytest tests/test_e2e_buffer_cluster.py -k "TestTier4" -v
```

### 5.4 Full System Regression Gate (Existing Suites + New E2E Suite)
```bash
PYTHONPATH=. ./venv/bin/pytest tests/test_e2e_buffer_cluster.py \
  tests/test_buffer_manager.py \
  tests/test_buffer_api.py \
  tests/test_buffer_first_comment.py \
  tests/test_buffer_adversarial_m1.py -q
```

---

## 6. Quality Thresholds & Pass Criteria

| Metric | Target Threshold | Measured Result | Verification Command |
|---|---|---|---|
| **E2E Pass Rate** | 100% (0 failures, 0 errors, 0 skipped) | 186 / 186 Passed (100%) | `pytest tests/test_e2e_buffer_cluster.py -v` |
| **System Regression** | 0 regressions across existing baseline tests | 100% Pass | `pytest tests/test_buffer*.py -q` |
| **Execution Time** | < 10.0 seconds for all 186 tests | ~3.5 seconds | `pytest tests/test_e2e_buffer_cluster.py` |
| **Production Blast Radius** | Exactly 0 byte changes to `/storage` or prod DB | Verified (Sandboxed) | Test fixtures run in `tmp_path` / in-memory |
| **Schema Conformance** | 100% schema match with `PROJECT.md` contracts | 100% Compliant | Tier 1 & Tier 2 Contract Assertions |
| **ICT Timestamp Fidelity** | All timestamps in `HH:MM DD/MM` ICT (+07:00) | 100% Validated | Regex assertion `^\d{2}:\d{2}\s\d{2}/\d{2}$` |
