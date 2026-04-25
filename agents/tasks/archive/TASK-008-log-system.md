# TASK-008: System Logs Optimization

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-008 |
| **Status** | In Progress (Backend Scope Done, chờ Claude verify/handoff) |
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
- [x] Dòng lệnh `PM2 logs` không còn bị Double Timestamps trên terminal.
- [x] Log PM2 (và log UI) không in ra thông báo `[IDLE] Backlog=...` liên tục (chỉ còn ghi ở backup).
- [x] `app.log` cục bộ vẫn giữ được Timestamp.
- [x] Prefix của Log khi có việc chạy sẽ hiển thị rõ ràng `[TÊN_WORKER] [Job-ID] [TRẠNG_THÁI] Tin nhắn`.

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [x] Bước 1: Refactor `app/utils/logger.py` sang kiến trúc Dual-Stream (Stream INFO không asctime, File DEBUG có asctime).
- [x] Bước 2: Đổi toàn bộ `logger.info("[IDLE] ...")` trong `workers/publisher.py` sang `logger.debug(...)`.
- [x] Bước 3: Chuẩn hóa prefix job logs trong `workers/publisher.py` và `workers/ai_generator.py` theo format `[WORKER] [Job-ID] [PHASE]`.

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```
$ python -m py_compile app/utils/logger.py workers/publisher.py workers/ai_generator.py
# PASS (exit code 0)

$ Select-String workers/publisher.py,workers/ai_generator.py 'logger\.info\("\[IDLE\]'
# No results

$ python logger probe (info+debug)
Console:
[INFO] task008_logger_probe_debug: [PROBE] info check
# Stream không có timestamp; debug không nổi trên stream

$ grep 'task008_logger_probe_debug' logs/app.log
2026-04-19 06:46:38 [INFO] task008_logger_probe_debug: [PROBE] info check
2026-04-19 06:46:38 [DEBUG] task008_logger_probe_debug: [PROBE] debug-only check for file handler
# app.log giữ timestamp + lưu được debug
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-19 | New | Task được tạo bởi Anti dựa trên DECISION-001 |
| 2026-04-19 | Planned | PLAN-008 được tạo và approve |
| 2026-04-19 | In Progress | Codex đã hoàn thành backend scope (logger + workers); chờ Claude verify/handoff |
