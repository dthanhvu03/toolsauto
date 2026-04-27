# ToolsAuto Operating Workflow v3

## 1. Tổng quan
Ba agent hoạt động theo vai cố định. Không agent nào được làm ngoài phạm vi vai của mình.

| Agent | Vai | Không được làm |
|---|---|---|
| **Antigravity (Anti)** | Orchestrator — Intake, Plan, Governance | Execute code, viết logic |
| **Codex** | Backend/System Engineer — Execute, Debug | Tự ý plan, tự ý assign task cho mình |
| **Claude Code** | UX, Refactor, Quality, Handoff | Execute core logic, viết adapter/worker |

---

## 2. Flow tổng quát

```
User Request
    │
    ▼
[Anti] Phase 1: Intake → tạo TASK-NNN.md
    │
    ▼
[Anti] Phase 2: Research → đọc context, xác định scope
    │
    ▼
[Anti] Phase 3: Planning → tạo PLAN-NNN.md + assign cho Codex hoặc Claude Code
    │
    ├──► [Codex] Phase 4: Execution (nếu task là backend/system)
    │         │
    │         ▼
    │    [Codex] Phase 5: Verification → ghi log/proof vào PLAN
    │
    └──► [Claude Code] Phase 4: Execution (nếu task là UX/refactor/docs)
              │
              ▼
         [Claude Code] Phase 5: Verification → ghi proof vào PLAN
    │
    ▼
[Anti hoặc Claude Code] Phase 6: Decision Recording (nếu cần ADR)
    │
    ▼
[Claude Code] Phase 7: Handoff → cập nhật current-status.md + archive
```

---

## 3. Trạng thái chuẩn của một Task

```
New → Planned → Assigned → In Progress → Verified → Handed Off → Done
```

- **New**: Vừa nhận yêu cầu từ user
- **Planned**: Anti đã tạo PLAN và approve
- **Assigned**: Anti đã ghi rõ Owner trong TASK
- **In Progress**: Agent được assign đang thực thi
- **Verified**: Agent thực thi đã ghi proof verify
- **Handed Off**: Claude Code đã cập nhật current-status.md
- **Done**: Task và Plan đã archive

---

## 4. Workflow chi tiết từng Phase

### Phase 1 — Intake (Owner: Anti)
- Đọc yêu cầu từ user
- Phân loại: Bug / Feature / Refactor / Audit / Documentation
- Tạo `agents/tasks/TASK-NNN.md` từ template
- Ghi rõ: Objective, Priority, Owner (Codex / Claude Code), Blockers, Acceptance Criteria

**Output bắt buộc**: `agents/tasks/TASK-NNN.md` với trạng thái `New`

---

### Phase 2 — Research (Owner: Anti)
**Đọc theo đúng thứ tự này**:
1. `agents/handoffs/current-status.md`
2. `agents/plans/active/`
3. `agents/tasks/` đang active
4. `agents/decisions/`

**Không được**:
- Code bất kỳ thứ gì trong phase này
- Giả định logic cũ là đúng
- Bỏ qua current-status.md

---

### Phase 3 — Planning (Owner: Anti)
- Tạo `agents/plans/active/PLAN-NNN.md` từ template
- Ghi rõ: Goal, Scope, Out of Scope, Approach từng bước, Risks, Validation Plan, Rollback Plan
- **Micro-tasking Rule**: Ưu tiên chia nhỏ PLAN thành các giai đoạn (Phases) có thể thực thi độc lập để tránh cạn kiệt token.
- **Assign rõ ràng** trong PLAN: `Executor: Codex` hoặc `Executor: Claude Code`
- Cập nhật TASK status → `Planned`
- Thông báo cho Codex hoặc Claude Code bắt đầu

**Output bắt buộc**: `agents/plans/active/PLAN-NNN.md` với `Executor` được chỉ định rõ

**Zero-Autonomous-Execution**: Codex và Claude Code KHÔNG được tự bắt đầu execute khi chưa có PLAN từ Anti.

---

### Phase 4 — Execution

#### Nếu Owner là Codex:
- Đọc PLAN được Anti assign trước khi viết 1 dòng code
- Chỉ sửa đúng những file được liệt kê trong Scope của PLAN
- Mỗi bước = 1 logical change nhỏ, có thể verify độc lập
- Nếu phát hiện scope phải mở rộng → DỪNG → báo Anti
- Nếu sửa >3 file cho 1 bug → DỪNG → báo Anti

#### Nếu Owner là Claude Code:
- Đọc PLAN được Anti assign trước khi viết 1 dòng code
- Chỉ làm: UX, template, CSS, docs, refactor readability, handoff writing
- Không viết: adapter, worker, core business logic, database migration
- Minimal diff — không refactor "tiện thể"

---

### Phase 5 — Verification (Owner: agent đã execute)
**Bắt buộc ghi proof vào PLAN file**:
- Lệnh đã chạy + output
- Log thực tế
- Test result hoặc manual check result

**Không được**:
- Dùng "chắc là ổn" hoặc "có vẻ hoạt động"
- Mark task Done trước khi có proof
- Chuyển sang Phase 6/7 khi chưa verify xong

Sau khi verify xong → cập nhật TASK status → `Verified` → **chuyển sang Phase 5.5**

---

### Phase 5.5 — Anti Sign-off Gate (Owner: Anti) ⛔ BLOCKING

**Đây là cổng chặn bắt buộc. Không qua được Phase 5.5 = KHÔNG được archive, KHÔNG được mark Done.**

Anti phải điền checklist này trực tiếp vào file PLAN trước khi cho phép Claude Code chuyển sang Phase 7:

```markdown
## Anti Sign-off Gate
Reviewed by: Antigravity — [YYYY-MM-DD]

### Acceptance Criteria Check
*(Lấy từ TASK — điền từng dòng, không được bỏ qua)*

| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | [criterion 1 từ TASK] | Yes / No — [link/ref proof] | ✅ / ❌ |
| 2 | [criterion 2 từ TASK] | Yes / No — [link/ref proof] | ✅ / ❌ |
| 3 | [criterion 3 từ TASK] | Yes / No — [link/ref proof] | ✅ / ❌ |

### Scope Check
- [ ] Executor chỉ làm đúng Scope trong PLAN, không mở rộng âm thầm
- [ ] Không có file ngoài Scope bị sửa

### Proof Quality Check
- [ ] Proof là output thực tế (log/command/screenshot) — không phải lời khẳng định
- [ ] Proof cover hết các mục trong Validation Plan

### Final Decision
- [ ] **ALL criteria PASS** → Ghi: `APPROVED — Ready to archive`
- [ ] **Có criterion FAIL** → Ghi lý do + tạo TASK mới cho phần còn thiếu → KHÔNG archive task hiện tại

**Verdict**: APPROVED / REJECTED — [lý do nếu REJECTED]
```

**Quy tắc cứng cho Anti**:
- Không được dùng "có vẻ ổn", "chắc là xong" — phải ghi rõ proof reference
- Nếu criterion nào không có proof → tự động REJECTED, tạo task fix
- Nếu bất kỳ ô nào trong bảng trống → Phase 5.5 chưa hoàn thành

---

### Phase 6 — Decision Recording (Owner: Anti hoặc Claude Code)
Tạo `agents/decisions/ADR-NNN.md` khi:
- Chọn giữa 2+ phương án kỹ thuật lớn
- Thay đổi cấu trúc database/schema
- Quyết định về library/framework dài hạn
- Thay đổi core flow

Dùng template `agents/templates/adr.template.md`.

---

### Phase 7 — Handoff (Owner: Claude Code)
**Bắt buộc trước khi kết thúc phiên**:

1. Cập nhật `agents/handoffs/current-status.md`:
   - System state hiện tại
   - Active tasks còn lại
   - Unfinished work và blockers
   - Next action cụ thể (không mơ hồ)

2. Nếu task Done:
   - Di chuyển `agents/tasks/TASK-NNN.md` → `agents/tasks/archive/`
   - Di chuyển `agents/plans/active/PLAN-NNN.md` → `agents/plans/archive/`

3. Update TASK status → `Done`

---

## 5. Inter-Agent Handoff Protocol

Khi Codex xong execution và cần Claude Code review/handoff:
```
Codex ghi vào PLAN: "Execution Done. Cần Claude Code verify UI + viết handoff."
Claude Code đọc PLAN → verify → viết current-status.md → archive
```

Khi Claude Code phát hiện lỗi backend trong quá trình review:
```
Claude Code DỪNG → ghi issue vào current-status.md → báo Anti
Anti tạo TASK mới → assign Codex
```

Khi Anti cần context từ Codex hoặc Claude Code:
```
Anti đọc current-status.md + PLAN execution notes
Nếu không đủ → hỏi trực tiếp trong phiên
```

---

## 6. Workflow theo loại công việc

### Bug / Incident
```
Anti: Facts → Hypotheses → assign Codex
Codex: Log Trace → Root Cause → Fix → Regression check
Claude Code: Verify UI impact → viết handoff
```

### Feature
```
Anti: Request → Normalize → PLAN → assign
Codex: Implement core logic
Claude Code: Review UX/template → ADR nếu cần → Handoff
```

### Refactor
```
Anti: Define unchanged behavior → PLAN → assign Claude Code
Claude Code: Review structure → Minimal steps → Verify → Handoff
Codex: Chỉ vào nếu có phần backend phức tạp
```

### Audit
```
Anti: Scan → Assess → Identify risks → Prioritize → Recommend
Output: ADR hoặc PLAN mới cho sprint tiếp theo
```

---

## 7. Escalation Rules

| Tình huống | Escalate lên |
|---|---|
| Scope mơ hồ | Anti |
| Plan conflict với implementation thực tế | Anti |
| Priority tranh chấp | Anti |
| Lỗi runtime sâu, worker treo, queue/concurrency | Codex |
| Cần cleanup handoff, UX thiếu tự nhiên | Claude Code |
| Cần sửa >3 file cho 1 bug | DỪNG → Anti |

---

## 8. Guardrails — Quy tắc thép

1. **Zero-Autonomous-Execution**: Codex và Claude Code KHÔNG tự ý execute khi chưa có TASK + PLAN từ Anti
2. **No Plan No Code**: Không 1 dòng code nào trước khi PLAN tồn tại trong `agents/plans/active/`
3. **No Scope Creep**: Không mở rộng scope âm thầm — phát hiện thì báo Anti
4. **Proof Required**: Verify phải có bằng chứng thực tế, không phải lời khẳng định
5. **Checkpoint Rule**: Cập nhật `current-status.md` khi bắt đầu task mới, đổi phase, trước sửa logic lớn, sau verify milestone
6. **Handoff is Mandatory**: Không phiên nào kết thúc mà không update current-status.md
7. **Atomic Commits**: Mỗi commit = 1 logical change. Không gom nhiều thứ vào 1 commit
8. **Thin Controller**: Router chỉ nhận request, validate, gọi service, trả response. Cấm viết SQL thô hoặc gọi subprocess trong router.
9. **Schema Centralization**: Mọi Pydantic BaseModel phải nằm trong `app/schemas/`. Cấm định nghĩa schema chui trong router.
10. **No God Service**: Không để 1 file service vượt quá 1000 LOC. Nếu phát hiện — tách nhỏ theo domain.
11. **Adapter Must Be Blind**: Dispatcher cấm hardcode rẽ nhánh theo tên platform. Dùng Registry Pattern.
12. **DRY Error Handling**: Luồng try/catch Playwright phải dùng Decorator hoặc Helper chung. Cấm copy-paste.

---

## 9. Daily Operating Checklist

### Bắt đầu phiên (mọi agent)
- [ ] Đọc `current-status.md`
- [ ] Đọc `plans/active/`
- [ ] Xác định task mình đang được assign
- [ ] Xác nhận với Anti nếu không rõ

### Trong khi làm
- [ ] Bám đúng Scope của PLAN
- [ ] Ghi lại rủi ro phát sinh ngay khi phát hiện
- [ ] Cập nhật Checkpoint nếu đến milestone

### Kết thúc phiên (Claude Code làm)
- [ ] Update `current-status.md`
- [ ] Ghi Next Action cụ thể
- [ ] Archive task/plan nếu Done

---

## 10. Failure Recovery Workflow
Nếu một agent bị dừng đột ngột (hết token, lỗi runtime):

1. **Đọc `current-status.md`** — xác định last known state
2. **Phân loại work**:
   - `Confirmed Done`: Đã verify + đã ghi proof → tin được
   - `Claimed but unverified`: Phải kiểm tra lại
   - `In-progress / Unknown`: Coi như chưa xong
3. **Verify lại** phần "Claimed but unverified" trước khi tiếp tục
4. **Resume từ checkpoint** gần nhất đã confirm
5. **Anti re-assign** nếu cần thiết

---

> *"Viết để người khác tiếp tục được ngay, không phải để chứng minh mình đã làm."*
