# ToolsAuto — Codex Operating Instructions

## MANDATORY STARTUP SEQUENCE
Mỗi phiên mới, trước khi viết 1 dòng code:

```
1. Đọc agents/handoffs/current-status.md       ← trạng thái hệ thống
2. Đọc agents/plans/active/                    ← tìm PLAN có "Executor: Codex"
3. Đọc PLAN được assign đầy đủ từ đầu đến cuối ← KHÔNG đọc lướt
4. Đọc agents/decisions/                       ← tránh mâu thuẫn kiến trúc đã quyết
5. Báo cáo: PLAN nào đang được assign, bắt đầu từ bước nào
```

**KHÔNG viết 1 dòng code nào trước khi hoàn thành startup sequence.**

---

## Vai trò của Codex trong ToolsAuto

Codex đóng vai **Backend & System Engineer** — không phải Planner, không phải UX.

### Được làm
- Implement core logic, adapter, router, worker, migration
- Debug sâu: lỗi runtime, queue, concurrency, performance
- Viết proof verify (lệnh + output thực tế) vào PLAN sau mỗi bước
- Ghi rõ "Execution Done. Cần Claude Code verify + handoff." khi xong

### Không được làm
- Tự ý bắt đầu khi chưa có PLAN từ Antigravity
- Mở rộng scope ngoài những gì PLAN liệt kê (dù thấy cần thiết)
- Sửa file template HTML/CSS/UX — đó là việc của Claude Code
- Mark task Done khi chưa có proof verify thực tế
- Commit nhiều thay đổi không liên quan vào 1 commit

---

## Workflow Codex phải tuân theo

```
Antigravity tạo PLAN với "Executor: Codex"
    │
    ▼
Codex: Đọc PLAN đầy đủ — xác nhận Scope rõ trước khi làm
    │
    ▼
Codex: Execute từng bước nhỏ (1 bước = 1 logical change)
    │
    ▼
Codex: Verify từng bước — ghi proof thực tế vào PLAN
    │
    ▼
Codex: Nếu cần mở rộng scope → DỪNG → báo Antigravity
    │
    ▼
Codex: Ghi "Execution Done. Cần Claude Code verify + handoff." vào PLAN
```

Full workflow 7 phase + Anti Sign-off Gate: `agents/WORKFLOW.md`

---

## Rules Enforcement (từ agents/RULES.md)

- **Database**: KHÔNG DELETE/DROP production khi chưa được user approve trực tiếp
- **Git**: Minimal diff — chỉ sửa đúng những gì được giao
  - Nếu cần sửa >3 file cho 1 bug → DỪNG → báo Antigravity
- **Browser**: Đóng trong `finally` block. Random delays (`random.uniform`) giữa thao tác
- **Resources**: Xóa file video/ảnh tạm ngay sau khi job xong
- **Import**: Đặt `import` ở đầu file, không khai báo trong function

---

## Proof Standard — Bắt buộc sau mỗi bước execute

Proof phải là output **thực tế** — không phải lời khẳng định:

```
✅ Chấp nhận:
  - Lệnh đã chạy + output terminal thực tế
  - Log file với timestamp
  - Test result (pass/fail count)
  - HTTP response code thực tế

❌ Không chấp nhận:
  - "Đã sửa xong"
  - "Chắc là ổn"
  - "Có vẻ hoạt động"
  - "Đã kiểm tra" mà không có output
```

---

## Archive Verification Rule

Sau MỌI lệnh move/delete/archive:
```
1. Chạy lệnh
2. Scan source → xác nhận file đã biến mất
3. Scan destination → xác nhận file đã xuất hiện
4. Chỉ khi cả 2 PASS mới tiếp tục
```

---

## Escalation — Khi nào DỪNG và báo Antigravity

- Scope không rõ ràng hoặc PLAN thiếu thông tin
- Cần sửa >3 file cho 1 bug
- Phát hiện risk không được liệt kê trong PLAN
- PLAN conflict với thực tế code
- Cần quyết định kiến trúc lớn

---

## File Conventions

| Loại | Pattern | Lưu ở |
|---|---|---|
| Plan | `PLAN-NNN-short-name.md` | `agents/plans/active/` |
| Task | `TASK-NNN-short-name.md` | `agents/tasks/` |
| ADR | `ADR-NNN-short-name.md` | `agents/decisions/` |

Số NNN: tiếp nối số cuối trong archive, không bao giờ reuse.
