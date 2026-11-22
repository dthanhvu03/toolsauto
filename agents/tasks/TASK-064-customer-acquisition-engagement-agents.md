# TASK-064 — Agent tìm khách và tương tác

| Field | Value |
|---|---|
| Status | Verified. Anti sign-off and Claude handoff pending |
| Executor | Codex — direct owner process exception 19/11/2026 |
| Plan | PLAN-178 |
| Decisions | ADR-066, ADR-067 |

## Acceptance
- [x] Acquisition filters genuine needs and revalidates the queued reply in the existing sender.
- [x] Engagement is inbound-only and scoped by account and bot. Support and financial cases are handed to the owner. An Linh DM is disabled.
- [x] Status reports work, quiet periods and errors per role using aggregate counts.
- [x] Deployment proof records the existing cadence, quotas, account roles and worker isolation.
- [x] Regression suite and production process health verified.
- [x] Existing heartbeat configuration reads the new role status on its 15-minute schedule.

## Proof
- 328 related tests passed in 31.76s. Ruff, Python compilation, ecosystem syntax and git diff --check passed.
- Read-only replay at 05:21 VN returned query_only=1 and held all 24 currently approved AI Store rows.
- PM2 PID 1149851 online after the 05:24 VN reload. At 05:27 VN status had a fresh heartbeat and both roles in quiet_hours. The first natural business activity has yet to be observed.
- Proof in reports/customer-agents/runtime-proof.json. First read-only role reports are in reports/customer-agents-20261119/.
- **Execution Done. Cần Claude Code verify + handoff.**
