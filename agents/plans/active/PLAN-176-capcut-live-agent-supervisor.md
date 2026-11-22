# PLAN-176 — CapCut live agent supervisor

> **Owner stopped20/11/2026 — PLAN185:** chủbot hủy toàn bộ agent tăngtrưởng để chọn hướng mới dựa research. Runtime2processstopped/PID0,growth.enabled=false,heartbeatđãxóa; khôngtựbậtlại. Giữcode/history/proof cũ bên dưới. Statusnàythaythế mọi chỉdẫn tiếp tục chạy nền trong PLAN.

## Metadata
| Field | Value |
|---|---|
| ID | PLAN-176 |
| Status | In Progress — implementation/verification |
| Executor | Codex — direct owner authorization 2026-11-18 |
| Related Task | TASK-062 |
| Related Decisions | DECISION-005 (Phase 1 suggest-only), ADR-066, ADR-067 |
| Related Work | PLAN-172, PLAN-173, CapCut trial `threads_ai_cc18_anlinh_p1` |

## Authorization and assignment
Owner asked to build the event-driven specialist supervisor after agreeing that a 15-minute heartbeat alone is not continuous. PLAN-173 is the existing Codex assignment, currently executed; it only covers cohort reporting. This is a new bounded backend task, directly authorized by the owner. The monitor reports to the existing owner-facing Codex heartbeat; it does not become an operator for Store/Threads. A coordination note is added to PLAN-172 before implementation, per ADR-067.

## Goal
A persistent PM2 process detects changes to the exact CapCut Store cohort within a short poll interval. On new aggregate signals it creates separate measurement, conversion, and content-specialist analyses through the existing `AIUseCases` facade. Analysis is evidence-bound, suggestion-only, and visible in sanitized local artifacts; the existing 15-minute heartbeat surfaces new events in chat.

## Scope
- Add exact-source filtering to `cashback_bot/store_campaign.py` without changing its current default prefix behavior.
- Add a standalone supervisor module under `app/features/threads/growth/` and a three-role prompt/analysis helper. Use a separate local sidecar under `storage/db/config/` for dedupe/cooldown state; never write the Store SQLite.
- Watch source/customer/product-step/QR/paid/delivered/refund aggregates for product #2 and `threads_ai_cc18_anlinh_p1`. Use a read-only SQLite snapshot and a bounded overlapping lookback so a delayed `src:` write is not lost. Order creation and delivery/refund updates are distinct.
- Emit aggregate-only events and role reports under `reports/capcut-20261118/agent-supervisor/`; no names, usernames, Telegram IDs, credentials, raw SQL rows, or account items.
- Add a dedicated PM2 entry and start only that new process after tests pass. Do not restart Store, Threads_Growth, Dashboard, or any unrelated process.
- Update the existing 15-minute heartbeat prompt to surface only newly created supervisor events; unchanged ticks should remain quiet.

## Non-goals and safety boundary
- No customer or public messages, automatic publishing, campaign expansion, queue/config/price/stock changes, purchases, QR creation, vendor calls, or account/session operation.
- No database migration or write to production business tables. No free-form shell, auto-healing, or approval/action queue.
- No AI call on an unchanged snapshot. Coalesce short bursts, persist idempotent event keys, rate-limit specialist batches, and fall back to deterministic aggregate status when the provider is unavailable.
- The three roles are specialist analyses on each qualifying event, not three model processes continuously generating tokens. The watcher polls continuously; Codex chat delivery follows the existing 15-minute heartbeat.

## Implementation Steps
1. Confirm data timestamps, source write ordering, service launch convention, and existing AI facade; record architecture and privacy boundaries.
2. Implement exact-source report support, persistent read-only watcher, isolated sidecar dedupe, aggregate event format, and three evidence-bound specialist prompts using the existing AI facade.
3. Add deterministic unit/integration tests with temporary SQLite and mocked AI; verify no LLM call on baseline/unchanged data and no PII in output.
4. Add one isolated PM2 process; run module and report smoke tests before starting it; verify status, logs, event dedupe, and existing processes unchanged.
5. Update owner-facing heartbeat and PLAN/TASK/current-status with actual command output and latency boundary.

## Decision Notes
- Follows DECISION-005 Phase 1: suggest-only. Rules and aggregate SQL are the source of truth; LLM hypotheses must cite aggregate evidence and confidence.
- The Store source database is SQLite. Use `mode=ro` and transaction snapshots; the separate sidecar holds only monitor fingerprints/cooldowns, not customer records.
- Near-real-time detection is bounded by polling (target <=5 seconds); Codex chat notification is bounded by the 15-minute heartbeat. Do not claim push/webhook latency.
- Existing `Threads_Growth` is not reused: it posts/replies and owns a different lifecycle. The new PM2 process must have independent code, state, logs, and kill switch.

## Verification Plan
- Unit tests: exact source vs prefix collision, user row before `src:` row, first-only product marker, QR vs paid vs delivered/refund, pending-to-done transition, restart dedupe, overlapping windows, read-only source DB, sidecar idempotency, redaction, AI mocked/errors/cooldown.
- Runtime: new PM2 process online; source DB unchanged; sidecar/event JSON has no PII; no existing PM2 process restart; heartbeat reads newest event once and is quiet without changes.
- Run `ruff`, focused pytest and `git diff --check`.

## Rollback
Stop/delete only `CapCut_Agent_Supervisor`; remove only its ecosystem entry and new supervisor modules/tests if requested. Preserve reports and sidecar until owner decides. Do not change/rollback existing bot data or flows.

## Handoff
Execution is not complete until the new worker is running and dedupe/role output are proven. Keep Anti sign-off and Claude handoff pending; do not archive or mark Done in this execution.

## Verification refinement before final deployment
- Full trial cohort is rescanned on every tick since publication, using exact source equality; this supersedes the proposed lookback and avoids delayed-source/high-watermark gaps entirely for this small cohort. Semantic aggregate changes are detected; first-step markers remain first-only, and events shorter than the poll interval or offsetting aggregate changes may not be reconstructable. No claim of per-user event stream.
- Added regression coverage file tests/test_capcut_supervisor_runtime.py, atomic status.json, dispatch flock,10s burst coalescing,60s AI batch cooldown, persisted completed roles. Added file to Scope: existing reports/capcut-20261118/measure_trial.py uses exactsource for parity with supervisor.
- Unit/integration tests use mocked AI only. Final bounded live smoke may call existing AIUseCases once for each of3roles using actualaggregate copied to a TEMPORARY sidecar with current=previous; label manual_model_smoke, never seed production sidecar or fake customers. This separately proves model routing, not business-event ingestion. No repeated role retry on failure.
- Process shutdown can be force-killed by PM2 after15s while provider call is pending; unfinished model role can run again after restart (at-least-once AIcall, not exactlyonce); completedroleoutputs persisted. No customer action exists in this worker.

## Execution proof — 18/11/2026
- Implementation: exact `source_exact=True` report filter (default prefix behavior preserved), `capcut_supervisor.py`, separate `storage/db/config/capcut_supervisor.sqlite` sidecar, aggregate JSON/status artifacts, PM2 `CapCut_Agent_Supervisor` entry. Store source remains SQLite `mode=ro`; sidecar is rejected if configured to same path as Store DB. No production schema/business-table write.
- Specialist roles: measurement, conversion, content; existing `AIUseCases.generate_text` facade, evidence aggregate only, suggest-only output. No calls on unchanged snapshots; 10s burst coalescing, 60s cooldown, sidecar `flock`, partial role resume and PM2 restart persistence. Shutdown may repeat unfinished provider role at-least-once after forced kill; completed roles persist.
- Tests: `pytest -q tests/test_capcut_supervisor.py tests/test_capcut_supervisor_runtime.py tests/test_store_campaign.py tests/test_store_bot.py tests/test_threads_growth.py tests/test_growth_funnel.py tests/test_growth_report.py` → **247 passed in 44.68s**; Ruff **All checks passed!**; py_compile PASS; `node --check ecosystem.config.js` PASS; git diff --check PASS. Independent runtime review added 6 regression tests (flock, exact source/admin filter, QR status, queue drain, fallback roles, partial resume).
- Runtime: `pm2 start ecosystem.config.js --only CapCut_Agent_Supervisor`; `pm2 save`; final status **online**, PID242927, restart count3 (three deliberate reloads while implementing; no crash loop), `exec cwd=/home/vu/toolsauto`, restart dump includes process. Existing Maintenance/Web_Dashboard/Threads_Growth statuses unchanged by final start/reload. Poll target5s; owner chat heartbeat15m.
- Real baseline: `capcut_supervisor --once` → baseline/unchanged, new_users0, product_markers0, QR0, delivered_orders0, revenue0, mature24h0/conversionnull. Production sidecar currently events `{ignored:1}`: one rollout-only QR-status-field normalization event was preserved and marked ignored after code update; it had QR status `{}` and all customer/order counts0, no production business event. No current production AI batch after final normalization.
- Bounded live model smoke: `reports/capcut-20261118/agent-supervisor/smoke/proof.json`, temporary sidecar only, actual aggregate (all counts0), 3 calls through facade; roles measurement/conversion/content all `suggestion`, fallback_roles=[], customer_or_public_actions0, production_event_inserted=false. This proves provider path only, not a real cohort event.
- Runtime proof: `agent-supervisor/runtime-proof.json` (latest read-only PM2/process/sidecar/status/smoke aggregate; no PII). `status.json` written atomically with health, poll interval, baseline counts and specialist roles.
- **Execution Done. Cần Claude Code verify + handoff.** Continuous watcher deployed; specialists are event-driven suggestions, not three permanently thinking processes. No commit/push; Anti sign-off/Claude handoff pending; keep PLAN/TASK active.

### Final post-fix verification — 18/11/2026
- Current related run after empty-QR-shape normalization:247 passed in44.68s; Ruff All checks passed; py_compile/ecosystem syntax/git diff check exit0.
- Updated runtime-proof.json at13:01VN with PM2 state, status, sidecar counts and rollout-only analysis history. Current health unchanged; last rollout field event is ignored, no current business-event row. Store DB remains unmodified by watcher.
- Transparent rollout note: before migration-normalization fix, adding empty qr_requests_by_current_status={} to existing baseline created a false schema-shape event with all customer/order counts0. That event triggered3 suggest-only specialist calls, had0 external/customer actions, and full output is preserved in smoke/rollout-qr-field-normalization.json; sidecar row preserved but ignored. semantic comparison now treats missing legacy empty QR map as {} and regression locks behavior. No further provider calls on unchanged post-fix baseline.
- Live AI smoke is separate in smoke/proof.json: actual aggregate counts copied into temp sidecar and dispatched once,3 roles suggestion,fallback0,no production event/fake customers/orders. No organic trial event has called production specialist path; deterministic event flow is covered by temp DB tests.
- Watcher survives while host/PM2 is running, polls5s; existing Codex heartbeat surfaces15m. Roles are three prompts in one Python process invoked on event, not three autonomous Codex subagent processes. Forced PM2 kill during provider call may repeat unfinished role after restart; completed roles persist.
- Latest live check at 23:41 ICT: runtime proof refreshed; PID242927 online, PM2 unstable restarts0, heartbeat fresh/no error, scan unchanged, current business events0, sidecar retains only the ignored rollout-shape event. PM2 logs show three deliberate deployment reloads.
- **Execution Done. Cần Claude Code verify + handoff.** No archive/Done, no commit/push.
