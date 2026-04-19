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
| **Git Status** | Clean (all TASK-007 + TASK-008 committed & pushed) |
| **Last Major Work** | TASK-008: Log Optimization — DONE & Archived |

---

## Active Tasks

- ⚡ **TASK-009**: Fix Settings Reset on Deploy (New → Assigned to Codex)
  - **PLAN**: PLAN-009
  - **ADR**: DECISION-002
  - **Scope**: Dời `ai_persona.json` → `storage/db/config/`, cập nhật `.gitignore`, thêm rule vào `CLAUDE.md`

---

## Done This Session (Verified)

- ✅ **TASK-007 DONE**: 9Router Gateway phục hồi, Circuit Breaker CLOSED
- ✅ **TASK-008 DONE & Archived**: Log Optimization — Dual-Stream + IDLE demote + Prefix + UI Colorize
- ✅ Legacy `worker.py` removed, archived to `storage/archive_legacy/`

---

## Unfinished

- ⏳ **TASK-009** chờ Codex thực thi PLAN-009.

---

## Blockers / Risks

- ⚠️ HTTP 429 từ model endpoint: provider rate-limit, không phải lỗi hệ thống.

---

## Next Action

1. **Codex**: Đọc `PLAN-009` và thực thi 4 bước (đổi path, .gitignore, CLAUDE.md, quét codebase).
2. **Antigravity**: Review & sign-off PLAN-009 sau khi Codex hoàn tất.

---

## Workflow Reference

- Quy trình: `agents/WORKFLOW.md`
- Prompt chuẩn: `agents/PROMPT_SYSTEM.md`
- Claude Code tự động đọc: `CLAUDE.md` (root)
