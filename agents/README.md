🚀 ToolsAuto Agent Collaboration Workspace (v2)

Hệ thống cộng tác đa-agent cho việc xây dựng và vận hành các automation/backend system một cách ổn định – rõ ràng – có thể bàn giao liên tục.

🎯 Mục tiêu

Workspace này tồn tại để đảm bảo:
- Agent làm đúng việc
- Agent sau hiểu ngay việc đang làm
- Không mất context qua từng phiên
- Không “loạn hệ thống” khi scale

📂 Structure
```text
agents/
  PLAN_SYSTEM.md    <- Quy định về lập kế hoạch
  PROMPT_SYSTEM.md  <- "Linh hồn" & thái độ của AI
  RULES.md          <- "Bộ luật" kỷ luật dự án (An toàn DB, Git, Python)
  WORKFLOW.md       <- Quy trình tác nghiệp (Research -> Plan -> Execute)
  plans/
    active/
    archive/
  tasks/
  handoffs/
  decisions/
  templates/
```

### Ý nghĩa
- **PROMPT_SYSTEM.md**: Định nghĩa vai trò và cách AI phản hồi.
- **RULES.md**: Tổng hợp các quy tắc an toàn kỹ thuật (từ .agents/rules/).
- **plans/active**: kế hoạch đang dùng.
- **plans/archive**: kế hoạch cũ (không xóa).
- **tasks/**: danh sách công việc cụ thể.
- **handoffs/**: trạng thái hiện tại + bàn giao giữa các phiên.
- **decisions/**: các quyết định kỹ thuật quan trọng (ADR).
- **templates/**: các mẫu tài liệu chuẩn Pro.

### 🧩 Templates
Tất cả Agent bắt buộc sử dụng template từ `agents/templates/`:
- `plan.template.md`
- `task.template.md`
- `handoff.template.md`
- `adr.template.md`
- `audit.template.md`

🎭 Team Roles

### 🛠 Codex — Backend & System Engineer
- **Focus**: core logic, adapter, runtime / worker, performance & stability.
- **Responsibility**: implement logic, debug sâu, đảm bảo system chạy ổn định.

### 🎨 Claude — UX, Refactor & Quality
- **Focus**: readability, interaction flow, documentation, refactor an toàn.
- **Responsibility**: làm code dễ hiểu, viết handoff rõ, kiểm tra edge cases.

### 🛸 Antigravity — Orchestrator
- **Focus**: planning, prioritization, coordination.
- **Responsibility**: chia nhỏ task, giữ hướng dự án, resolve conflict.

⚙️ Operating Flow
`Research → Plan → Execute → Verify → Handoff`

### Core Rules
1. **Rule Compliance**: Mọi hành động phải tuân thủ nghiêm ngặt **[RULES.md](file:///home/vu/toolsauto/agents/RULES.md)**.
2. **No Plan, No Code**: Không execute nếu chưa có plan rõ được phê duyệt.
3. **Traceability**: Mọi task đều phải được link về plan mẹ.

👉 Nếu có mâu thuẫn giữa các quy tắc → **Antigravity quyết định**.

End of document.
