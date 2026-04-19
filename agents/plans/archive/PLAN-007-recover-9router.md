# Plan: Recover 9Router API Gateway
ID: PLAN-007
Task ID: TASK-007
Executor: Codex

## Goal
Khôi phục lại luồng sinh nội dung AI bằng cách khôi phục cổng kết nối 9Router API Gateway (`localhost:20128`), giúp Circuit Breaker của `ai_pipeline.py` thoát khỏi trạng thái `OPEN`.

## Scope
- Dò tìm instance của 9Router. Kiểm tra các vị trí nghi ngờ: Docker containers, PM2 processes, hoặc file thực thi độc lập (Ollama/Custom Gateway).
- Khởi động lại service và xác nhận port `20128` có Listen trở lại hay chưa.
- Test bằng `curl http://localhost:20128/v1/models` hoặc tool tương đương.
- **Refactor URL**: Truy quét file `storage/db/config/9router_config.json`, `app/services/ai_pipeline.py` và `app/config.py`. Phài đảm bảo URL của 9Router KHÔNG BỊ HARDCODE (Ví dụ: `http://localhost:12345/v1` mà phải được kế thừa từ biến cấu hình tập trung để đồng bộ với chiến dịch Refactor toàn dự án).
- Trả lại hệ thống vận hành trơn tru cho Antigravity.

## Out of Scope
- Không đụng chạm vào cấu trúc core code của `ai_pipeline.py` hay mô hình `content_orchestrator.py` vì chúng hoạt động đúng chuẩn ngắt mạch (Circuit Breaker) khi server đích down.

## Approach
1. Mở terminal, chạy lệnh `docker ps -a` và `pm2 status` để chẩn đoán xem 9Router Service được quản lý bởi Process Manager nào.
2. Kiểm tra log của 9Router (tuỳ theo PM2 logs hoặc `docker logs`) để tìm nguyên nhân gốc rễ (Root Cause) bị crash.
3. Restart process.
4. Lấy status ping port 20128 trả về OK.

## Validation Plan
1. **Automated Test / Diagnostics**: Chạy lệnh curl vào port 20128, xác nhận phản hồi HTTP thay vì `Connection refused`.
2. **Review State**: Khởi động backend sinh mẫu log AI xem Circuit `HALF_OPEN -> CLOSED`.

## Execution Notes
### Step 1 — Diagnose Process Manager (done)
- Ran:
  - `docker ps -a` -> Docker CLI unavailable in this WSL distro (cannot use Docker path for this task).
  - `pm2 status` -> PM2 daemon running but process list initially empty.
  - `ss -ltnp | grep ':20128'` + `curl http://localhost:20128/v1/models` -> port closed (`Connection refused`).
- Root cause trace:
  - Existing PM2 logs indicated `9Router_Gateway` historically managed by PM2.
  - `9router` launched without headless flags enters interactive menu (`Choose Interface`), so API listener was not reliably up.

### Step 2 — Recover Gateway Service on 20128 (done)
- Restarted gateway in non-interactive mode:
  - `pm2 delete 9Router_Gateway`
  - `pm2 start 9router --name 9Router_Gateway -- --tray --no-browser --skip-update`
- Persisted process list:
  - `pm2 save`
- Proof:
  - `pm2 status` shows `9Router_Gateway` online.
  - `ss -ltnp` shows `LISTEN ... 0.0.0.0:20128`.
  - `curl -i http://localhost:20128/v1/models` returns `HTTP/1.1 200 OK`.
  - Response includes model list (`models_count=6` in diagnostic parse).

### Step 3 — Refactor URL Hardcode in Scope Files (done)
- File changes:
  - `app/config.py`: added centralized `ROUTER_BASE_URL` env config.
  - `app/services/ai_pipeline.py`: replaced 2 hardcoded fallbacks with `config.ROUTER_BASE_URL`.
- Scope-limited audit file:
  - `storage/db/config/9router_config.json` kept as runtime config source (no structural change needed).
- Proof:
  - `python -m py_compile app/config.py app/services/ai_pipeline.py` -> pass.
  - `grep` confirms `ai_pipeline.py` now references `config.ROUTER_BASE_URL` and no `127.0.0.1:20128` literal remains.

### Step 4 — Validation of Runtime State (done)
- Initial state file showed degraded mode:
  - `storage/db/config/9router_runtime.json` had `"circuit_state": "OPEN"`.
- Ran pipeline connectivity diagnostic via `AICaptionPipeline.test_connection(...)`.
- Post-check proof:
  - Shared runtime state now reports `"runtime_circuit_state": "CLOSED"`.
  - `test_connection` received HTTP 429 from model endpoint (gateway reachable, provider limit/rate condition).
  - Gateway endpoint remains reachable with HTTP 200 on `/v1/models`.

## Anti Sign-off Gate
Reviewed by: Antigravity — [2026-04-19]

## Claude Code Verify — [2026-04-19]
**Reviewer**: Claude Code (UX/Refactor/Quality role)

**Proof checked:**
- `app/config.py:127` — `ROUTER_BASE_URL` env-driven, no hardcode ✅
- `app/services/ai_pipeline.py` — grep `20128` = 0 hits; references `config.ROUTER_BASE_URL` ✅
- `storage/db/config/9router_runtime.json` — `"circuit_state": "CLOSED"` ✅
- All TASK-007 Acceptance Criteria: PASS

**Status: DONE — Ready to archive**
