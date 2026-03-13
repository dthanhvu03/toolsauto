# Scope: Tool cá nhân ổn định (FB-first)

## Mục tiêu
- 01 user, chạy trên máy cá nhân (khuyến nghị) hoặc 1 VPS ổn định.
- UI quản lý job: upload nội dung, tạo job, xem trạng thái, retry/reschedule.
- Worker 24/7 xử lý queue.
- Adapter theo platform (ưu tiên FB trước).

## Out of scope (giai đoạn 1)
- Multi-user / RBAC / phân quyền.
- Redis/Celery, microservices.
- Calendar view kéo-thả.
- Analytics nâng cao.

## Yêu cầu tối thiểu (MVP)
- CRUD Job + trạng thái PENDING/RUNNING/DONE/FAILED.
- Upload file + inbox viewer.
- Random caption (từ file cấu hình).
- Worker loop: fetch due job -> dispatch -> update status -> retry/backoff.
- Logging + screenshot khi lỗi (để debug).
- Adapter interface, implement FB adapter dạng "pluggable".

## Tiêu chí thành công
- Job chạy đúng lịch, không chạy trùng.
- UI cập nhật trạng thái theo thời gian thực (HTMX polling).
- Khi lỗi: có log + screenshot + retry theo backoff.