# ToolsAuto Agent Workspace v3

Hệ thống cộng tác 3 agent cho ToolsAuto — rõ vai, đúng quy trình, không mất context.

---

## Mục tiêu
- Agent làm đúng việc, đúng vai
- Agent sau hiểu ngay trạng thái mà không cần giải thích lại
- Không loạn hệ thống khi scale

---

## Ba Agent & Vai trò

### Antigravity (Anti) — Orchestrator
- **Làm**: Intake, Research, Planning, Assign, ADR, Governance
- **Không làm**: Execute code, viết logic
- **Trigger**: Mọi task đều bắt đầu từ Anti

### Codex — Backend & System Engineer
- **Làm**: Implement core logic, adapter, worker, debug runtime
- **Không làm**: Tự ý plan, tự assign task cho mình, sửa UI/template
- **Trigger**: Khi Anti tạo PLAN với `Executor: Codex`

### Claude Code — UX, Refactor & Quality
- **Làm**: Template, CSS, UX review, refactor readability, docs, handoff
- **Không làm**: Viết adapter/worker/core logic, execute khi chưa có PLAN
- **Trigger**: Khi Anti tạo PLAN với `Executor: Claude Code`, hoặc sau khi Codex xong để review + handoff

---

## Flow tóm tắt

```
User Request → Anti (Intake + Plan) → Codex hoặc Claude Code (Execute + Verify) → Claude Code (Handoff)
```

Chi tiết từng phase: xem [WORKFLOW.md](WORKFLOW.md)

---

## Cấu trúc thư mục

```
agents/
  README.md            ← File này — overview + roles
  WORKFLOW.md          ← Quy trình 7 phase chi tiết + Inter-agent rules
  PLAN_SYSTEM.md       ← Vòng đời Plan, khi nào cần, Plan vs Task
  PROMPT_SYSTEM.md     ← Prompt chuẩn cho từng agent role
  RULES.md             ← Bộ luật kỷ luật (DB, Git, Browser, Resources)
  QUICK_START.md       ← Lệnh copy-paste dùng ngay

  plans/
    active/            ← Plan đang thực thi (có Executor được assign rõ)
    archive/           ← Plan Done hoặc Cancelled

  tasks/
    archive/           ← Task Done

  handoffs/
    current-status.md  ← Trạng thái hệ thống (cập nhật mọi checkpoint)

  decisions/
    README.md          ← Hướng dẫn viết ADR
    ADR-NNN-*.md       ← Quyết định kiến trúc

  templates/
    plan.template.md
    task.template.md
    handoff.template.md
    adr.template.md
    audit.template.md
```

Root level: `CLAUDE.md` — Claude Code tự động đọc khi bắt đầu mỗi phiên.

---

## Quy tắc thép (không ngoại lệ)

1. **No Plan No Code**: Không 1 dòng code nào trước khi PLAN tồn tại trong `plans/active/`
2. **Zero-Autonomous-Execution**: Codex và Claude Code KHÔNG tự execute khi chưa được Anti assign
3. **Proof Required**: Verify phải có bằng chứng thực tế — log, output, command result
4. **Handoff Mandatory**: Mọi phiên làm việc PHẢI kết thúc bằng update `current-status.md`
5. **Checkpoint Rule**: Cập nhật `current-status.md` khi bắt đầu task, đổi phase, trước sửa logic lớn, sau verify milestone
6. **Conflict Resolution**: Mâu thuẫn giữa agents → Anti quyết định

---

## Templates bắt buộc

Mọi agent phải dùng template từ `agents/templates/`:
- `plan.template.md` — cho mọi PLAN
- `task.template.md` — cho mọi TASK
- `handoff.template.md` — cho mọi Handoff
- `adr.template.md` — cho mọi ADR
- `audit.template.md` — cho Audit request
