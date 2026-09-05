# TASK-056 — Hạ tầng tự phục hồi

- **Plan**: PLAN-057
- **Executor**: Claude Code
- **Giao bởi**: Owner, 2026-09-04 ("nâng cấp hệ thống để chạy trơn tru")
- **Trạng thái**: In Progress

## Việc
A. Mở lại CI (sửa cả python-version lẫn pytest collect file hỏng)
B. Bỏ `|| true` ở `alembic upgrade head` trong deploy
C. `docker-compose.yml` + `restart: unless-stopped` cho Postgres
D. `manage.py db backup` dùng `pg_dump` + chứng minh restore được

## Ràng buộc
Chỉ hạ tầng/config. Không chạm adapter/worker/core logic — phần đó cần ADR mới.
