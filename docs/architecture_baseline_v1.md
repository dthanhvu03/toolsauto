# Architecture Baseline v1: Automation Control Panel

## I. Executive Summary

**System Classification**: Deterministic State-Controlled Automation Engine
**Problem Solved**: Unstable, opaque personal automation scripts failing silently, leaving orphaned browser processes, queueing blocked actions against banned accounts, and losing transactional integrity.
**Architectural Significance**: Implements enterprise-grade backoffice disciplines—atomic locking, bounded state machines, and decoupled routing—upon a monolithic, personal-scale footprint (SQLite/FastAPI/Playwright).
**Maturity Level**: Professional Personal Grade

## II. Architectural Overview

The system design enforces strict separation of concerns to guarantee background execution stability without locking the user interface.

- **Control Plane (HTTP/UI)**: FastAPI paired with HTMX and Tailwind. It operates as a stateless proxy, casting HTTP mutations into the Service layer and dynamically swapping HTML fragments without hard page reloads.
- **Worker Plane**: A decoupled, continuous asynchronous event loop. It polls the database, claims jobs atomically, and manages its own internal heartbeat telemetry.
- **Adapter Layer**: Domain-isolated contract implementations (e.g., Facebook Adapter). Adapters execute Playwright instructions blindly, abstracted from system queues, UI interactions, and database sessions.
- **Data Layer**: SQLite initialized in Write-Ahead Logging (WAL) mode. This guarantees non-blocking concurrent reads (UI dashboard) while the Worker process executes single-writer transaction claims.
- **Account Session Layer**: Strictly isolated persistent profile directories mapped to a multi-tiered connection state (`NEW`, `LOGGING_IN`, `ACTIVE`, `INVALID`). Credentials are strictly out-of-scope; users manually mediate headed authentication.
- **Health & Observability**: Passive boundary monitors. Fast, `index=True` aggregations compute system vitality (orphans, failure rates, stale heartbeats) and emit deterministic degradation signals.

## III. State Machine Discipline

- **Job State Transitions**: Fixed linear vectors (`PENDING` -> `RUNNING` -> `DONE` | `FAILED`).
- **Account State Transitions**: Lifecycle constrained (`NEW` -> `LOGGING_IN` -> `ACTIVE` <-> `INVALID`). Limits are enforced numerically.
- **Enforcement Mechanisms**: The API Router relies 100% on the `Service` layer to compute transitions. Hard boundaries raise native Python `ValueError` exceptions avoiding HTTP 500s.
- **Atomic Update Strategy**: Transitions execute via single SQLite queries (`UPDATE ... WHERE status = ...`) rather than `SELECT` -> `UPDATE` patterns, structurally eliminating database race conditions on manual actions.
- **Event Logging**: Critical actions populate an append-only `JobEvent` ledger bridging the gap between automated telemetry and manual admin overrides.

## IV. Concurrency & Stability Analysis

- **SQLite WAL Suitability**: Highly optimal. The UI represents a high-read vector, while the Worker represents a low-volume, high-value write vector. WAL prevents locked dashboard views during worker claims.
- **Atomic Claim Safety**: The `QueueService` isolates claims by embedding filtering limits into a single transaction.
- **Worker Heartbeat Logic**: Separates system-wide availability (`SystemState.heartbeat_at`) from execution validity (`Job.last_heartbeat_at`).
- **Multi-Account Execution**: Strictly safe. Profile boundaries operate in separate directories. Isolation rules dictate a single account cannot poison the global queue if it hits a fatal exception.

## V. Operational Load Scenario Modeling

- **Low Load (10 jobs/hour, 1 Account)**: Operates near trivially. UI remains highly responsive < 50ms, worker idles safely.
- **Moderate Load (50 jobs/hour, 5 Accounts)**: SQLite WAL manages read/write locks gracefully. Bounded `cooldown_seconds` forces the dispatcher to interleave account execution preventing localized rate-limit bans against adapters safely.
- **Stress Scenario (Worker Crash mid-RUNNING)**: If the OS SIGKILLs the Worker process while a job is `RUNNING`:
  - The OS destroys the active Playwright subprocess.
  - The `SystemState.heartbeat_at` ages out, triggering the `/health` degraded UI alert.
  - The `Job.last_heartbeat_at` hits the orphan threshold.
  - Upon the next manual or automated worker reboot, the Orchestrator instantly sweeps the Orphan exactly back to `PENDING` ensuring zero lost state.

## VI. Failure Handling Strategy & Matrix

| Failure Type                 | Detection Mechanism                         | Mitigation Strategy                                      | Residual Risk                                                      |
| :--------------------------- | :------------------------------------------ | :------------------------------------------------------- | :----------------------------------------------------------------- |
| **Browser Process Segfault** | Job Heartbeat Timeout (`last_heartbeat_at`) | Orphan Sweeper resets to `PENDING` on reboot             | Partial duplicate action (if crashed post-click but pre-DB-commit) |
| **Adapter Selector Drift**   | UI Wait Timeout -> `PlaywrightTimeoutError` | Marked `FAILED`, emits `RETRYABLE` event                 | Requires manual code redeployment to fix Selectors                 |
| **Account Ban/Lockout**      | `login_status` check fails before execution | Circuit Breaker triggers (`INVALID`), marks Account dead | 0% risk to other parallel accounts                                 |
| **Concurrent UI Toggles**    | Atomic `UPDATE` returns 0 affected rows     | API catches `ValueError`, prevents overlap               | UI race condition briefly showing stale state                      |

## VII. Observability & System Visibility

- **Health Endpoint**: A highly mature `/health` JSON aggregation bounding `psutil` infrastructure metrics with logical business objects.
- **Degraded Logic**: Removes ambiguity. The system is deterministically `degraded` if specific rules are broken (11+ failures, 1+ orphans, dead worker).
- **Job-Level Heartbeats**: Grants real-time introspection into long-running synchronous Playwright operations.

## VIII. Security & Risk Posture

- **Credential Safety**: Maximum possible score. By shifting to user-interactive headless injection via `content/profiles`, the database never stores passwords.
- **Execution Boundary Safety**: Adapters securely interact via contracts and do not hold database session keys or cross-account access.
- **Browser Persistence Risks**: Profile cache directories remain unencrypted on disk. A compromised host OS grants total access to authenticated session cookies.

## IX. System Maturity Assessment

| Category                 | Score    | Justification                                                                         |
| :----------------------- | :------- | :------------------------------------------------------------------------------------ |
| Architecture Clarity     | **9/10** | Strict separation of Control, Data, and Adapter layers ensures clear boundaries.      |
| State Machine Discipline | **9/10** | Atomic UI guardrails prevent impossible state injections completely.                  |
| Failure Tolerance        | **8/10** | Circuit breakers cleanly isolate poison-pill jobs without crashing the queue.         |
| Concurrency Safety       | **8/10** | SQLite WAL and `RETURNING` locks handle local vertical scaling gracefully.            |
| Observability            | **7/10** | Hardcoded JSON API exists, but lacks historical scrape targets (Prometheus/Grafana).  |
| Risk Containment         | **8/10** | Profiles separated cleanly at the filesystem level.                                   |
| Extensibility            | **7/10** | Adapters use strict Contracts, making new Platforms (Instagram) easy to mock.         |
| Maintainability          | **8/10** | Python exceptions are properly captured and bounded, avoiding 500-error tracing hell. |

**Overall Maturity Classification**: **Professional Personal Grade**

## X. Gaps to "Self-Healing Orchestration Platform"

To fully ascend to a self-healing platform, the following updates remain:

1.  **External Supervisor**: Requires a daemon like `pm2` or `systemd` to automatically reboot the worker utilizing the `/health` endpoint as a liveness probe.
2.  **Idempotency Hardening**: Implementing synchronous "truth checks" (e.g. `external_post_id`) against the external platform prior to recovering an Orphaned task.
3.  **Memory Threshold Restart**: Forcing a graceful Worker exit if `psutil` memory balloons past a 1GB threshold.

## XI. Architectural Verdict

This system is a **Deterministic State-Controlled Automation Engine**.
It acts autonomously, possesses native awareness of its own bounds, structurally isolates execution footprints, aggressively self-regulates traffic using circuit breakers, and exposes a decoupled, stateless visualization plane. It brings production-grade backend disciplines to a headless browser footprint safely.
