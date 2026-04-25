# PLAN-NNN: [Plan Name]

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-NNN |
| **Status** | Draft / Active / Executing / Done / Cancelled |
| **Executor** | Codex / Claude Code ← agent thực thi |
| **Created by** | Antigravity |
| **Related Task** | TASK-NNN |
| **Related ADR** | ADR-NNN / None |
| **Created** | YYYY-MM-DD |
| **Updated** | YYYY-MM-DD |

---

## Goal
Mục tiêu kỹ thuật cụ thể cần đạt. Một đoạn ngắn, rõ ràng.

---

## Context
- Hiện trạng hệ thống liên quan
- Vấn đề đang gặp phải
- Lý do cần thay đổi

---

## Scope
*(Executor chỉ được làm những gì trong danh sách này)*

- File/component A — thay đổi gì
- File/component B — thay đổi gì

## Out of Scope
*(Executor KHÔNG được làm những điều này trong plan này)*

- ...

---

## Proposed Approach
*(Các bước thực hiện theo thứ tự — Executor đọc và làm từng bước)*

**Bước 1**: [mô tả cụ thể]
**Bước 2**: [mô tả cụ thể]
**Bước 3**: [mô tả cụ thể]

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| [mô tả risk] | Low/Med/High | [hướng xử lý] |

---

## Validation Plan
*(Executor phải thực hiện những check này và ghi kết quả vào Execution Notes)*

- [ ] Check 1: [lệnh / phương thức kiểm tra]
- [ ] Check 2: [lệnh / phương thức kiểm tra]
- [ ] Check 3: [lệnh / phương thức kiểm tra]

---

## Rollback Plan
Nếu execution fail → [mô tả cách rollback cụ thể, ví dụ: `git checkout -- <file>`]

---

## Execution Notes
*(Executor điền vào theo thứ tự từng bước — KHÔNG để trống khi Done)*

- ✅ / ❌ / ⏳ Bước 1: [kết quả thực tế]
- ✅ / ❌ / ⏳ Bước 2: [kết quả thực tế]

**Verification Proof**:
```
# Output thực tế của validation checks
```

---

## Anti Sign-off Gate ⛔
*(Anti điền vào — BLOCKING. Không có section này = Claude Code không được archive)*

**Reviewed by**: Antigravity — [YYYY-MM-DD]

### Acceptance Criteria Check
*(Copy từ TASK — điền từng dòng, không bỏ qua)*

| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | [criterion từ TASK] | Yes/No — [ref] | ✅ / ❌ |
| 2 | [criterion từ TASK] | Yes/No — [ref] | ✅ / ❌ |

### Scope & Proof Check
- [ ] Executor làm đúng Scope, không mở rộng âm thầm
- [ ] Proof là output thực tế, không phải lời khẳng định
- [ ] Proof cover hết Validation Plan

### Verdict
> **APPROVED** / **REJECTED** — [lý do nếu REJECTED, tạo TASK mới cho phần thiếu]

---

## Handoff Note
*(Claude Code điền vào sau khi Anti APPROVED)*

- Trạng thái sau execution: ...
- Những gì cần làm tiếp (nếu có): ...
- Archived: Yes / No — [date]
