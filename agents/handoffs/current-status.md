# ToolsAuto — Current Project Status

*Last updated by: Antigravity — 2026-04-19*

---

## System State
| Item | State |
|---|---|
| **Environment** | WSL Ubuntu / Python 3.10 / Direct Server |
| **Backend** | Running (manage.py serve) |
| **9Router Gateway** | ✅ ONLINE — port 20128 listening, Circuit Breaker CLOSED |
| **Git Branch** | develop |
| **Git Status** | Clean |
| **Last Major Work** | TASK-009: Fix Settings Reset on Deploy — DONE & Archived |

---

## Active Tasks

- ✅ **TASK-010 DONE**: GraphQL Sync + Caption Fix + Deploy Path Filter
  - **Status**: Archived
  - **PLAN**: PLAN-010 (Archived)

---

## Done This Session (Verified)

- ✅ **TASK-007 DONE**: 9Router Gateway phục hồi
- ✅ **TASK-008 DONE & Archived**: Log Optimization
- ✅ **TASK-009 DONE & Archived**: Fix Settings Reset on Deploy

---

## Unfinished

- ⏳ **TASK-010** Phase A/B/C chờ execution.

---

## Blockers / Risks

- ⚠️ **CRITICAL**: Deploy liên tục giết Publisher — cần Phase A (path filter) ngay lập tức.
- ⚠️ Facebook đổi DOM Reels Step 3 — caption không điền được. Cần VPS screenshot debug.

---

## Next Action

1. **Antigravity**: Thực thi PLAN-010 Phase A (deploy path filter) → commit → push.
2. **Antigravity**: Thực thi Phase C (GraphQL sync enhancement).
3. **Antigravity**: Debug DOM VPS → Thực thi Phase B (caption selector fix).

---

## Workflow Reference

- Quy trình: `agents/WORKFLOW.md`
- Prompt chuẩn: `agents/PROMPT_SYSTEM.md`
- Claude Code tự động đọc: `CLAUDE.md` (root)
