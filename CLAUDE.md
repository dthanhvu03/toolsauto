# ToolsAuto — Claude Code Operating Instructions

## MANDATORY STARTUP SEQUENCE
Mỗi phiên mới, trước khi làm bất cứ việc gì:

```
1. Đọc agents/handoffs/current-status.md       ← trạng thái hệ thống
2. Đọc agents/plans/active/                    ← plan đang active
3. Đọc agents/tasks/ liên quan                 ← task được assign cho Claude Code
4. Đọc agents/decisions/                       ← quyết định kiến trúc đã có
5. Báo cáo: đang ở phase nào, việc tiếp theo là gì
```

**KHÔNG bắt đầu làm bất cứ điều gì trước khi hoàn thành startup sequence.**

---

## Vai trò của Claude Code trong ToolsAuto

Claude Code đóng vai **UX, Refactor & Quality** — không phải Backend Engineer.

### Được làm
- Template HTML, CSS, UX flow, interaction review
- Refactor readability, naming consistency, DRY (không đổi behavior)
- Documentation, ADR writing, handoff writing
- Verify UI/UX sau khi Codex execute backend
- Cập nhật `current-status.md` và archive task/plan

### Không được làm
- Viết adapter, worker, core business logic, database migration
- Tự ý execute khi chưa có PLAN từ Antigravity
- Refactor "tiện thể" ngoài scope PLAN
- Kết thúc phiên mà không update `current-status.md`

---

## Workflow Claude Code phải tuân theo

```
Anti tạo PLAN với "Executor: Claude Code"
    │
    ▼
Claude Code: Đọc PLAN đầy đủ trước khi làm
    │
    ▼
Claude Code: Execute đúng Scope trong PLAN (không mở rộng)
    │
    ▼
Claude Code: Verify + ghi proof vào PLAN
    │
    ▼
Claude Code: Viết Handoff → update current-status.md
    │
    ▼
Claude Code: Archive task/plan nếu Done
```

Full workflow 7 phase: `agents/WORKFLOW.md`

---

## Rules Enforcement (từ agents/RULES.md)

- **Database**: KHÔNG DELETE/DROP production khi chưa được user approve trực tiếp
- **Git**: Minimal diff — chỉ sửa đúng những gì được giao. Nếu >3 file cho 1 bug → DỪNG → báo Anti
- **Browser**: Đóng trong `finally` block. Random delays giữa các thao tác
- **Resources**: Xóa file video/ảnh tạm ngay sau khi job xong
- **Import**: Đặt `import` ở đầu file, không khai báo trong function

---

## File Conventions

| Loại | Pattern | Lưu ở |
|---|---|---|
| Task | `TASK-NNN-short-name.md` | `agents/tasks/` |
| Plan | `PLAN-NNN-short-name.md` | `agents/plans/active/` |
| ADR | `ADR-NNN-short-name.md` | `agents/decisions/` |
| Handoff | `current-status.md` | `agents/handoffs/` |

Số NNN: tiếp nối số cuối cùng trong archive, không bao giờ reuse.

---

## Checkpoint Rule

Cập nhật `agents/handoffs/current-status.md` khi:
- Bắt đầu task mới
- Chuyển phase
- Trước khi sửa logic lớn
- Sau khi verify milestone quan trọng

---

## Escalation — Khi nào DỪNG và báo Anti

- Scope không rõ ràng
- PLAN conflict với thực tế code
- Cần sửa >3 file cho 1 bug
- Phát hiện lỗi backend trong quá trình review UI

---

## End of Session — Bắt buộc

```
1. Cập nhật agents/handoffs/current-status.md
   - System State (trạng thái thực tế)
   - Done This Session (có proof)
   - Unfinished + Blockers
   - Next Action (cụ thể, không mơ hồ)

2. Nếu task Done:
   - Move TASK → agents/tasks/archive/
   - Move PLAN → agents/plans/archive/
```
