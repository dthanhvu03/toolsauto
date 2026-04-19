# TASK-008: System Logs Optimization

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-008 |
| **Status** | Planned |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-008 |
| **Created** | 2026-04-19 |
| **Updated** | 2026-04-19 |

---

## Objective
Tối ưu hóa hệ thống Log để loại bỏ Double Timestamps, giảm tải log rác từ trạng thái IDLE của các Worker, và chuẩn hóa cấu trúc Prefix.

---

## Scope
- Tách Formatter của Python cho StreamHandler và FileHandler trong `app/utils/logger.py`.
- Lọc quét và đổi toàn bộ `logger.info(...)` của vòng lặp IDLE trong thư mục `workers/*.py` xuống `logger.debug(...)`.
- Chuẩn hóa Prefix log ở các Worker theo chuẩn định sẵn.

## Out of Scope
- Code phần CSS / UI Highlight trên trang Web Dashboard (Claude Code sẽ đảm nhận theo thỏa thuận trong DECISION-001).

---

## Blockers
- Không có

---

## Acceptance Criteria
- [ ] Dòng lệnh `PM2 logs` không còn bị Double Timestamps trên terminal.
- [ ] Log PM2 (và log UI) không in ra thông báo `[IDLE] Backlog=...` liên tục (chỉ còn ghi ở backup).
- [ ] `app.log` cục bộ vẫn giữ được Timestamp.
- [ ] Prefix của Log khi có việc chạy sẽ hiển thị rõ ràng `[TÊN_WORKER] [Job-ID] [TRẠNG_THÁI] Tin nhắn`.

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [ ] Bước 1: 
- [ ] Bước 2: 

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```
# Lệnh đã chạy + output thực tế
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-19 | New | Task được tạo bởi Anti dựa trên DECISION-001 |
| 2026-04-19 | Planned | PLAN-008 được tạo và approve |
