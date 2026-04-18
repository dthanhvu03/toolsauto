🚀 ToolsAuto Operating Workflow

## 1. Mục tiêu của workflow
Workflow này giúp mọi agent trong ToolsAuto làm việc theo cùng một nhịp:
- Hiểu đúng việc trước khi làm.
- Không nhảy vào code quá sớm.
- Luôn có bước verify.
- Luôn kết thúc bằng handoff rõ ràng.

## 2. Flow tổng quát
`New Request → Normalize Task → Research Context → Create / Update Plan → Execute → Verify → Record Decision (if needed) → Write Handoff → Done / Next Agent`

## 3. Trạng thái chuẩn của một task
`New → Planned → In Progress → Verified → Handed Off → Done`

### Ý nghĩa
- **New**: vừa nhận yêu cầu.
- **Planned**: đã rõ scope và hướng làm.
- **In Progress**: đang thực thi.
- **Verified**: đã kiểm tra cơ bản.
- **Handed Off**: đã ghi bàn giao.
- **Done**: kết thúc hoàn toàn.

---

## 4. Workflow theo từng phase

### Phase 1 — Intake / Nhận việc
Mục tiêu: Biến yêu cầu thô thành task rõ ràng.
- **Bắt buộc**: Đọc yêu cầu hiện tại, xác định loại hình (Bug, Feature, Refactor, Audit, Documentation).
- **Output**: `agents/tasks/TASK-XXX.md`.

### Phase 2 — Research Context
Mục tiêu: Hiểu trạng thái hiện tại trước khi đề xuất thay đổi.
- **Phải đọc theo thứ tự**: `current-status.md` -> `plans/active/` -> active `tasks` -> `decisions/`.
- **Không được làm**: Code ngay khi chưa đọc context, giả định logic cũ là đúng.

### Phase 3 — Planning
Mục tiêu: Đề xuất giải pháp kỹ thuật cụ thể.
- **Bắt buộc**: Cho mọi thay đổi logic, cấu trúc hoặc dọn dẹp hệ thống. 
- **Quy tắc**: Bản kế hoạch **phải** tồn tại trong dự án (`agents/plans/active/PLAN-XXX.md`) trước khi thực hiện. Không được chỉ sử dụng kịch bản ẩn/nội bộ của Agent.
- **Output**: `agents/plans/active/PLAN-XXX.md`.

### Phase 4 — Execution
Mục tiêu: Thực thi thay đổi với rủi ro thấp nhất (low blast radius).
- **Nguyên tắc**: Ưu tiên minimal-diff, không mở rộng scope âm thầm.

### Phase 5 — Verification
Mục tiêu: Xác nhận thay đổi bằng bằng chứng thực tế.
- **Phương thức**: Log, command, output, manual flow, regression check.
- **Không được**: Dùng "chắc là ổn", mark done nếu chưa verify.
- **Checkpoint**: Chỉ được chuyển phase hoặc archive task sau khi đã có bằng chứng Verify rõ ràng được ghi lại.

### Phase 6 — Decision Recording
Mục tiêu: Lưu lại lý do tại sao một quyết định lớn được đưa ra.
- **Output**: `agents/decisions/ADR-XXX.md`.

### Phase 7 — Handoff
Mục tiêu: Giúp agent sau tiếp tục ngay lập tức.
- **Bắt buộc**: Cập nhật `agents/handoffs/current-status.md`.
- **Dọn dẹp**: Di chuyển Task hoàn thành vào `tasks/archive/` và Plan hoàn thành vào `plans/archive/`.

---

## 5. Workflow theo loại công việc
- **Bug/Incident**: Facts -> Hypotheses -> Log Trace -> Root Cause -> Fix -> Regression -> Handoff.
- **Feature**: Request -> Normalize -> Plan -> Implement -> Verify -> ADR (if needed) -> Handoff.
- **Refactor**: Review structure -> Define unchanged behavior -> Minimal steps -> Verify -> Handoff.
- **Audit**: Scan -> Assess state -> Identify risks -> Prioritize -> Recommend.

---

## 6. Ownership workflow theo agent
- **Antigravity**: Intake, task normalization, planning, prioritization, governance.
- **Codex**: Execution, deep debugging, core/runtime work, performance.
- **Claude**: Refactor review, documentation, handoffs, interaction flows, readability.

---

## 7. Escalation rules
- **Escalate to Antigravity**: Scope mơ hồ, Plan/Implementation conflict, priority tranh chấp.
- **Escalate to Codex**: Lỗi runtime sâu, worker treo, queue/concurrency problem.
- **Escalate to Claude**: Cần cleanup bàn giao, kịch bản tương tác thiếu tự nhiên.

---

## 8. Guardrails (Quy tắc thép)
- Không code khi chưa hiểu context.
- Không bỏ qua handoff.
- Không coi “đã gõ xong” là “đã hoàn thành”.
- Không đổi scope âm thầm.
- Không để quyết định kiến trúc lớn mà không có ADR.
- **Zero-Autonomous-Execution**: **CẤM TUYỆT ĐỐI** việc tự ý thực thi thay đổi nếu chưa có Task + Plan đã được duyệt và phân công (Delegate) rõ ràng trong thư mục `agents/`.
- **Checkpoint Rule**: Bắt buộc cập nhật `current-status.md` khi: bắt đầu task mới, đổi phase, trước khi sửa logic lớn, hoặc sau khi verify xong một mốc quan trọng.

---

## 9. Daily operating checklist
- **Sáng/Bắt đầu**: Đọc `current-status.md`, task liên quan, plan active.
- **Trong khi làm**: Bám đúng scope, ghi lại rủi ro phát sinh, tuân thủ **Checkpoint Rule** để luôn có điểm phục hồi.
- **Cuối phiên**: Update handoff, ghi validation status và next action cụ thể.

---

## 10. Failure Recovery Workflow
Nếu một Agent bị dừng đột ngột (hết token, lỗi runtime, mất context):

### Bước 1 — Read current state
- Đọc `agents/handoffs/current-status.md`.
- Đối chiếu với Task và Plan đang active.

### Bước 2 — Reconstruct last safe point
- Phân loại công việc: 
    - **Confirmed Done**: Đã xong + Đã verify + Đã ghi log -> Có thể tin.
    - **Claimed but unverified**: Agent trước nói đã làm nhưng chưa có verify rõ -> Bắt buộc kiểm tra lại.
    - **In-progress / Unknown**: Coi như chưa xong.

### Bước 3 — Verify before resuming
- Kiểm tra lại các phần "Claimed but unverified".
- Tuyệt đối không tiếp tục dựa trên giả định.

### Bước 4 — Resume from safe state
- Chỉ bắt đầu lại từ mốc ổn định (Checkpoint) gần nhất đã xác nhận.

### Bước 5 — Update handoff
- Ghi lại trạng thái đã phục hồi và các phần đã re-verify.

---

## 11. Nguyên tắc cốt lõi
> *"Viết để người khác tiếp tục được ngay, không phải để chứng minh mình đã làm."*
