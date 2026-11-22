# TASK-062 — CapCut live agent supervisor

## Metadata
| Field | Value |
|---|---|
| ID | TASK-062 |
| Status | Verified — Anti sign-off / Claude handoff pending |
| Priority | P1 |
| Executor | Codex — owner trực tiếp yêu cầu triển khai 2026-11-18 |
| Related Plan | PLAN-176 |
| Related Decisions | DECISION-005, ADR-066, ADR-067 |

## Objective
Run a persistent, read-only campaign supervisor that detects meaningful changes to the exact CapCut trial cohort and produces separate measurement, conversion, and content-specialist notes promptly.

## Acceptance Criteria
- [x] Persistent worker observes the Store SQLite using `mode=ro`; business DB schema and customer flow are not changed.
- [x] Exact trial source and product #2 are monitored; events are aggregate-only and deduplicated across poll ticks/restarts.
- [x] Three specialist roles run only when a new meaningful aggregate event is detected; no model call while the snapshot is unchanged; output is suggestions only.
- [x] Missing DB, read errors, AI errors, and worker restarts fail closed without reporting false zero or creating duplicate alerts.
- [x] Focused tests cover exact source, delayed source write, events, dedupe/restart, privacy, and mocked AI.
- [x] PM2 process is isolated from existing workers, verified online, and owner-facing 15-minute heartbeat reads its sanitized report.

## Out of Scope
No customer-facing post/reply/DM/broadcast, purchase/QR/FatCat/SePay operation, price/stock/queue mutation, bot-flow change, auto-healing, free-form shell, production DB write/schema, quota change, or commit/push.

## Verification Proof
- 247 related tests passed in44.68s; Ruff, py_compile, ecosystem syntax and diff check PASS.
- PM2 `CapCut_Agent_Supervisor` online (PID242927, restart count3 deliberate reloads), saved in PM2 dump; poll5s, heartbeat15m. Sidecar separate from Store DB, source DB mode=ro.
- Unit/runtime tests cover delayed source, exact source, admin filter, first-marker semantics, QR status changes, delivered/refund, missing DB fail-closed, privacy, dedupe/restart, concurrency flock, burst coalescing, provider fallback and partial resume.
- Live smoke through real AI facade on actual aggregate in temp sidecar produced 3 suggestion roles with no customer/public action. Production source has no real trial cohort event yet; sidecar rollout field event ignored after normalization.
- **Execution Done. Cần Claude Code verify + handoff.**

### Latest live check — 18/11/2026 23:41 ICT
- `runtime-proof.json`: supervisor PID242927 online, PM2 unstable restarts0, fresh heartbeat/no error, scan unchanged, current business events0. Only sidecar event is the ignored rollout-shape record.
- PM2 logs show three deliberate deployment reloads; no crash-loop evidence. Worker polls every5s while PM2/host is running; chat heartbeat remains15m.

### Final operational note
A rollout-only empty QR-field shape change emitted3AI suggestions on all-zero evidence before compatibility normalization. Full evidence remains preserved and row marked ignored; fix + regression test prevents recurrence. It triggered no customer-facing action. No organic trial event has yet called production specialist path. Forced termination can repeat unfinished role at-least-once; not exactly-once.

**Execution Done. Cần Claude Code verify + handoff.** Anti sign-off pending; task remains active.
