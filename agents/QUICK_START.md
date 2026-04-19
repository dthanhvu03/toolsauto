# ToolsAuto Quick Start v3 — 3 Agent Model

Copy-paste các lệnh dưới vào chat với đúng agent.

---

## Antigravity (Anti) — Dùng khi giao việc mới

### Nhận task từ user và lập plan
```
Act as Antigravity for ToolsAuto.
Yêu cầu: [mô tả yêu cầu]

1. Đọc agents/handoffs/current-status.md và agents/plans/active/
2. Tạo TASK-NNN.md (dùng agents/templates/task.template.md)
3. Nếu cần code: tạo PLAN-NNN.md (dùng agents/templates/plan.template.md), ghi rõ Executor: Codex hoặc Claude Code
4. Cập nhật current-status.md
5. Báo cáo: task ID, plan ID, ai cần làm tiếp
```

### ⛔ Pre-Close Sign-off — PHẢI làm trước khi archive bất kỳ task nào
```
Act as Antigravity for ToolsAuto.
Sign-off: agents/plans/active/PLAN-NNN.md

1. Đọc TASK-NNN — liệt kê toàn bộ Acceptance Criteria
2. Với TỪNG criterion: tìm proof trong PLAN Execution Notes, đánh PASS/FAIL
3. Check Scope: executor có làm ngoài scope không?
4. Điền bảng Anti Sign-off Gate trực tiếp vào PLAN file
5. APPROVED (tất cả PASS) → báo Claude Code archive
   REJECTED (có FAIL) → tạo TASK mới, KHÔNG archive

Cấm: "chắc ổn", "có vẻ xong" — phải ref proof cụ thể từng criterion.
```

### Risk review trước khi merge
```
Act as Antigravity for ToolsAuto.
Risk Review: [branch / change / plan]
Phát hiện: breaking changes, security risk, rollback readiness, observability gaps.
Output: GO / GO WITH CAUTION / NO-GO + lý do.
```

---

## Codex — Dùng khi giao execute backend

### Execute plan được assign
```
Act as Codex for ToolsAuto.
Execute: agents/plans/active/PLAN-NNN.md

1. Đọc toàn bộ PLAN trước khi viết 1 dòng code
2. Chỉ sửa file trong Scope — không mở rộng
3. Execute từng bước nhỏ, ghi Execution Notes + proof vào PLAN
4. Nếu cần mở rộng scope → DỪNG → báo Anti
5. Sau khi xong: ghi "Execution Done. Cần Claude Code verify + handoff."
```

### Debug incident
```
Act as Codex for ToolsAuto.
Symptom: [mô tả lỗi]

Flow: Observed Facts → Hypotheses → Log Trace → Root Cause → Fix → Regression Check
Output: incident note, facts vs assumptions tách biệt.
```

---

## Claude Code — Dùng cho UX / Refactor / Handoff

### Startup đầu phiên
```
Act as Claude Code for ToolsAuto.
1. Đọc agents/handoffs/current-status.md
2. Đọc agents/plans/active/
3. Báo cáo: task được assign, đang ở phase nào, việc tiếp theo là gì
```

### Execute plan UX/refactor được assign
```
Act as Claude Code for ToolsAuto.
Execute: agents/plans/active/PLAN-NNN.md

1. Đọc toàn bộ PLAN trước khi làm
2. Chỉ làm trong Scope: template, CSS, UX, docs, refactor readability
3. Minimal diff — không đổi behavior, không refactor tiện thể
4. Ghi proof verify vào PLAN
5. Viết handoff, update current-status.md
```

### Kết thúc phiên (bắt buộc)
```
Act as Claude Code for ToolsAuto.
Kết thúc phiên — viết Handoff.

1. Cập nhật agents/handoffs/current-status.md:
   - System State, Done This Session (có proof), Unfinished, Blockers, Next Action cụ thể
2. Nếu task Done: move TASK → tasks/archive/, move PLAN → plans/archive/
```

---

## Lệnh vạn năng — Khi muốn agent tự tìm đường

```
Hãy quét agents/ và tiếp tục theo quy trình ToolsAuto v3.
Đọc current-status.md trước, báo cáo hiện trạng, rồi mới hành động.
```

## Lệnh phục hồi — Khi agent bị ngắt nửa chừng

```
Agent trước đã bị dừng đột ngột.
Thực hiện Failure Recovery Workflow trong agents/WORKFLOW.md Section 10.
Đọc current-status.md, phân loại Done/Claimed/Unknown, verify lại trước khi tiếp tục.
```
