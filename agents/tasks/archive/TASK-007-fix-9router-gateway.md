# Task: Fix 9Router API Gateway Connection Issue
ID: TASK-007
Status: Done
Owner: Codex

## Objective
Hiện tại 9Router API Gateway (`http://localhost:20128/v1`) đang sập / từ chối kết nối (`Connection refused`). Điều này khiến `ai_pipeline.py` bị kẹt ở trạng thái Circuit Breaker `OPEN` và hệ thống AI Captioning bị degrade về `poorman_fallback`. Mục tiêu: Sửa lỗi để 9Router hoạt động trở lại.

## Acceptance Criteria
- [ ] 9Router API Gateway khởi động lại thành công và lắng nghe trên port `20128`.
- [ ] Endpoint `/chat/completions` GET/POST hoạt động và trả về HTTP Status > 0.
- [ ] Xử lý triệt để file `9router_config.json` hoặc `app/services/ai_pipeline.py` đang bị hardcode URL `http://localhost:20128/v1` để nó có thể được cấu hình linh hoạt thông qua biến môi trường hoặc file Settings nhằm xoá bỏ hardcode tĩnh.
- [ ] File `storage/db/config/9router_runtime.json` ghi nhận `circuit_state` = `CLOSED` (có thể bằng cách restart hoặc bắn request thành công).
- [ ] Ghi lại nguyên nhân dẫn tới Gateway sập vào file PLAN.

## Priority
Khẩn cấp (CRITICAL) - Content Auto Publisher đang mất trí não.

## Blockers
Gateway đang câm, cần Codex chui vào check PM2 list, Docker hoặc Log hệ thống để dò xem instance 9Router gốc nằm ở đâu.
